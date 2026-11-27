import unittest
from pathlib import Path

from agentctl.globs import matches
from agentctl import config
from agentctl.risk import Change, assess

POLICY = config.load(Path(__file__).resolve().parent / "no-such-project")["risk"]


def tier(paths, has_story=True, lines=10):
    return assess([Change(p, lines, 0) for p in paths], POLICY, has_story)


class GlobTests(unittest.TestCase):
    def test_double_star_matches_any_depth(self):
        self.assertTrue(matches("a/b/auth/login.py", ["**/auth/**"]))
        self.assertTrue(matches("auth/login.py", ["**/auth/**"]))
        self.assertFalse(matches("a/authz/login.py", ["**/auth/**"]))

    def test_single_star_stays_in_one_segment(self):
        self.assertTrue(matches("docs/a.md", ["docs/*.md"]))
        self.assertFalse(matches("docs/x/a.md", ["docs/*.md"]))
        self.assertTrue(matches("README.md", ["**/*.md"]))


class RiskTests(unittest.TestCase):
    def test_docs_only_is_t0_even_without_story(self):
        self.assertEqual(tier(["docs/guideline.md", "README.md"], has_story=False).tier, "T0")

    def test_code_within_story_is_t1(self):
        self.assertEqual(tier(["src/orders/service.py", "tests/test_orders.py"]).tier, "T1")

    def test_tests_are_not_t0(self):
        self.assertEqual(tier(["tests/test_orders.py"]).tier, "T1")

    def test_code_without_story_is_t2(self):
        result = tier(["src/orders/service.py"], has_story=False)
        self.assertEqual(result.tier, "T2")
        self.assertIn("no approved story", result.reasons[0])

    def test_high_risk_path_is_t2(self):
        self.assertEqual(tier(["src/payments/transfer.py"]).tier, "T2")
        self.assertEqual(tier(["db/migrations/0002_add_proof.sql"]).tier, "T2")

    def test_guardrails_are_t2(self):
        for path in [".github/workflows/ci.yml", "agentdev.toml", "AGENTS.md", "CLAUDE.md", ".claude/settings.json"]:
            self.assertEqual(tier([path]).tier, "T2", path)

    def test_specs_are_human_gated(self):
        self.assertEqual(tier(["docs/specs/012-foo/story.md"]).tier, "T2")
        self.assertEqual(tier(["docs/sprints/003.toml"]).tier, "T2")

    def test_new_dependency_is_t2(self):
        result = tier(["web/package.json", "web/src/app.ts"])
        self.assertEqual(result.tier, "T2")
        self.assertTrue(any("dependency_manifests" in r for r in result.reasons))

    def test_large_diff_is_t2(self):
        self.assertEqual(tier(["src/a.py"], lines=601).tier, "T2")
        self.assertEqual(tier([f"src/f{i}.py" for i in range(41)], lines=1).tier, "T2")

    def test_lock_files_do_not_count_for_size_but_are_a_dependency_change(self):
        result = assess([Change("web/pnpm-lock.yaml", 5000, 4000), Change("src/a.py", 5, 0)], POLICY, True)
        self.assertEqual(result.tier, "T2")
        self.assertTrue(any("dependency_manifests" in r for r in result.reasons))
        self.assertFalse(any(r.startswith("size") for r in result.reasons))

    def test_a_lock_file_alone_is_t2(self):
        for path in ["package-lock.json", "api/uv.lock", "go.sum"]:
            self.assertEqual(tier([path]).tier, "T2", path)

    def test_scanner_configuration_is_a_guardrail(self):
        for path in [".gitleaks.toml", ".gitleaksignore", ".semgrepignore", ".gitattributes"]:
            self.assertEqual(tier([path]).tier, "T2", path)

    def test_one_risky_file_taints_the_whole_change(self):
        self.assertEqual(tier(["docs/a.md", "src/auth/session.py"]).tier, "T2")


if __name__ == "__main__":
    unittest.main()


class QuotedPathTests(unittest.TestCase):
    def test_a_path_git_would_quote_still_matches_the_policy(self):
        import os
        import subprocess
        import tempfile

        from agentctl import risk
        from agentctl.globs import matches

        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=tmp, check=True, capture_output=True, env=env)
            git("init", "-q", "-b", "main")
            git("commit", "-q", "--allow-empty", "-m", "base")
            os.makedirs(os.path.join(tmp, "auth"))
            with open(os.path.join(tmp, "auth", "caf\u00e9 login.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            git("add", "-A")
            git("commit", "-q", "-m", "change")
            changes = risk.changes_from_git("HEAD~1", "HEAD", cwd=tmp)
        self.assertEqual([c.path for c in changes], ["auth/caf\u00e9 login.py"])
        self.assertTrue(matches(changes[0].path, ["**/auth/**", "auth/**"]))
