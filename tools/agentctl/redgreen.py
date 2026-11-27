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
from .trace import TC_IN_TEST_RE, TcResult, parse_junit


def _git(args: list[str], cwd: str | Path) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, cwd=cwd).stdout


def test_files_to_overlay(repo: Path, base: str, spec: Spec, test_paths: list[str]) -> list[str]:
    """Files added or modified by the PR that are tests or mention this story's TC ids."""
    changed = _git(["diff", "--name-only", "--no-renames", "--diff-filter=AM", f"{base}...HEAD"], repo).split("\n")
    selected = []
    for path in filter(None, changed):
        if matches(path, test_paths):
            selected.append(path)
            continue
        try:
            text = (repo / path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(m.group(1) == spec.id for m in TC_IN_TEST_RE.finditer(text + " " + path)):
            selected.append(path)
    return selected


def run_on_base(repo: Path, base: str, overlay: list[str], test_cmd: str, junit_glob: str) -> dict[str, TcResult]:
    """Check out `base` in a temporary worktree, overlay the test files, run the tests."""
    tmp = Path(tempfile.mkdtemp(prefix="redgreen-"))
    worktree = tmp / "base"
    _git(["worktree", "add", "--detach", str(worktree), base], repo)
    try:
        for rel in overlay:
            target = worktree / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / rel, target)
        # A non-zero exit is the expected outcome here, so it is not an error.
        subprocess.run(test_cmd, shell=True, cwd=worktree, capture_output=True, text=True)
        return parse_junit([str(worktree / junit_glob)])
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def check(spec: Spec, base_results: dict[str, TcResult], head_results: dict[str, TcResult]) -> list[str]:
    problems = []
    for tc in spec.tc:
        head = head_results.get(tc.id, TcResult())
        if not head.ok:
            problems.append(f"{tc.id}: not green on head ({head.status})")
            continue
        if tc.red_exempt:
            continue
        if base_results.get(tc.id, TcResult()).ok:
            problems.append(
                f"{tc.id}: passes on base without the implementation, so it does not verify the new behaviour"
            )
    return problems
