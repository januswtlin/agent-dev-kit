import tempfile
import unittest
from pathlib import Path

from agentctl import redgreen, specs, trace

ROOT = Path(__file__).resolve().parents[2]


def junit(cases: list[tuple[str, str]]) -> str:
    """cases: (test name, outcome) where outcome is pass | fail | error | skip."""
    body = []
    for name, outcome in cases:
        child = {"pass": "", "fail": "<failure/>", "error": "<error/>", "skip": "<skipped/>"}[outcome]
        body.append(f'<testcase classname="tests.test_proof" name="{name}">{child}</testcase>')
    return "<testsuites><testsuite>" + "".join(body) + "</testsuite></testsuites>"


def results(cases):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.xml"
        path.write_text(junit(cases), encoding="utf-8")
        return trace.parse_junit([str(path)])


ALL_PASS = [(f"test_tc_000_0{i}_something", "pass") for i in range(1, 7)]


class ParseTests(unittest.TestCase):
    def test_accepts_identifier_friendly_spellings(self):
        got = results([("test_TC_000_01_upload", "pass"), ("TC-000-02 rejects pdf", "pass"), ("tc00003", "pass")])
        self.assertEqual(set(got), {"TC-000-01", "TC-000-02", "TC-000-03"})

    def test_does_not_match_inside_other_words_or_longer_numbers(self):
        self.assertEqual(results([("test_etc_000_01", "pass"), ("test_tc_000_012", "pass")]), {})

    def test_failed_beats_passed_for_the_same_tc(self):
        got = results([("test_tc_000_01_a", "pass"), ("test_tc_000_01_b", "fail")])
        self.assertEqual(got["TC-000-01"].status, "failed")


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.specs = specs.load_all(ROOT / "docs/specs")

    def test_all_passing_is_ok(self):
        self.assertEqual(trace.check(self.specs, results(ALL_PASS), story="000"), [])

    def test_missing_test_is_reported(self):
        problems = trace.check(self.specs, results(ALL_PASS[:-1]), story="000")
        self.assertEqual(problems, ["TC-000-06: missing (story 000)"])

    def test_skipped_test_does_not_count(self):
        cases = ALL_PASS[:-1] + [("test_tc_000_06_x", "skip")]
        self.assertEqual(trace.check(self.specs, results(cases), story="000"), ["TC-000-06: skipped (story 000)"])

    def test_failed_and_errored_tests_do_not_count(self):
        cases = ALL_PASS[:-2] + [("test_tc_000_05_x", "fail"), ("test_tc_000_06_x", "error")]
        problems = trace.check(self.specs, results(cases), story="000")
        self.assertEqual(len(problems), 2)

    def test_story_not_started_is_ignored_when_working_on_another(self):
        self.assertEqual(trace.check(self.specs, {}, story=None), [])

    def test_partially_implemented_story_fails_even_on_other_branches(self):
        problems = trace.check(self.specs, results(ALL_PASS[:2]), story=None)
        self.assertEqual(len(problems), 4)

    def test_undeclared_tc_id_is_reported(self):
        problems = trace.check(self.specs, results(ALL_PASS + [("test_tc_000_99_extra", "pass")]), story="000")
        self.assertEqual(problems, ["TC-000-99: used in tests but not declared in any approved spec"])

    def test_deleting_every_test_of_a_finished_story_is_caught_by_base_comparison(self):
        problems = trace.check(self.specs, {}, story=None, base=results(ALL_PASS))
        self.assertEqual(len(problems), 6)
        self.assertIn("passed on base but is missing now", problems[0])

    def test_deleting_a_spec_together_with_its_tests_is_still_caught(self):
        without_spec = {k: v for k, v in self.specs.items() if k != "000"}
        problems = trace.check(without_spec, {}, story=None, base=results(ALL_PASS))
        self.assertEqual(len(problems), 6)

    def test_a_human_can_retire_test_cases(self):
        retired = {f"TC-000-0{i}" for i in range(1, 7)}
        self.assertEqual(trace.check({}, {}, story=None, base=results(ALL_PASS), retired=retired), [])

    def test_evidence_table_lists_every_tc(self):
        table = trace.evidence_markdown(self.specs["000"], results(ALL_PASS))
        for tc_id in self.specs["000"].tc_ids:
            self.assertIn(tc_id, table)
        self.assertIn("Manual done-when", table)


class RedGreenTests(unittest.TestCase):
    def setUp(self):
        self.spec = specs.load_all(ROOT / "docs/specs")["000"]

    def test_red_on_base_green_on_head_passes(self):
        base = results([(name, "fail") for name, _ in ALL_PASS])
        self.assertEqual(redgreen.check(self.spec, base, results(ALL_PASS)), [])

    def test_missing_on_base_counts_as_red(self):
        self.assertEqual(redgreen.check(self.spec, {}, results(ALL_PASS)), [])

    def test_vacuous_test_that_passes_on_base_is_rejected(self):
        base = results([("test_tc_000_03_always_true", "pass")])
        problems = redgreen.check(self.spec, base, results(ALL_PASS))
        self.assertEqual(len(problems), 1)
        self.assertIn("TC-000-03: passes on base", problems[0])

    def test_a_base_run_with_no_report_proves_nothing(self):
        problems = redgreen.check(self.spec, {}, results(ALL_PASS), base_report_count=0)
        self.assertEqual(len(problems), 1)
        self.assertIn("produced no report at all", problems[0])
        # With a report, a test missing from it (its file could not be imported) is red.
        self.assertEqual(redgreen.check(self.spec, {}, results(ALL_PASS), base_report_count=1), [])

    def test_a_failed_setup_on_base_shows_nothing(self):
        problems = redgreen.check(self.spec, {}, results(ALL_PASS), base_report_count=1, base_red_count=3, setup_exit=2)
        self.assertEqual(len(problems), 1)
        self.assertIn("setup command exited 2", problems[0])

    def test_missing_from_a_base_report_in_which_nothing_failed_is_not_red(self):
        problems = redgreen.check(self.spec, {}, results(ALL_PASS), base_report_count=1, base_red_count=0)
        self.assertTrue(problems and all("did not run on base" in p for p in problems))
        self.assertEqual(redgreen.check(self.spec, {}, results(ALL_PASS), base_report_count=1, base_red_count=1), [])

    def test_skipped_on_base_is_not_red(self):
        base = results([("test_tc_000_02_x", "skip")])
        problems = redgreen.check(self.spec, base, results(ALL_PASS), base_report_count=1)
        self.assertEqual(problems, ["TC-000-02: was skipped on base, which does not show that it fails there"])

    def test_not_green_on_head_is_rejected(self):
        problems = redgreen.check(self.spec, {}, results(ALL_PASS[:-1]))
        self.assertEqual(problems, ["TC-000-06: not green on head (missing)"])


