"""Red-green check: a story's tests must fail on the base commit and pass on head.

This is what catches a vacuous test (`assert True`): it would pass on base,
before the behaviour exists. The PR's test files are overlaid on a clean
checkout of the base commit and the project's test command is run there.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .globs import matches
from .specs import Spec
from . import ids
from .trace import TcResult, parse_junit


def _git(args: list[str], cwd: str | Path) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, cwd=cwd).stdout


def test_files_to_overlay(repo: Path, base: str, spec: Spec, test_paths: list[str]) -> list[str]:
    """Files added or modified by the PR that are tests or mention this story's TC ids."""
    changed = _git(["diff", "--name-only", "-z", "--no-renames", "--diff-filter=AM", f"{base}...HEAD"], repo).split("\0")
    selected = []
    for path in filter(None, changed):
        if matches(path, test_paths):
            selected.append(path)
            continue
        try:
            text = (repo / path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(m.group(1) == spec.id for m in ids.TC_IN_TEST_RE.finditer(text + " " + path)):
            selected.append(path)
    return selected


def run_on_base(repo: Path, base: str, overlay: list[str], test_cmd: str, junit_glob: str,
                out_dir: Path | None = None, setup_cmd: str = "", info: dict | None = None) -> dict[str, TcResult]:
    """Check out `base` in a temporary worktree, overlay the test files, run the tests.

    With `out_dir`, the JUnit files produced on base are copied there.
    `setup_cmd` runs first in the worktree: without the project's dependencies
    every test would fail there for the wrong reason, and "it failed on base"
    would mean nothing. Its exit status is recorded in `info["setup_exit"]`.
    """
    tmp = Path(tempfile.mkdtemp(prefix="redgreen-"))
    worktree = tmp / "base"
    _git(["worktree", "add", "--detach", str(worktree), base], repo)
    try:
        for rel in overlay:
            target = worktree / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / rel, target)
        if setup_cmd:
            done = subprocess.run(setup_cmd, shell=True, cwd=worktree, capture_output=True, text=True)
            if info is not None:
                info["setup_exit"] = done.returncode
        # A non-zero exit is the expected outcome here, so it is not an error.
        subprocess.run(test_cmd, shell=True, cwd=worktree, capture_output=True, text=True)
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            for produced in sorted(worktree.glob(junit_glob)):
                shutil.copy2(produced, out_dir / produced.name)
        return parse_junit([str(worktree / junit_glob)])
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def check(spec: Spec, base_results: dict[str, TcResult], head_results: dict[str, TcResult],
          base_report_count: int | None = None, base_red_count: int | None = None,
          setup_exit: int | None = None) -> list[str]:
    """Each test case must be green on head and demonstrably red on base.

    "Red" has to be something the runner reported: a failure or an error. A test
    that was skipped on base proves nothing. A test missing from the base report
    is accepted only when the base run did produce a report (the usual case: the
    new test file could not even be imported, which the runner records). If the
    base run produced no report at all, nothing has been shown and the check fails.
    The same holds when the setup command failed there, and when a test case is
    missing from a base report in which nothing red belongs to the overlaid test
    files (`base_red_count` counts only those): then the story's tests simply did
    not run, whatever else failed.
    """
    problems = []
    if setup_exit not in (None, 0):
        return [f"the setup command exited {setup_exit} on base, so a failing test there shows nothing "
                "(does `make setup` work on a clean checkout of the base branch?)"]
    if base_report_count == 0:
        return ["the test run on base produced no report at all, so red-green cannot be established "
                "(do [tests] setup_cmd and test_cmd work on a clean checkout of the base branch?)"]
    for tc in spec.tc:
        head = head_results.get(tc.id, TcResult())
        if not head.ok:
            problems.append(f"{tc.id}: not green on head ({head.status})")
            continue
        if tc.red_exempt:
            continue
        base = base_results.get(tc.id, TcResult())
        if base.ok:
            problems.append(
                f"{tc.id}: passes on base without the implementation, so it does not verify the new behaviour"
            )
        elif base.status == "skipped":
            problems.append(f"{tc.id}: was skipped on base, which does not show that it fails there")
        elif base.status == "missing" and base_red_count == 0:
            problems.append(f"{tc.id}: is not in the base report and no failure there belongs to this story's "
                            "test files, so its test did not run on base")
    return problems
