import base64
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from agentctl import apptoken, github

ROOT = Path(__file__).resolve().parents[2]


class SecretLookupTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def test_developer_specific_secret_wins_over_shared(self):
        os.environ["CONDUCTOR_SECRETS"] = json.dumps({"DISPATCH_TOKEN": "shared", "DISPATCH_TOKEN_ALICE_SMITH": "hers"})
        self.assertEqual(github.secret("DISPATCH_TOKEN", "alice-smith"), "hers")
        self.assertEqual(github.secret("DISPATCH_TOKEN"), "shared")
        self.assertEqual(github.secret("MISSING", "bob"), "")

    def test_a_named_developer_never_gets_the_shared_secret_by_accident(self):
        os.environ.pop("CONDUCTOR_LOCAL_DEVELOPER", None)
        os.environ["CONDUCTOR_SECRETS"] = json.dumps({"DISPATCH_TOKEN": "shared"})
        self.assertEqual(github.secret("DISPATCH_TOKEN", "bob"), "")
        # On bob's own Mac the plain name is bob's.
        os.environ["CONDUCTOR_LOCAL_DEVELOPER"] = "bob"
        self.assertEqual(github.secret("DISPATCH_TOKEN", "bob"), "shared")
        self.assertEqual(github.secret("DISPATCH_TOKEN", "alice"), "")

    def test_falls_back_to_the_environment_for_local_runs(self):
        os.environ.pop("CONDUCTOR_SECRETS", None)
        os.environ["CLAUDE_TRIGGER_URL_BOB"] = "https://bob"
        self.assertEqual(github.secret("CLAUDE_TRIGGER_URL", "bob"), "https://bob")


class AppTokenTests(unittest.TestCase):
    def test_remote_url_forms(self):
        for url in ["https://github.com/acme/app.git", "git@github.com:acme/app.git", "https://github.com/acme/app/\n",
                    "https://x-access-token:abc@github.com/acme/app"]:
            self.assertEqual(apptoken.repo_from_remote(url), "acme/app", url)
        self.assertIsNone(apptoken.repo_from_remote("https://example.com/acme/app"))

    @unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
    def test_jwt_is_signed_with_the_app_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, pub = Path(tmp) / "key.pem", Path(tmp) / "pub.pem"
            subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
            subprocess.run(["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(pub)], check=True, capture_output=True)
            token = apptoken.make_jwt("12345", key, now=1_000_000)
            header, payload, signature = token.split(".")
            pad = lambda s: s + "=" * (-len(s) % 4)
            self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(payload))),
                             {"iat": 999_940, "exp": 1_000_540, "iss": "12345"})
            sig = Path(tmp) / "sig"
            sig.write_bytes(base64.urlsafe_b64decode(pad(signature)))
            verify = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig)],
                                    input=f"{header}.{payload}".encode(), capture_output=True)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_cached_token_is_reused_only_while_valid_and_for_the_same_repo(self):
        cached = {"repo": "acme/app", "app_id": "1", "token": "t", "expires": 2000}
        self.assertTrue(apptoken._fresh(cached, "acme/app", "1", now=1000))
        self.assertFalse(apptoken._fresh(cached, "acme/app", "1", now=1800))
        self.assertFalse(apptoken._fresh(cached, "acme/other", "1", now=1000))
        self.assertFalse(apptoken._fresh(cached, "acme/app", "2", now=1000))


