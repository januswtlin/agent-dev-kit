"""Command line entry point: python3 -m agentctl <command>."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from . import budget, docs, doctor, lease, redgreen, risk, specs, trace


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
    changed = None
    if args.base:
        out = subprocess.run(["git", "diff", "--name-only", "--no-renames", f"{args.base}...HEAD"],
                             check=True, capture_output=True, text=True).stdout
        changed = {line for line in out.splitlines() if line}
    return _finish("spec lint", specs.lint(_root() / "docs/specs", changed))


def cmd_docs_lint(args) -> int:
    return _finish("docs lint", docs.lint(_root()))


def cmd_trace(args) -> int:
    root = _root()
    all_specs = specs.load_all(root / "docs/specs")
    story = args.story or _story_from_branch(args.branch or _current_branch())
    head = trace.parse_junit(args.junit)
    base = trace.parse_junit(args.base_junit) if args.base_junit else None
    return _finish("traceability", trace.check(all_specs, head, story, base))


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


def cmd_redgreen_collect(args) -> int:
    """Run the story's tests on the base commit and keep the JUnit files (runs PR code)."""
    root = _root()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    project = _toml(root / "policy/project.toml")
    story = args.story or _story_from_branch(args.branch or _current_branch())
    all_specs = specs.load_all(root / "docs/specs")
    if not story or story not in all_specs:
        print("red-green: no story on this branch, nothing to collect")
        return 0
    overlay = redgreen.test_files_to_overlay(root, args.base, all_specs[story], project.get("test_paths", []))
    print("overlaying on base:", ", ".join(overlay) or "(nothing)")
    redgreen.run_on_base(root, args.base, overlay, project["test_cmd"], project["junit_glob"], out_dir=out)
    (out / "collected.json").write_text(json.dumps({"story": story, "base": args.base, "overlay": overlay}), encoding="utf-8")
    return 0


def cmd_redgreen_judge(args) -> int:
    """Judge red-green from JUnit files only. Executes no project code."""
    story = args.story or _story_from_branch(args.branch or _current_branch())
    all_specs = specs.load_all(_root() / "docs/specs")
    if not story or story not in all_specs:
        print("red-green: no story on this branch, nothing to check")
        return 0
    base_dir = Path(args.base_dir)
    marker = base_dir / "collected.json"
    # No JUnit file on base means every test was red there, which is a pass. So an
    # absent collection step must not be mistaken for that.
    if not marker.exists() or json.loads(marker.read_text(encoding="utf-8")).get("story") != story:
        return _finish("red-green", [f"no base results for story {story}: the collection step did not run"])
    return _finish("red-green", redgreen.check(all_specs[story], trace.parse_junit([str(base_dir / "*.xml")]),
                                               trace.parse_junit(args.junit)))


def cmd_evidence(args) -> int:
    root = _root()
    all_specs = specs.load_all(root / "docs/specs")
    if args.story not in all_specs:
        print(f"unknown story {args.story}", file=sys.stderr)
        return 1
    print(trace.evidence_markdown(all_specs[args.story], trace.parse_junit(args.junit)))
    return 0


def _reconcile_once(root: Path, dry_run: bool) -> int:
    from . import github, reconcile

    policy = _toml(root / "policy/conductor.toml")
    roles = _toml(root / "policy/roles.toml")
    state, context = github.collect(root)
    actions = reconcile.plan(state, policy, roles)
    if not actions:
        print("nothing to do")
    return github.execute(actions, context, roles, dry_run=dry_run)


def cmd_reconcile(args) -> int:
    from . import github

    root = _root()
    if args.respect_lease:
        # On GitHub Actions: stand down while a local conductor holds a fresh lease.
        ttl = _toml(root / "policy/conductor.toml").get("local_lease_minutes", 20)
        verdict = lease.decide(os.environ.get("CONDUCTOR_HOME", ""), os.environ.get("CONDUCTOR_LEASE", ""), time.time(), ttl)
        if verdict == "skip":
            print("a local conductor holds the lease; nothing to do here")
            return 0
        if verdict == "takeover" and not args.dry_run:
            print("the local conductor's lease expired; GitHub Actions takes over")
            github.gh("variable", "set", "CONDUCTOR_HOME", "--body", "actions")
    return 1 if _reconcile_once(root, args.dry_run) else 0


