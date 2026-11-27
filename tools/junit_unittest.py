#!/usr/bin/env python3
"""Run Python's unittest over a directory and write the results as JUnit XML.

The default `make test` of the template, so that a new project has a test
runner that produces what the gates read (reports/junit/*.xml) before it has
chosen a stack. Standard library only. Replace it in the Makefile when the
project has its own runner.

    python3 tools/junit_unittest.py TEST_DIR OUTPUT.xml

Exits 1 when a test failed or could not be loaded, 0 otherwise, also when
TEST_DIR does not exist yet (the report is then empty).
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from xml.sax.saxutils import escape, quoteattr


class Recording(unittest.TestResult):
    def __init__(self) -> None:
        super().__init__()
        self.cases: list[tuple[str, str, str, float]] = []
        self._started = time.time()

    def startTest(self, test) -> None:
        super().startTest(test)
        self._started = time.time()

    def _add(self, test, kind: str, text: str = "") -> None:
        self.cases.append((test.id(), kind, text, time.time() - self._started))

    def addSuccess(self, test) -> None:
        super().addSuccess(test)
        self._add(test, "passed")

    def addFailure(self, test, err) -> None:
        super().addFailure(test, err)
        self._add(test, "failure", self._exc_info_to_string(err, test))

    def addError(self, test, err) -> None:
        # Also a module that cannot be imported and a failing setUpClass.
        super().addError(test, err)
        self._add(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason) -> None:
        super().addSkip(test, reason)
        self._add(test, "skipped", str(reason))

    def addExpectedFailure(self, test, err) -> None:
        # The assertion failed. unittest calls that a success; for the gates it is
        # not a test that passed, so it is reported as skipped and counts for nothing.
        super().addExpectedFailure(test, err)
        self._add(test, "skipped", "expected failure: the assertion did not hold")

    def addUnexpectedSuccess(self, test) -> None:
        super().addUnexpectedSuccess(test)
        self._add(test, "failure", "unexpected success")


def to_xml(cases: list[tuple[str, str, str, float]]) -> str:
    def count(kind: str) -> int:
        return sum(1 for case in cases if case[1] == kind)

    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             f'<testsuites><testsuite name="unittest" tests="{len(cases)}" failures="{count("failure")}" '
             f'errors="{count("error")}" skipped="{count("skipped")}">']
    for test_id, kind, text, seconds in cases:
        classname, _, name = test_id.rpartition(".")
        head = f'<testcase classname={quoteattr(classname)} name={quoteattr(name)} time="{seconds:.3f}"'
        if kind == "passed":
            lines.append(head + "/>")
        else:
            lines.append(f"{head}><{kind}>{escape(text)}</{kind}></testcase>")
    lines.append("</testsuite></testsuites>")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    start, out = argv[1], argv[2]
    result = Recording()
    if os.path.isdir(start):
        sys.path.insert(0, os.getcwd())  # tests import the project's code from the repository root
        unittest.defaultTestLoader.discover(start).run(result)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(to_xml(result.cases))
    bad = sum(1 for case in result.cases if case[1] in ("failure", "error"))
    print(f"unittest: {len(result.cases)} test(s), {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