class TemplateNeutralityTests(unittest.TestCase):
    def test_init_fills_in_the_people(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ("scripts/init.sh", ".github/CODEOWNERS", "policy/roles.toml"):
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, Path(tmp) / rel)
            run = subprocess.run([str(Path(tmp) / "scripts/init.sh"), "alice", "bob-b"], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            roles = tomllib.loads((Path(tmp) / "policy/roles.toml").read_text())
            self.assertEqual(roles["directors"], ["alice"])
            self.assertEqual(roles["humans"], ["alice", "bob-b"])
            owners = (Path(tmp) / ".github/CODEOWNERS").read_text()
            self.assertIn("@alice", owners)
            self.assertNotIn("DIRECTOR_LOGIN", owners)
            again = subprocess.run([str(Path(tmp) / "scripts/init.sh"), "carol"], capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            bad = subprocess.run([str(ROOT / "scripts/init.sh"), "not a login"], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)


if __name__ == "__main__":
    unittest.main()


class SandboxCheckTests(unittest.TestCase):
    def test_placeholders_are_not_mistaken_for_real_tokens(self):
        from agentctl import doctor
        for real in ("ghp_abc", "ghs_abc", "github_pat_abc", "gho_abc"):
            self.assertTrue(doctor.looks_like_real_github_token(real), real)
        for fake in ("proxy-managed", "sbx-cs-123", "", None):
            self.assertFalse(doctor.looks_like_real_github_token(fake), fake)

    def test_a_path_down_to_the_project_is_fine_but_private_folders_are_not(self):
        from agentctl import doctor
        with tempfile.TemporaryDirectory() as tmp:
            users = Path(tmp) / "Users"
            (users / "alice" / "dev" / "project").mkdir(parents=True)
            self.assertEqual(doctor.private_host_paths(users), [])
            (users / "alice" / "Documents").mkdir()
            (users / "alice" / ".ssh").mkdir()
            self.assertEqual(sorted(Path(p).name for p in doctor.private_host_paths(users)), [".ssh", "Documents"])
            self.assertEqual(doctor.private_host_paths(Path(tmp) / "missing"), [])

    def test_a_path_under_users_is_private_only_if_it_is_a_private_folder(self):
        from agentctl import doctor
        self.assertEqual(doctor.private_host_paths(Path("/nonexistent")), [])


class Recorder:
    """Stands in for the gh CLI: records calls, can be told to fail some."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], fail

    def __call__(self, *args, check=True, token=None):
        self.calls.append(args)
        if any(args[:len(f)] == f for f in self.fail):
            raise subprocess.CalledProcessError(1, "gh", stderr="boom")
        return ""


class DispatchTests(unittest.TestCase):
    CONTEXT = {"issues": {"001": 2}, "sprint_issue": 1, "sprint": "001", "specs": {}, "prs": {"001": 7},
               "shas": {"001": "abc"}, "assignees": {"001": "alice"}, "default_branch": "main", "repo": "o/r"}

    def setUp(self):
        self.saved_env, self.saved_gh = dict(os.environ), github.gh
        for name in ("GITHUB_ACTIONS", "CONDUCTOR_SECRETS", "CONDUCTOR_LOCAL_DEVELOPER", "AGENTCTL_TRUSTED_SCRIPTS"):
            os.environ.pop(name, None)

    def tearDown(self):
        github.gh = self.saved_gh
        os.environ.clear()
        os.environ.update(self.saved_env)

    def run_actions(self, roles, action, fail=()):
        from agentctl.reconcile import Action
        github.gh = Recorder(fail)
        failures = github.execute([Action("dispatch", story="001", **action)], self.CONTEXT, roles)
        return failures, github.gh.calls

    def test_the_marker_is_written_before_the_work_is_sent_and_carries_the_commit(self):
        os.environ["DISPATCH_TOKEN_ALICE"] = "t"
        roles = {"harness": {"codex": {"via": "comment"}}}
        failures, calls = self.run_actions(roles, dict(stage="impl", harness="codex", attempt=1))
        self.assertEqual(failures, 0)
        comments = [c for c in calls if c[:2] == ("issue", "comment")]
        self.assertIn("<!-- conductor ", comments[0][4])
        self.assertIn('"sha": "abc"', comments[0][4])
        self.assertTrue(comments[1][4].startswith("@codex "))
        self.assertEqual(comments[1][2], "7")  # sent to the pull request the conductor already knows
        self.assertIn(("issue", "edit", "2", "--remove-label", "done:impl"), calls)

    def test_a_failed_send_withdraws_its_marker(self):
        roles = {"harness": {"claude": {"via": "workflow"}}}
        failures, calls = self.run_actions(roles, dict(stage="impl", harness="claude", attempt=1),
                                           fail=[("workflow", "run")])
        self.assertEqual(failures, 1)
        bodies = [c[4] for c in calls if c[:2] == ("issue", "comment")]
        marker_id = json.loads(github.MARKER_RE.findall(bodies[0])[0])["id"]
        self.assertEqual(json.loads(github.MARKER_RE.findall(bodies[1])[0]), {"cancel": marker_id})
        self.assertEqual(github.read_markers(bodies), [])  # so the next pass plans it again

    def test_a_stage_that_has_to_wait_leaves_nothing_behind(self):
        roles = {"harness": {"ollama": {"via": "sbx"}}}
        os.environ["GITHUB_ACTIONS"] = "true"
        failures, calls = self.run_actions(roles, dict(stage="impl", harness="ollama", attempt=1))
        self.assertEqual((failures, calls), (0, []))
        # On another developer's Mac it waits too, whatever the route: that conductor
        # only holds its own developer's credentials.
        del os.environ["GITHUB_ACTIONS"]
        os.environ.update(CONDUCTOR_LOCAL_DEVELOPER="bob", AGENTCTL_TRUSTED_SCRIPTS="/x", DISPATCH_TOKEN="bobs")
        failures, calls = self.run_actions(roles, dict(stage="impl", harness="ollama", attempt=1))
        self.assertEqual((failures, calls), (0, []))
        failures, calls = self.run_actions({"harness": {"codex": {"via": "comment"}}}, dict(stage="impl", harness="codex", attempt=1))
        self.assertEqual((failures, calls), (0, []))

    def test_a_review_is_asked_for_one_commit(self):
        roles = {"harness": {"claude": {"via": "http", "review_workflow": "agent-review.yml"}}}
        failures, calls = self.run_actions(roles, dict(stage="review", harness="claude", attempt=1))
        self.assertEqual(failures, 0)
        run = next(c for c in calls if c[:2] == ("workflow", "run"))
        self.assertIn("sha=abc", run)

    def test_auto_merge_is_tied_to_the_commit_and_can_be_withdrawn(self):
        from agentctl.reconcile import Action
        github.gh = Recorder()
        context = dict(self.CONTEXT, pr_shas={"7": "abc", "12": "def"})
        actions = [Action("enable-auto-merge", story="001"), Action("enable-auto-merge", reason="#12"),
                   Action("enable-auto-merge", reason="#99"), Action("disable-auto-merge", reason="#12")]
        self.assertEqual(github.execute(actions, context, {}), 0)
        self.assertEqual(github.gh.calls, [
            ("pr", "merge", "7", "--auto", "--squash", "--match-head-commit", "abc"),
            ("pr", "merge", "12", "--auto", "--squash", "--match-head-commit", "def"),
            ("pr", "merge", "12", "--disable-auto")])

    def test_a_run_limited_to_other_developers_and_stopped_when_the_lease_moves(self):
        from agentctl.reconcile import Action
        github.gh = Recorder()
        os.environ["DISPATCH_TOKEN_ALICE"] = "t"
        roles = {"harness": {"codex": {"via": "comment"}}}
        actions = [Action("mark-ready", story="001"), Action("dispatch", story="001", stage="impl", harness="codex", attempt=1)]
        only = lambda action, context: action.kind == "dispatch"  # noqa: E731
        self.assertEqual(github.execute(actions, self.CONTEXT, roles, only=only, guard=lambda: False), 0)
        self.assertEqual(github.gh.calls, [])
        self.assertEqual(github.execute(actions, self.CONTEXT, roles, only=only, guard=lambda: True), 0)
        self.assertNotIn(("pr", "ready", "7"), github.gh.calls)
        self.assertTrue(any(c[:2] == ("issue", "comment") for c in github.gh.calls))

    def test_missing_credentials_fail_before_anything_is_written(self):
        roles = {"harness": {"claude": {"via": "http"}, "codex": {"via": "comment"}}}
        for harness in ("claude", "codex"):
            failures, calls = self.run_actions(roles, dict(stage="impl", harness=harness, attempt=1))
            self.assertEqual((failures, calls), (1, []), harness)

    def test_bad_names_never_reach_a_shell_or_a_path(self):
        roles = {"harness": {"x": {"via": "workflow"}}}
        failures, calls = self.run_actions(roles, dict(stage="impl; rm -rf /", harness="x", attempt=1))
        self.assertEqual((failures, calls), (1, []))


class ObservationTests(unittest.TestCase):
    def test_only_trusted_authors_markers_count(self):
        issue = {"comments": [
            {"author": {"login": "conductor[bot]"}, "body": '<!-- conductor {"id":"a","stage":"impl","at":1} -->'},
            {"author": {"login": "alice-agent[bot]"}, "body": '<!-- conductor {"id":"b","stage":"review","at":2} -->'},
            {"author": {"login": "alice-agent[bot]"}, "body": '<!-- conductor {"cancel":"a"} -->'},
        ]}
        bodies = github._comments_by(issue, {"conductor[bot]", "alice"})
        self.assertEqual([m["stage"] for m in github.read_markers(bodies)], ["impl"])

    def test_the_storys_pull_request_is_open_same_repo_and_into_the_default_branch(self):
        def pr(number, state, head="story/012-x", base="main", cross=False):
            return {"number": number, "state": state, "headRefName": head, "baseRefName": base, "isCrossRepository": cross}
        prs = [pr(5, "MERGED"), pr(9, "CLOSED"), pr(8, "OPEN", base="other"), pr(7, "OPEN", cross=True),
               pr(6, "OPEN"), pr(4, "OPEN", head="story/0123-x"), pr(3, "OPEN", head="story/013-y")]
        self.assertEqual(github.select_pr(prs, "012", "main")["number"], 6)
        self.assertEqual(github.select_pr([p for p in prs if p["number"] != 6], "012", "main")["number"], 5)
        self.assertIsNone(github.select_pr([pr(9, "CLOSED")], "012", "main"))

    def test_only_human_approved_spec_and_sprint_pull_requests_merge_by_themselves(self):
        def pr(number, head, decision, **kw):
            return dict({"number": number, "state": "OPEN", "headRefName": head, "baseRefName": "main",
                         "isCrossRepository": False, "reviewDecision": decision, "autoMergeRequest": None}, **kw)
        prs = [pr(1, "spec/014-x", "APPROVED"), pr(2, "sprint/002", "REVIEW_REQUIRED"),
               pr(3, "chore/docs", "APPROVED"),          # chores are merged by a person
               pr(4, "chore/typo", None),                 # nobody had to review it: never auto-merged
               pr(5, "spec/015-y", "APPROVED", baseRefName="other"),
               pr(6, "spec/016-z", "APPROVED", autoMergeRequest={"x": 1}),
               pr(7, "story/001-a", "APPROVED")]
        self.assertEqual(github.approved_decision_prs(prs, "main"), [1])

    def test_branches_without_a_pull_request_for_their_tip(self):
        def pr(head, oid, state, base="main"):
            return {"headRefName": head, "headRefOid": oid, "state": state, "baseRefName": base, "isCrossRepository": False}
        prs = [pr("story/001-a", "old", "MERGED"), pr("spec/002-b", "s2", "OPEN")]
        branches = [("main", "m"), ("story/001-a", "new"), ("spec/002-b", "s3"), ("chore/x", "c"),
                    ("feature/y", "f"), ("story/bad name;rm", "z")]
        # 001 has new commits after its merged PR; the spec's PR is still open; feature/* is not ours.
        self.assertEqual(github.unopened_branches(branches, prs, "main"), ["chore/x", "story/001-a"])
        # A pull request into some other base does not stand in for the real one.
        decoy = [pr("story/001-a", "new", "OPEN", base="elsewhere")]
        self.assertEqual(github.unopened_branches([("story/001-a", "new")], decoy, "main"), ["story/001-a"])
        # Only the branch the spec names is a story's branch.
        self.assertEqual(github.unopened_branches([("story/001-a", "n"), ("story/001-decoy", "d")], [], "main",
                                                  {"story/001-a"}), ["story/001-a"])

    def test_a_second_branch_with_the_same_story_number_is_not_the_storys_pull_request(self):
        def pr(number, head):
            return {"number": number, "state": "OPEN", "headRefName": head, "baseRefName": "main", "isCrossRepository": False}
        prs = [pr(5, "story/012-upload"), pr(9, "story/012-decoy")]
        self.assertEqual(github.select_pr(prs, "012", "main", "story/012-upload")["number"], 5)

    def test_the_tier_comes_from_commit_statuses_and_the_strictest_wins(self):
        self.assertEqual(github.tier_of({"risk-tier/T0": "success", "ci": "success"}), "T0")
        self.assertEqual(github.tier_of({"risk-tier/T0": "success", "risk-tier/T1": "success"}), "T1")
        self.assertEqual(github.tier_of({"risk-tier/T0": "pending"}), "T2")
        self.assertEqual(github.tier_of({"risk-tier/T9": "success"}), "T2")
        self.assertEqual(github.tier_of({}), "T2")

    def test_a_variable_that_cannot_be_read_is_not_an_unset_variable(self):
        saved = github.gh

        def missing(*args, **kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="gh: Not Found (HTTP 404)")

        def broken(*args, **kw):
            raise subprocess.CalledProcessError(1, "gh", stderr="error connecting to api.github.com")
        try:
            github.gh = missing
            self.assertEqual(github.variable("CONDUCTOR_PAUSED"), "")
            github.gh = broken
            with self.assertRaises(github.Unreadable):
                github.variable("CONDUCTOR_PAUSED")
        finally:
            github.gh = saved


class StageProfileTests(unittest.TestCase):
    def test_only_stages_that_deliver_code_or_specs_can_push(self):
        from agentctl import profiles
        # Nobody but the conductor can both push and act on pull requests.
        for name, perms in profiles.TOKEN_PERMISSIONS.items():
            self.assertFalse(perms["contents"] == "write" and perms["pull_requests"] == "write", name)
        can_push = {s for s in profiles.STAGE_PROFILES if profiles.for_stage(s)["token"] == "write"}
        self.assertEqual(can_push, {"design", "tests", "impl", "fix", "resolve-conflict", "fix-main", "product-owner", "planner"})
        for stage in ("review", "triage"):
            self.assertEqual(profiles.for_stage(stage)["token"], "read")
        self.assertEqual(profiles.TOKEN_PERMISSIONS["read"]["contents"], "read")

    def test_only_building_stages_reach_package_registries(self):
        from agentctl import profiles
        build = {s for s in profiles.STAGE_PROFILES if profiles.for_stage(s)["network"] == "build"}
        self.assertEqual(build, {"design", "tests", "impl", "fix", "resolve-conflict", "fix-main"})

    def test_spec_writers_get_spec_settings_and_everyone_else_story_settings(self):
        from agentctl import profiles
        self.assertEqual({s for s in profiles.STAGE_PROFILES if profiles.for_stage(s)["settings"] == "spec"},
                         {"product-owner", "planner"})
        story = json.loads((ROOT / "sandbox/story-agent.claude-settings.json").read_text())["permissions"]["deny"]
        spec = json.loads((ROOT / "sandbox/spec-agent.claude-settings.json").read_text())["permissions"]["deny"]
        self.assertIn("Edit(docs/specs/**)", story)
        self.assertNotIn("Edit(docs/specs/**)", spec)
        self.assertIn("Edit(policy/**)", spec)  # guardrails stay off limits for both

    def test_an_unknown_stage_gets_the_least(self):
        from agentctl import profiles
        self.assertEqual(profiles.for_stage("something-new"), {"token": "read", "network": "base", "settings": "story"})

    def test_token_request_is_limited_to_one_repository_and_the_profile(self):
        from agentctl import profiles
        body = apptoken.request_body("acme/app", profiles.TOKEN_PERMISSIONS["read"])
        self.assertEqual(body, {"repositories": ["app"], "permissions": {"contents": "read", "pull_requests": "write", "issues": "write"}})
        self.assertEqual(profiles.TOKEN_PERMISSIONS["write"]["pull_requests"], "read")
        self.assertNotEqual(apptoken.cache_path("read"), apptoken.cache_path("write"))

    def test_registries_are_not_in_the_base_allowlist(self):
        base = (ROOT / "sandbox/allowlist.txt").read_text()
        build = (ROOT / "sandbox/allowlist-build.txt").read_text()
        self.assertNotIn("registry.npmjs.org", base)
        self.assertIn("registry.npmjs.org", build)
        self.assertIn("github.com", base)