def cmd_conductor(args) -> int:
    """Run the conductor in this terminal, or hand it back to GitHub Actions."""
    from . import github

    repo = _root()
    if args.where == "status":
        home = github.gh("variable", "get", "CONDUCTOR_HOME", check=False).strip() or "actions"
        stamp = github.gh("variable", "get", "CONDUCTOR_LEASE", check=False).strip()
        age = f", last local pass {int((time.time() - float(stamp)) / 60)} min ago" if stamp.replace(".", "").isdigit() else ""
        print(f"conductor runs on: {home}{age}")
        return 0
    if args.where == "away":
        github.gh("variable", "set", "CONDUCTOR_HOME", "--body", "actions")
        github.gh("workflow", "run", "conductor.yml", check=False)
        print("handed over to GitHub Actions")
        return 0

    os.environ.update(lease.load_env_file(repo / ".env.conductor"))
    github.gh("variable", "set", "CONDUCTOR_HOME", "--body", "local")
    print(f"conductor is running here, every {args.interval}s. Ctrl-C hands over to GitHub Actions.")
    try:
        while True:
            if github.gh("variable", "get", "CONDUCTOR_HOME", check=False).strip() != "local":
                print("another conductor took over; stopping")
                return 0
            try:
                _reconcile_once(lease.fresh_main_checkout(repo), args.dry_run)
            except (subprocess.CalledProcessError, OSError, SystemExit) as exc:
                print(f"pass failed: {exc}")  # keep going; the next pass starts from scratch
            github.gh("variable", "set", "CONDUCTOR_LEASE", "--body", str(int(time.time())), check=False)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        github.gh("variable", "set", "CONDUCTOR_HOME", "--body", "actions", check=False)
        github.gh("workflow", "run", "conductor.yml", check=False)
        print("\nhanded over to GitHub Actions")
        return 0


def cmd_budget(args) -> int:
    """Estimate month-to-date Actions spend and move heavy CI when it nears the allowance."""
    from . import github

    cfg = budget.settings(_toml(_root() / "policy/conductor.toml"))
    repo = github.gh_json("repo", "view", "--json", "nameWithOwner")["nameWithOwner"]
    try:
        usage = json.loads(github.gh("variable", "get", "ACTIONS_USAGE", check=False) or "null")
    except json.JSONDecodeError:
        usage = None
    now = time.time()
    month = budget.month_of(now)
    since = usage["through"] if usage and usage.get("month") == month else budget.month_start_iso(month)
    run_ids = github.gh("api", "--paginate", f"repos/{repo}/actions/runs?status=completed&created=>={since[:10]}&per_page=100",
                        "--jq", ".workflow_runs[].id", check=False).split()
    jobs: list[dict] = []
    for run_id in run_ids:
        jobs.extend(github.gh_json("api", "--paginate", f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
                                   "--jq", ".jobs", default=[]) or [])
    usage = budget.accumulate(usage, jobs, now, cfg)
    runner, reason = budget.choose_runner(usage, cfg)
    print(budget.summary(usage, runner, cfg))
    if not args.dry_run:
        github.gh("variable", "set", "ACTIONS_USAGE", "--body", json.dumps(usage))
        current = github.gh("variable", "get", "CI_RUNNER", check=False).strip()
        if current != runner:
            github.gh("variable", "set", "CI_RUNNER", "--body", runner)
            print(f"CI_RUNNER -> {runner} ({reason})")
    return 0


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
    p.add_argument("--base", help="also require both language versions of a story to change together since this ref")
    p.set_defaults(func=cmd_spec_lint)

    p = sub.add_parser("docs-lint", help="check that every document has its -zh-TW counterpart with the same structure")
    p.set_defaults(func=cmd_docs_lint)

    p = sub.add_parser("redgreen-collect", help="run the story's tests on the base commit and keep the JUnit files")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--out", required=True)
    p.add_argument("--story")
    p.add_argument("--branch")
    p.set_defaults(func=cmd_redgreen_collect)

    p = sub.add_parser("redgreen-judge", help="judge red-green from JUnit files only")
    p.add_argument("--base-dir", required=True, help="directory written by redgreen-collect")
    p.add_argument("--junit", nargs="+", required=True)
    p.add_argument("--story")
    p.add_argument("--branch")
    p.set_defaults(func=cmd_redgreen_judge)

    p = sub.add_parser("conductor", help="run the conductor in this terminal (here), hand it to Actions (away), or show where it runs")
    p.add_argument("where", choices=["here", "away", "status"])
    p.add_argument("--interval", type=int, default=180, help="seconds between passes when running here")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_conductor)

    p = sub.add_parser("budget", help="estimate this month's Actions spend; move heavy CI to self-hosted near the allowance")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_budget)

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
    p.add_argument("--respect-lease", action="store_true", help="stand down while a local conductor holds the lease")
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
