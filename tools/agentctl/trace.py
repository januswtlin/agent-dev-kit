"""Traceability: every approved test case must map to a test that actually ran and passed.

The evidence is the test runner's JUnit XML, not a search of the source tree.
A test carries its TC id in its name, class name or file name. Because many
languages forbid '-' in identifiers, `TC-012-03`, `tc_012_03` and `TC01203`
are all accepted.
"""

from __future__ import annotations

import glob
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .specs import Spec

TC_IN_TEST_RE = re.compile(r"(?<![A-Za-z0-9])TC[-_ ]?(\d{3})[-_ ]?(\d{2})(?!\d)", re.IGNORECASE)


@dataclass
class TcResult:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.failed:
            return "failed"
        if self.passed:
            return "passed"
        if self.skipped:
            return "skipped"
        return "missing"

    @property
    def ok(self) -> bool:
        return self.status == "passed"


def parse_junit(patterns: list[str]) -> dict[str, TcResult]:
    """Collect per-TC results from JUnit XML files matching the glob patterns."""
    results: dict[str, TcResult] = {}
    files: list[str] = []
    for pattern in patterns:
        files.extend(sorted(glob.glob(pattern, recursive=True)))
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for case in root.iter("testcase"):
            label = " ".join(filter(None, [case.get("classname"), case.get("name"), case.get("file")]))
            ids = {f"TC-{m.group(1)}-{m.group(2)}" for m in TC_IN_TEST_RE.finditer(label)}
            if not ids:
                continue
            name = "::".join(filter(None, [case.get("classname"), case.get("name")]))
            children = {child.tag for child in case}
            for tc_id in ids:
                result = results.setdefault(tc_id, TcResult())
                if children & {"failure", "error"}:
                    result.failed.append(name)
                elif "skipped" in children:
                    result.skipped.append(name)
                else:
                    result.passed.append(name)
    return results


def check(
    specs: dict[str, Spec],
    head: dict[str, TcResult],
    story: str | None = None,
    base: dict[str, TcResult] | None = None,
) -> list[str]:
    """Return a list of traceability violations (empty means the check passes).

    - The story under work must have every TC passing.
    - Any other story is all-or-nothing: once one of its TCs has a test, all must pass.
    - A TC that passed on the base branch must still pass (no silent deletion).
    - A TC id used in tests must exist in an approved spec.
    """
    problems: list[str] = []
    declared: set[str] = set()

    for spec in specs.values():
        declared.update(spec.tc_ids)
        started = any(tc_id in head for tc_id in spec.tc_ids)
        if spec.id != story and not started:
            continue
        for tc_id in spec.tc_ids:
            status = head.get(tc_id, TcResult()).status
            if status != "passed":
                problems.append(f"{tc_id}: {status} (story {spec.id})")

    if base:
        for tc_id, result in sorted(base.items()):
            if result.ok and tc_id in declared and not head.get(tc_id, TcResult()).ok:
                message = f"{tc_id}: passed on base but is {head.get(tc_id, TcResult()).status} now"
                if not any(p.startswith(f"{tc_id}:") for p in problems):
                    problems.append(message)

    for tc_id in sorted(set(head) - declared):
        problems.append(f"{tc_id}: used in tests but not declared in any approved spec")
    return problems


def evidence_markdown(spec: Spec, head: dict[str, TcResult]) -> str:
    """AC -> TC -> test -> result table, posted to the requirement issue on merge."""
    icon = {"passed": "✅", "failed": "❌", "skipped": "⚠️ skipped", "missing": "❌ missing"}
    lines = [
        f"### Evidence: story {spec.id} {spec.title}",
        "",
        "| AC | TC | Level | Test | Result |",
        "|---|---|---|---|---|",
    ]
    for ac_id, ac_text in spec.ac.items():
        for tc in [t for t in spec.tc if ac_id in t.ac]:
            result = head.get(tc.id, TcResult())
            tests = result.passed + result.failed + result.skipped
            shown = "<br>".join(f"`{t}`" for t in tests[:3]) or "none"
            lines.append(f"| {ac_id} {ac_text} | {tc.id} {tc.text} | {tc.level} | {shown} | {icon[result.status]} |")
    manual = [d for d in spec.done_when if d.get("check", "manual") == "manual"]
    if manual:
        lines += ["", "**Manual done-when items (confirm at release):**"]
        lines += [f"- [ ] {d.get('text', '')}" for d in manual]
    return "\n".join(lines) + "\n"
