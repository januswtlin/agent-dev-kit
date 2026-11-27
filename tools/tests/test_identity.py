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
        self.assertEqual(github.secret("DISPATCH_TOKEN", "bob"), "shared")
        self.assertEqual(github.secret("DISPATCH_TOKEN"), "shared")
        self.assertEqual(github.secret("MISSING", "bob"), "")

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

    def test_local_sandbox_stages_wait_when_the_conductor_is_on_actions(self):
        from agentctl.reconcile import Action
        saved = dict(os.environ)
        os.environ["GITHUB_ACTIONS"] = "true"
        try:
            roles = {"harness": {"ollama": {"via": "sbx"}}}
            context = {"issues": {"001": 2}, "sprint_issue": 1, "sprint": "001", "specs": {}, "prs": {}, "assignees": {}}
            action = Action("dispatch", story="001", stage="impl", harness="ollama", attempt=1)
            with self.assertRaises(github.Deferred):
                github._send(action, context, roles)
            # Deferred is not a failure: the run stays green and no marker is written.
            self.assertEqual(github.execute([action], context, roles), 0)
        finally:
            os.environ.clear()
            os.environ.update(saved)


class StageProfileTests(unittest.TestCase):
    def test_only_stages_that_deliver_code_or_specs_can_push(self):
        from agentctl import profiles
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
        self.assertNotEqual(apptoken.cache_path("read"), apptoken.cache_path("write"))

    def test_registries_are_not_in_the_base_allowlist(self):
        base = (ROOT / "sandbox/allowlist.txt").read_text()
        build = (ROOT / "sandbox/allowlist-build.txt").read_text()
        self.assertNotIn("registry.npmjs.org", base)
        self.assertIn("registry.npmjs.org", build)
        self.assertIn("github.com", base)
