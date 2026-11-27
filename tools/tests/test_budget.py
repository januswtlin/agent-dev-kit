import json
import os
import tempfile
import unittest
from pathlib import Path

from agentctl import budget, docs, local

CFG = budget.settings(None)
NOV = 1795000000.0  # 2026-11-18T...Z
assert budget.month_of(NOV) == "2026-11"


def job(start, end, labels=("ubuntu-latest",), conclusion="success"):
    return {"started_at": start, "completed_at": end, "labels": list(labels), "conclusion": conclusion}


class CostTests(unittest.TestCase):
    def test_every_job_is_rounded_up_to_a_whole_minute(self):
        self.assertAlmostEqual(budget.job_cost(job("2026-11-02T00:00:00Z", "2026-11-02T00:00:05Z"), CFG), 0.006)
        self.assertAlmostEqual(budget.job_cost(job("2026-11-02T00:00:00Z", "2026-11-02T00:01:01Z"), CFG), 0.012)

    def test_price_depends_on_the_runner(self):
        span = ("2026-11-02T00:00:00Z", "2026-11-02T00:03:00Z")
        self.assertAlmostEqual(budget.job_cost(job(*span, labels=["ubuntu-slim"]), CFG), 0.006)
        self.assertAlmostEqual(budget.job_cost(job(*span, labels=["ubuntu-24.04-arm"]), CFG), 0.015)
        self.assertEqual(budget.job_cost(job(*span, labels=["self-hosted", "agent-sandbox"]), CFG), 0.0)

    def test_skipped_and_unfinished_jobs_are_free(self):
        self.assertEqual(budget.job_cost(job("2026-11-02T00:00:00Z", "2026-11-02T00:00:00Z", conclusion="skipped"), CFG), 0.0)
        self.assertEqual(budget.job_cost({"labels": ["ubuntu-latest"], "started_at": None, "completed_at": None}, CFG), 0.0)


class AccumulateTests(unittest.TestCase):
    def test_only_jobs_after_the_last_run_are_added(self):
        usage = {"month": "2026-11", "through": "2026-11-10T00:00:00Z", "usd": 1.0}
        jobs = [job("2026-11-09T00:00:00Z", "2026-11-09T00:10:00Z"), job("2026-11-11T00:00:00Z", "2026-11-11T00:10:00Z")]
        out = budget.accumulate(usage, jobs, NOV, CFG)
        self.assertAlmostEqual(out["usd"], 1.06)
        self.assertEqual(out["through"], "2026-11-11T00:10:00Z")
        self.assertEqual(budget.accumulate(out, jobs, NOV, CFG), out)  # running again adds nothing

    def test_a_new_month_starts_from_zero(self):
        usage = {"month": "2026-10", "through": "2026-10-31T00:00:00Z", "usd": 17.5}
        out = budget.accumulate(usage, [job("2026-10-31T23:00:00Z", "2026-10-31T23:30:00Z")], NOV, CFG)
        self.assertEqual(out, {"month": "2026-11", "through": "2026-11-01T00:00:00Z", "usd": 0.0})


class RunnerChoiceTests(unittest.TestCase):
    def test_overflow_at_the_threshold_and_back_on_a_new_month(self):
        hosted, _ = budget.choose_runner({"month": "2026-11", "usd": 15.0}, CFG)
        self.assertEqual(json.loads(hosted), "ubuntu-latest")
        configured = budget.settings({"actions": {"overflow_runner": ["self-hosted", "ci-ephemeral"]}})
        moved, reason = budget.choose_runner({"month": "2026-11", "usd": 15.3}, configured)
        self.assertEqual(json.loads(moved), ["self-hosted", "ci-ephemeral"])
        self.assertIn("85%", reason)

    def test_overflow_is_off_unless_a_runner_is_configured(self):
        stays, reason = budget.choose_runner({"month": "2026-11", "usd": 17.9}, CFG)
        self.assertEqual(json.loads(stays), "ubuntu-latest")
        self.assertIn("no overflow runner is configured", reason)
        back, _ = budget.choose_runner(budget.accumulate({"month": "2026-10", "through": "x", "usd": 18}, [], NOV, CFG), CFG)
        self.assertEqual(json.loads(back), "ubuntu-latest")

    def test_policy_overrides_defaults(self):
        cfg = budget.settings({"actions": {"monthly_allowance_usd": 12, "price_per_minute": {"standard": 0.01}}})
        self.assertEqual(cfg["monthly_allowance_usd"], 12)
        self.assertEqual(cfg["price_per_minute"], {"standard": 0.01, "light": 0.002, "arm": 0.005})


class LocalTests(unittest.TestCase):
    def test_only_one_conductor_per_project_on_a_mac(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            subprocess.run(["git", "-C", tmp, "remote", "add", "origin", "https://github.com/o/r.git"], check=True)
            saved = os.environ.get("XDG_STATE_HOME")
            os.environ["XDG_STATE_HOME"] = str(Path(tmp) / "state")
            try:
                first = local.single_instance(Path(tmp))
                with self.assertRaises(SystemExit):
                    local.single_instance(Path(tmp))
                first.close()
                local.single_instance(Path(tmp)).close()  # free again once the first one ends
            finally:
                if saved is None:
                    os.environ.pop("XDG_STATE_HOME", None)
                else:
                    os.environ["XDG_STATE_HOME"] = saved

    def test_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.conductor"
            path.write_text('# comment\nCLAUDE_TRIGGER_URL="https://x"\nBAD LINE\nA=b=c\n', encoding="utf-8")
            self.assertEqual(local.load_env_file(path), {"CLAUDE_TRIGGER_URL": "https://x", "A": "b=c"})
            self.assertEqual(local.load_env_file(Path(tmp) / "none"), {})


class DocsLintTests(unittest.TestCase):
    def make(self, files: dict[str, str]) -> str:
        tmp = tempfile.mkdtemp()
        for rel in docs.REQUIRED:
            files.setdefault(rel, "# T\n")
            files.setdefault(rel[:-3] + "-zh-TW.md", "# T\n")
        for rel, text in files.items():
            if text is None:
                continue
            path = Path(tmp) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return tmp

    def test_clean(self):
        self.assertEqual(docs.lint(self.make({})), [])

    def test_missing_translation_orphan_translation_and_structure_drift(self):
        root = self.make({
            "docs/operations-zh-TW.md": None,
            "docs/extra-zh-TW.md": "# only zh\n",
            "docs/guideline.md": "# A\n## B\n```\n# not a heading\n```\n## C\n",
            "docs/guideline-zh-TW.md": "# A\n## B\n",
        })
        problems = "\n".join(docs.lint(root))
        self.assertIn("docs/operations.md: no operations-zh-TW.md", problems)
        self.assertIn("docs/extra-zh-TW.md: no English source", problems)
        self.assertIn("different heading structure (3 vs 2 headings)", problems)


if __name__ == "__main__":
    unittest.main()
