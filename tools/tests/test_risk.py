import unittest
from pathlib import Path

from agentctl.globs import matches
from agentctl.risk import Change, assess, load_policy

POLICY = load_policy(Path(__file__).resolve().parents[2] / "policy/risk-tiers.toml")


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
        for path in [".github/workflows/ci.yml", "policy/risk-tiers.toml", "AGENTS.md", "tools/agentctl/risk.py",
                     ".claude/settings.json", "prompts/review.md"]:
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

    def test_lock_files_do_not_count_for_size(self):
        changes = [Change("web/pnpm-lock.yaml", 5000, 4000), Change("src/a.py", 5, 0)]
        self.assertEqual(assess(changes, POLICY, True).tier, "T1")

    def test_one_risky_file_taints_the_whole_change(self):
        self.assertEqual(tier(["docs/a.md", "src/auth/session.py"]).tier, "T2")


if __name__ == "__main__":
    unittest.main()
