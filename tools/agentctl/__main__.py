"""Command line entry point: python3 -m agentctl <command>."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from . import doctor, redgreen, risk, specs, trace


def _root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(out.stdout.strip()) if out.returncode == 0 else Path.cwd()


def _trusted_root() -> Path:
    """Where policy files are read from.

    In CI this points at a checkout of the base branch, so a pull request cannot
    loosen the policy that judges it. Locally it is the repository itself.
    """
    return Path(os.environ.get("AGENTCTL_TRUSTED_ROOT") or _root())


def _toml(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _story_from_branch(branch: str | None) -> str | None:
    m = re.match(r"(?:refs/heads/)?story/(\d{3})(?:-|$)", branch or "")
    return m.group(1) if m else None


def _current_branch() -> str:
    return subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()


def _finish(name: str, problems: list[str]) -> int:
    if problems:
        print(f"{name}: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"{name}: ok")
    return 0


def cmd_risk(args) -> int:
    root = _root()
    policy = risk.load_policy(_trusted_root() / "policy/risk-tiers.toml")
    story = _story_from_branch(args.branch or _current_branch())
    has_story = bool(story and story in specs.load_all(root / "docs/specs"))
    result = risk.assess(risk.changes_from_git(args.base, args.head), policy, has_story)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_spec_lint(args) -> int:
    return _finish("spec lint", specs.lint(_root() / "docs/specs"))


def cmd_trace(args) -> int:
    root = _root()
    all_specs = specs.load_all(root / "docs/specs")
    story = args.story or _story_from_branch(args.branch or _current_branch())
    head = trace.parse_junit(args.junit)
    base = trace.parse_junit(args.base_junit) if args.base_junit else None
    return _finish("spec-trace", trace.check(all_specs, head, story, base))


def cmd_redgreen(args) -> int:
    root = _root()
    project = _toml(_trusted_root() / "policy/project.toml")
    story = args.story or _story_from_branch(args.branch or _current_branch())
    all_specs = specs.load_all(root / "docs/specs")
    if not story or story not in all_specs:
        print("red-green: no story on this branch, nothing to check")
        return 0
    spec = all_specs[story]
    overlay = redgreen.test_files_to_overlay(root, args.base, spec, project.get("test_paths", []))
    print("overlaying on base:", ", ".join(overlay) or "(nothing)")
    base_results = redgreen.run_on_base(root, args.base, overlay, project["test_cmd"], project["junit_glob"])
    head_results = trace.parse_junit(args.junit or [str(root / project["junit_glob"])])
    return _finish("red-green", redgreen.check(spec, base_results, head_results))


def cmd_evidence(args) -> int:
    root = _root()
    all_specs = specs.load_all(root / "docs/specs")
    if args.story not in all_specs:
        print(f"unknown story {args.story}", file=sys.stderr)
        return 1
    print(trace.evidence_markdown(all_specs[args.story], trace.parse_junit(args.junit)))
    return 0


def cmd_reconcile(args) -> int:
    from . import github, reconcile

    root = _root()
    policy = _toml(root / "policy/conductor.toml")
    roles = _toml(root / "policy/roles.toml")
    state, context = github.collect(root)
    actions = reconcile.plan(state, policy, roles)
    if not actions:
        print("nothing to do")
    failures = github.execute(actions, context, roles, dry_run=args.dry_run)
    return 1 if failures else 0


def cmd_status(args) -> int:
    from . import github

    state, context = github.collect(_root())
    summary = _status_summary(state, context)
    if args.markdown:
        print(_status_markdown(summary))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _status_summary(state, context) -> dict:
    return {
        "sprint": context["sprint"],
        "paused": state.paused,
        "main_red": state.main_red,
        "stories": [
            {
                "id": s.id,
                "state": "merged" if s.done else "needs-human" if "needs-human" in s.labels
                else "in-progress" if s.started else "todo",
                "stages_done": sorted(s.stage_done),
                "last_dispatch": s.last_dispatch.stage if s.last_dispatch else None,
                "fix_rounds": s.fix_rounds,
                "triage_count": s.triage_count,
                "blocked_by": s.blocked_by,
                "pr": s.pr.number if s.pr else None,
                "awaiting_human_review": bool(s.pr and s.pr.awaiting_human_review),
            }
            for s in sorted(state.stories.values(), key=lambda s: s.id)
        ],
    }


def _status_markdown(summary: dict) -> str:
    stories = summary["stories"]
    merged = sum(1 for s in stories if s["state"] == "merged")
    lines = [f"## Sprint {summary['sprint']}: {merged}/{len(stories)} merged", ""]
    if summary["paused"]:
        lines.append("**Conductor is paused (kill switch).**")
    if summary["main_red"]:
        lines.append("**main is red; dispatching is stopped until it is fixed.**")
    waiting = [s for s in stories if s["state"] == "needs-human" or s["awaiting_human_review"]]
    if waiting:
        lines += ["", "### Waiting for you"]
        for s in waiting:
            what = "review requested on PR #%s" % s["pr"] if s["awaiting_human_review"] else "needs a decision"
            lines.append(f"- Story {s['id']}: {what}")
    lines += ["", "| Story | State | Stages done | In flight | Fix rounds | PR |", "|---|---|---|---|---|---|"]
    for s in stories:
        lines.append("| {id} | {state} | {done} | {flight} | {fix} | {pr} |".format(
            id=s["id"], state=s["state"], done=", ".join(s["stages_done"]) or "-",
            flight=s["last_dispatch"] or "-", fix=s["fix_rounds"], pr=f"#{s['pr']}" if s["pr"] else "-"))
    return "\n".join(lines) + "\n"


def cmd_doctor(args) -> int:
    results = doctor.inside_checks() if args.inside else doctor.host_checks(_root())
    return doctor.report(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentctl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("risk", help="compute the risk tier of a change set")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--head", default="HEAD")
    p.add_argument("--branch", help="branch name (defaults to the current branch)")
    p.set_defaults(func=cmd_risk)

    p = sub.add_parser("spec-lint", help="check story specs for consistency")
    p.set_defaults(func=cmd_spec_lint)

    p = sub.add_parser("trace", help="check that every approved test case ran and passed")
    p.add_argument("--junit", nargs="+", required=True, help="glob(s) of JUnit XML files")
    p.add_argument("--base-junit", nargs="+", help="JUnit XML from the base branch, to detect removed tests")
    p.add_argument("--story")
    p.add_argument("--branch")
    p.set_defaults(func=cmd_trace)

    p = sub.add_parser("redgreen", help="check that the story's tests fail on base and pass on head")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--junit", nargs="+", help="JUnit XML from head (defaults to policy/project.toml junit_glob)")
    p.add_argument("--story")
    p.add_argument("--branch")
    p.set_defaults(func=cmd_redgreen)

    p = sub.add_parser("evidence", help="print the AC/TC/test evidence table for a story")
    p.add_argument("story")
    p.add_argument("--junit", nargs="+", required=True)
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("reconcile", help="conductor: observe GitHub and dispatch the next actions")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("status", help="deterministic sprint summary used by the director's brief")
    p.add_argument("--markdown", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("doctor", help="check host hygiene, or the sandbox boundary with --inside")
    p.add_argument("--inside", action="store_true")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