class SpecLintTests(unittest.TestCase):
    def test_example_spec_is_clean(self):
        self.assertEqual(specs.lint(ROOT / "docs/specs"), [])

    def write(self, root: Path, sid: str, toml: str, story: str):
        folder = root / f"{sid}-x"
        folder.mkdir(parents=True)
        (folder / "spec.toml").write_text(toml, encoding="utf-8")
        (folder / "story.md").write_text(story, encoding="utf-8")

    def test_reports_uncovered_ac_unknown_refs_and_mismatch_with_story(self):
        toml = '''
id = "001"
touches = ["x"]
[[ac]]
id = "AC-001-1"
[[ac]]
id = "AC-001-2"
[[tc]]
id = "TC-001-01"
ac = ["AC-001-1", "AC-001-9"]
level = "unit"
'''
        with tempfile.TemporaryDirectory() as tmp:
            self.write(Path(tmp), "001", toml, "AC-001-1 TC-001-01 TC-001-02")
            problems = "\n".join(specs.lint(tmp))
        self.assertIn("TC-001-01 references unknown AC-001-9", problems)
        self.assertIn("AC-001-2 has no test case", problems)
        self.assertIn("AC-001-2 is in spec.toml but not in story.md", problems)
        self.assertIn("TC-001-02 is in story.md but not in spec.toml", problems)

    GOOD = 'id = "001"\ntouches = ["x"]\n[[ac]]\nid = "AC-001-1"\n[[tc]]\nid = "TC-001-01"\nac = ["AC-001-1"]\nlevel = "unit"\n'

    def bilingual(self, en: str, zh: str | None, changed=None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            self.write(Path(tmp), "001", self.GOOD, en)
            if zh is not None:
                (Path(tmp) / "001-x" / "story-zh-TW.md").write_text(zh, encoding="utf-8")
            return "\n".join(specs.lint(tmp, changed))

    def test_both_language_versions_must_exist_and_match_in_shape(self):
        en = "# S\n## AC\nAC-001-1\n## TC\nTC-001-01\n"
        self.assertEqual(self.bilingual(en, "# 故事\n## 驗收\nAC-001-1\n## 測試\nTC-001-01\n"), "")
        self.assertIn("story-zh-TW.md is missing", self.bilingual(en, None))
        self.assertIn("do not list the same AC/TC ids", self.bilingual(en, "# 故事\n## 驗收\nAC-001-1\n## 測試\n"))
        self.assertIn("do not list the same AC/TC ids", self.bilingual(en, "# 故事\n## 驗收\nTC-001-01\n## 測試\nAC-001-1\n"))
        self.assertIn("different sections", self.bilingual(en, "# 故事\n## 驗收\nAC-001-1 TC-001-01\n"))

    def test_a_story_changed_in_one_language_only_is_reported(self):
        en = "# S\nAC-001-1 TC-001-01\n"
        zh = "# 故事\nAC-001-1 TC-001-01\n"
        self.assertIn("story.md changed but story-zh-TW.md did not", self.bilingual(en, zh, {"docs/specs/001-x/story.md"}))
        self.assertIn("story-zh-TW.md changed but story.md did not", self.bilingual(en, zh, {"docs/specs/001-x/story-zh-TW.md"}))
        self.assertEqual(self.bilingual(en, zh, {"docs/specs/001-x/story.md", "docs/specs/001-x/story-zh-TW.md"}), "")
        self.assertEqual(self.bilingual(en, zh, {"src/app.py"}), "")

    def test_reports_dependency_cycle_and_unknown_dependency(self):
        def toml(sid, dep):
            return (f'id = "{sid}"\ntouches = ["x"]\ndepends_on = ["{dep}"]\n[[ac]]\nid = "AC-{sid}-1"\n'
                    f'[[tc]]\nid = "TC-{sid}-01"\nac = ["AC-{sid}-1"]\nlevel = "unit"\n')
        with tempfile.TemporaryDirectory() as tmp:
            self.write(Path(tmp), "001", toml("001", "002"), "AC-001-1 TC-001-01")
            self.write(Path(tmp), "002", toml("002", "001"), "AC-002-1 TC-002-01")
            self.write(Path(tmp), "003", toml("003", "777"), "AC-003-1 TC-003-01")
            problems = "\n".join(specs.lint(tmp))
        self.assertIn("dependency cycle: 001 -> 002 -> 001", problems)
        self.assertIn("spec 003: depends_on unknown story 777", problems)


if __name__ == "__main__":
    unittest.main()
