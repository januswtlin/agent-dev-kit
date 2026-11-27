import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentctl import trace

ROOT = Path(__file__).resolve().parents[2]


class JunitUnittestTests(unittest.TestCase):
    def run_suite(self, source: str):
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp, "tests")
            tests.mkdir()
            (tests / "__init__.py").write_text("")
            (tests / "test_sub.py").write_text(source)
            out = Path(tmp, "r.xml")
            run = subprocess.run([sys.executable, "-I", str(ROOT / "tools/run.py"), "junit-unittest", "tests", str(out)],
                                 cwd=tmp, capture_output=True, text=True)
            return run.returncode, trace.parse_junit([str(out)]), out.read_text()

    def test_a_failing_subtest_fails_the_run_and_is_reported(self):
        code, results, xml = self.run_suite(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_tc_000_01_sizes(self):\n"
            "        for n in (1, 2.5, 3):\n"
            "            with self.subTest(n=n):\n"
            "                self.assertEqual(n % 2, 1)\n")
        self.assertEqual(code, 1)
        self.assertEqual(results["TC-000-01"].status, "failed")
        self.assertIn("(n=2.5)", xml)

    def test_passing_subtests_still_pass(self):
        code, results, _ = self.run_suite(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_tc_000_01_ok(self):\n"
            "        for n in (1, 3):\n"
            "            with self.subTest(n=n):\n"
            "                self.assertEqual(n % 2, 1)\n")
        self.assertEqual(code, 0)
        self.assertEqual(results["TC-000-01"].status, "passed")


if __name__ == "__main__":
    unittest.main()
