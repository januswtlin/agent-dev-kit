"""Command line entry point: python3 -m agentctl <command>."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import apptoken, budget, config, docs, doctor, ids, local, owners, pins, profiles, redgreen, risk, specs, trace


def _root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(out.stdout.strip()) if out.returncode == 0 else Path.cwd()


def _trusted_root() -> Path:
    """Where agentdev.toml is read from.

    In CI this points at a checkout of the base branch, so a pull request cannot
    loosen the configuration that judges it. Locally it is the repository itself.
    """
    return Path(os.environ.get("AGENTCTL_TRUSTED_ROOT") or _root())


def _config() -> dict:
    return config.load(_trusted_root())


def _specs(cfg: dict, root: Path) -> dict:
    return specs.load_all(config.path(cfg, root, "specs"))


def _story_from_branch(branch: str | None) -> str | None:
    return ids.story_from_branch(branch)


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
    root, cfg = _root(), _config()
    story = _story_from_branch(args.branch or _current_branch())
    has_story = bool(story and story in _specs(cfg, root))
    result = risk.assess(risk.changes_from_git(args.base, args.head), cfg["risk"], has_story)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_spec_lint(args) -> int:
    changed = None
    if args.base:
        out = subprocess.run(["git", "diff", "--name-only", "-z", "--no-renames", f"{args.base}...HEAD"],
                             check=True, capture_output=True, text=True).stdout
        changed = {line for line in out.split("\0") if line}
    cfg = _config()
    return _finish("spec lint", specs.lint(config.path(cfg, _root(), "specs"), changed,
                                           translation=cfg["stories"].get("translation", ""),
                                           max_lines=cfg["stories"].get("max_lines", specs.STORY_MAX_LINES)))


def cmd_docs_lint(args) -> int:
    cfg = _config()
    return _finish("docs lint", docs.lint(_root(), cfg["docs"].get("translation", ""), cfg["docs"].get("required", [])))


def cmd_trace(args) -> int:
    root, cfg = _root(), _config()
    all_specs = _specs(cfg, root)
    story = args.story or _story_from_branch(args.branch or _current_branch())
    head = trace.parse_junit(args.junit)
    base = None
    if args.base_junit:
        # One directory per earlier run. A test case that passed in any of them must
        # still pass: one partial or broken run on main must not make it forgettable.
        import glob as _glob
        by_run: dict[str, list[str]] = {}
        for pattern in args.base_junit:
            for path in sorted(_glob.glob(pattern, recursive=True)):
                by_run.setdefault(str(Path(path).parent), []).append(path)
        base = trace.passed_in_any([trace.parse_junit(paths) for paths in by_run.values()])
    retired = specs.load_retired(config.path(cfg, root, "specs"))
    return _finish("traceability", trace.check(all_specs, head, story, base, retired))


def cmd_redgreen(args) -> int:
    root, cfg = _root(), _config()
    project = cfg["tests"]
    story = args.story or _story_from_branch(args.branch or _current_branch())
    all_specs = _specs(cfg, root)
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
    # This job runs pull request code anyway, so the configuration may come from it.
    cfg = config.load(root)
    project = cfg["tests"]
    story = args.story or _story_from_branch(args.branch or _current_branch())
    all_specs = _specs(cfg, root)
    if not story or story not in all_specs:
        print("red-green: no story on this branch, nothing to collect")
        return 0
    overlay = redgreen.test_files_to_overlay(root, args.base, all_specs[story], project.get("test_paths", []))
    print("overlaying on base:", ", ".join(overlay) or "(nothing)")
    info: dict = {}
    redgreen.run_on_base(root, args.base, overlay, project["test_cmd"], project["junit_glob"], out_dir=out,
                         setup_cmd=project.get("setup_cmd", ""), info=info)
    reports = len(list(out.glob("*.xml")))
    (out / "collected.json").write_text(json.dumps({"story": story, "base": args.base, "overlay": overlay, "reports": reports,
                                                    "setup_exit": info.get("setup_exit")}), encoding="utf-8")
    return 0


def cmd_redgreen_judge(args) -> int:
    """Judge red-green from JUnit files only. Executes no project code."""
    story = args.story or _story_from_branch(args.branch or _current_branch())
    all_specs = _specs(_config(), _root())
    if not story or story not in all_specs:
        print("red-green: no story on this branch, nothing to check")
        return 0
    base_dir = Path(args.base_dir)
    marker = base_dir / "collected.json"
    # No JUnit file on base means every test was red there, which is a pass. So an
    # absent collection step must not be mistaken for that.
    try:
        collected = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    except (json.JSONDecodeError, OSError):
        collected = {}
    if not isinstance(collected, dict) or collected.get("story") != story:
        return _finish("red-green", [f"no base results for story {story}: the collection step did not run"])
    reports = len(list(base_dir.glob("*.xml")))
    setup_exit = collected.get("setup_exit")
    return _finish("red-green", redgreen.check(
        all_specs[story], trace.parse_junit([str(base_dir / "*.xml")]), trace.parse_junit(args.junit),
        base_report_count=reports,
        base_red_count=trace.count_red([str(base_dir / "*.xml")],
                                       [Path(str(p)).stem for p in collected.get("overlay") or [] if isinstance(p, str)]),
        setup_exit=setup_exit if isinstance(setup_exit, int) else None))


def cmd_evidence(args) -> int:
    all_specs = _specs(_config(), _root())
    if args.story not in all_specs:
        print(f"unknown story {args.story}", file=sys.stderr)
        return 1
    print(trace.evidence_markdown(all_specs[args.story], trace.parse_junit(args.junit)))
    return 0


def _reconcile_once(root: Path, dry_run: bool) -> int:
    from . import github, reconcile

    cfg = config.load(root)
    # A dry run reads and prints. It creates nothing, not even the tracking issues.
    state, context = github.collect(root, cfg, read_only=dry_run)
    actions = reconcile.plan(state, cfg["conductor"], cfg["roles"])
    if not actions:
        print("nothing to do")
    return github.execute(actions, context, cfg["roles"], dry_run=dry_run)


def _conductor_identity(repo: Path) -> tuple[str, str, str]:
    """Make this process act on GitHub as the Conductor App.

    Acting as the developer instead would make them the author of the pull
    requests the conductor opens, and GitHub does not let an author approve
    their own pull request.
    """
    env_path = local.conductor_env_path(repo)
    settings = local.load_env_file(env_path)
    missing = [k for k in ("CONDUCTOR_APP_ID", "CONDUCTOR_APP_KEY", "DEVELOPER") if not settings.get(k)]
    if missing:
        raise SystemExit(f"{env_path} must define {', '.join(missing)}. See docs/layer-4-conductor.md in the kit.")
    os.environ.update(settings)
    remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=repo).stdout
    full_name = apptoken.repo_from_remote(remote)
    if not full_name:
        raise SystemExit("origin is not a GitHub repository")
    slug = apptoken.app_slug(settings["CONDUCTOR_APP_ID"], settings["CONDUCTOR_APP_KEY"])
    os.environ["CONDUCTOR_BOT"] = f"{slug}[bot]"
    os.environ["CONDUCTOR_LOCAL_DEVELOPER"] = settings["DEVELOPER"]
    os.environ["GH_REPO"] = full_name
    return settings["CONDUCTOR_APP_ID"], settings["CONDUCTOR_APP_KEY"], full_name


def _as_conductor(app_id: str, key: str, full_name: str) -> None:
    os.environ["GH_TOKEN"] = apptoken.installation_token(app_id, key, full_name, profile="conductor")


# After this many failed passes in a row the conductor waits longer between passes.
BACKOFF_AFTER = 3
BACKOFF_SECONDS = 900


def cmd_conductor(args) -> int:
    """Run the conductor in this terminal. It is the project's only conductor."""
    repo = _root()
    app_id, key, full_name = _conductor_identity(repo)
    _as_conductor(app_id, key, full_name)
    # Local sandboxes clone this repository. Specs, sprint and configuration are read from a
    # fresh checkout of the default branch, never from the working tree.
    os.environ["AGENT_PROJECT_DIR"] = str(repo)

    if args.dry_run:
        return 1 if _reconcile_once(local.fresh_main_checkout(repo), True) else 0

    lock = local.single_instance(repo)  # held until the conductor stops
    print(f"conductor is running here as {os.environ['CONDUCTOR_BOT']}, every {args.interval}s. Ctrl-C stops it.")
    failures = 0
    try:
        while True:
            try:
                _as_conductor(app_id, key, full_name)
                trusted = local.fresh_main_checkout(repo)
                failed = _reconcile_once(trusted, False)
            except (subprocess.CalledProcessError, OSError, SystemExit) as exc:
                print(f"pass failed: {exc}")
                failed = 1
            failures = failures + 1 if failed else 0
            if failures >= BACKOFF_AFTER:
                print(f"{failures} passes in a row failed; next pass in {BACKOFF_SECONDS // 60} minutes")
            time.sleep(BACKOFF_SECONDS if failures >= BACKOFF_AFTER else args.interval)
    except KeyboardInterrupt:
        print("\nconductor stopped; nothing advances until it runs again")
        return 0
    finally:
        lock.close()


def cmd_app_token(args) -> int:
    """Print a short-lived token for this developer's agent GitHub App."""
    app_id = args.app_id or os.environ.get("AGENT_APP_ID")
    key = args.key or os.environ.get("AGENT_APP_KEY")
    if not app_id or not key:
        print("set AGENT_APP_ID and AGENT_APP_KEY (path to the App's private key)", file=sys.stderr)
        return 1
    repo = args.repo
    if not repo:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout
        repo = apptoken.repo_from_remote(remote)
    if not repo:
        print("cannot tell which repository this is; pass --repo owner/name", file=sys.stderr)
        return 1
    token = apptoken.installation_token(app_id, key, repo, profile=args.profile,
                                        permissions=profiles.TOKEN_PERMISSIONS[args.profile])
    if args.git_credential:
        print(f"username=x-access-token\npassword={token}")
    else:
        print(token)
    return 0


def cmd_repo_name(args) -> int:
    """owner/name of a GitHub remote URL; empty when it is not one."""
    print(apptoken.repo_from_remote(args.url) or "")
    return 0


def cmd_stage_profile(args) -> int:
    """Print what a stage's sandbox is given: token scope, network, settings."""
    profile = profiles.for_stage(args.stage)
    print(profile["token"], profile["network"], profile["settings"])
    return 0


def cmd_budget(args) -> int:
    """Estimate month-to-date Actions spend and move heavy CI when it nears the allowance."""
    return _budget(_root(), args.dry_run)


def _budget(root: Path, dry_run: bool) -> int:
    from . import github

    cfg = budget.settings(config.load(root)["conductor"])
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
    if not dry_run:
        github.gh("variable", "set", "ACTIONS_USAGE", "--body", json.dumps(usage))
        current = github.gh("variable", "get", "CI_RUNNER", check=False).strip()
        if current != runner:
            github.gh("variable", "set", "CI_RUNNER", "--body", runner)
            print(f"CI_RUNNER -> {runner} ({reason})")
    return 0


def cmd_status(args) -> int:
    from . import github

    root = _root()
    state, context = github.collect(root, config.load(root), read_only=True)
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


def cmd_codeowners(args) -> int:
    """Print .github/CODEOWNERS for this project, or check the committed one."""
    text = owners.codeowners(_config())
    if not args.check:
        print(text, end="")
        return 0
    path = _root() / ".github/CODEOWNERS"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    return _finish("codeowners", [] if current == text else
                   [".github/CODEOWNERS differs from agentdev.toml; run `agentctl codeowners > .github/CODEOWNERS`"])


def cmd_harness_settings(args) -> int:
    print(owners.harness_settings(_config(), args.kind), end="")
    return 0


def cmd_sandbox(args) -> int:
    """Run the kit's sandbox/sbx.sh (setup, job) for the project in the current directory."""
    from .github import KIT_ROOT
    os.execv("/bin/bash", ["bash", str(KIT_ROOT / "sandbox" / "sbx.sh"), *args.args])


def cmd_config(args) -> int:
    """Print one setting, for workflows and scripts: `agentctl config tests.test_cmd`."""
    value = _config()
    for part in args.key.split("."):
        if not isinstance(value, dict) or part not in value:
            print(f"no setting {args.key}", file=sys.stderr)
            return 1
        value = value[part]
    if isinstance(value, list) and args.words:
        print(" ".join(str(v) for v in value))
    elif isinstance(value, (dict, list)):
        print(json.dumps(value))
    else:
        print(value)
    return 0


def cmd_story_of(args) -> int:
    """Print the story id of a branch name, or nothing."""
    _config()  # the id length comes from the configuration
    print(_story_from_branch(args.branch) or "")
    return 0


def cmd_prompt(args) -> int:
    """Print a stage's prompt, filled in from the project's configuration."""
    from . import prompts
    print(prompts.render(args.stage, _config()))
    return 0


def cmd_pins(args) -> int:
    """Check that every reference to the kit in .github/workflows uses the version agentdev.toml pins."""
    cfg = _config()
    return _finish("kit pins", pins.check(_root(), cfg["kit"].get("repository", ""), cfg["kit"].get("version", "")))


def cmd_collect_junit(args) -> int:
    """Copy the JUnit files [tests] junit_glob finds into one directory, under unique names."""
    import glob as _glob
    import shutil
    cfg, root = config.load(_root()), _root()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    found = sorted(_glob.glob(str(root / cfg["tests"]["junit_glob"]), recursive=True))
    for n, path in enumerate(found):
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            continue
        shutil.copyfile(source, out / f"{n:03d}-{source.name}")
    print(f"{len(found)} JUnit file(s) from {cfg['tests']['junit_glob']}")
    return 0


def cmd_init(args) -> int:
    from . import init
    created, kept = init.init(_root(), args.people, args.kit_version, args.dry_run)
    for rel in created:
        print(("would create " if args.dry_run else "created ") + rel)
    for rel in kept:
        print(f"kept       {rel} (exists; merge the kit's version by hand if you need it)")
    if not args.dry_run:
        print("Next: review agentdev.toml, commit, and follow the setup document of each layer you adopt.")
    return 0


def cmd_rulesets(args) -> int:
    from .github import KIT_ROOT
    os.execv("/bin/bash", ["bash", str(KIT_ROOT / "scripts" / "apply-rulesets.sh"), args.layer, *([args.repo] if args.repo else [])])


def cmd_junit_unittest(args) -> int:
    from . import junit_unittest
    return junit_unittest.main(["junit-unittest", args.test_dir, args.output])


def cmd_doctor(args) -> int:
    results = doctor.inside_checks() if args.inside else doctor.host_checks(_root())
    return doctor.report(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentctl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("risk", help="compute the risk tier of a change set")
    p.add_argument("--base", default="refs/remotes/origin/main")
    p.add_argument("--head", default="HEAD")
    p.add_argument("--branch", help="branch name (defaults to the current branch)")
    p.set_defaults(func=cmd_risk)

    p = sub.add_parser("spec-lint", help="check story specs for consistency")
    p.add_argument("--base", help="also require both language versions of a story to change together since this ref")
    p.set_defaults(func=cmd_spec_lint)

    p = sub.add_parser("docs-lint", help="check that every document has its -zh-TW counterpart with the same structure")
    p.set_defaults(func=cmd_docs_lint)

    p = sub.add_parser("redgreen-collect", help="run the story's tests on the base commit and keep the JUnit files")
    p.add_argument("--base", default="refs/remotes/origin/main")
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

    p = sub.add_parser("conductor", help="run the conductor in this terminal; --dry-run prints one pass's plan")
    p.add_argument("--interval", type=int, default=180, help="seconds between passes")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_conductor)

    p = sub.add_parser("app-token", help="print a short-lived token for the agent's GitHub App")
    p.add_argument("--app-id")
    p.add_argument("--key", help="path to the App's private key")
    p.add_argument("--repo", help="owner/name (defaults to the origin remote)")
    p.add_argument("--git-credential", action="store_true", help="output in git credential-helper format")
    p.add_argument("--profile", choices=sorted(profiles.TOKEN_PERMISSIONS), default="write",
                   help="permission set: write (push) or read (cannot push)")
    p.set_defaults(func=cmd_app_token)

    p = sub.add_parser("repo-name", help="print owner/name for a GitHub remote URL")
    p.add_argument("url")
    p.set_defaults(func=cmd_repo_name)

    p = sub.add_parser("stage-profile", help="print the token scope, network and settings a stage's sandbox gets")
    p.add_argument("stage")
    p.set_defaults(func=cmd_stage_profile)

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
    p.add_argument("--base", default="refs/remotes/origin/main")
    p.add_argument("--junit", nargs="+", help="JUnit XML from head (defaults to [tests] junit_glob)")
    p.add_argument("--story")
    p.add_argument("--branch")
    p.set_defaults(func=cmd_redgreen)

    p = sub.add_parser("evidence", help="print the AC/TC/test evidence table for a story")
    p.add_argument("story")
    p.add_argument("--junit", nargs="+", required=True)
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("status", help="deterministic sprint summary used by the director's brief")
    p.add_argument("--markdown", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("codeowners", help="print .github/CODEOWNERS generated from agentdev.toml, or --check it")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_codeowners)

    p = sub.add_parser("harness-settings", help="print the Claude Code deny rules for a stage's sandbox")
    p.add_argument("kind", choices=["story", "spec"])
    p.set_defaults(func=cmd_harness_settings)

    p = sub.add_parser("sandbox", help="run the kit's sandbox script: setup, or job HARNESS STORY STAGE PROMPT")
    p.add_argument("args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_sandbox)

    p = sub.add_parser("config", help="print one setting of agentdev.toml (with the kit defaults), e.g. tests.test_cmd")
    p.add_argument("key")
    p.add_argument("--words", action="store_true", help="print a list as space-separated words")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("story-of", help="print the story id of a branch name")
    p.add_argument("branch")
    p.set_defaults(func=cmd_story_of)

    p = sub.add_parser("prompt", help="print a stage's prompt filled in for this project")
    p.add_argument("stage")
    p.set_defaults(func=cmd_prompt)

    p = sub.add_parser("pins", help="check that the workflows use the kit version agentdev.toml pins")
    p.set_defaults(func=cmd_pins)

    p = sub.add_parser("collect-junit", help="copy the JUnit files of [tests] junit_glob into one directory")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_collect_junit)

    p = sub.add_parser("init", help="copy the kit's project files into this repository (never overwrites)")
    p.add_argument("people", nargs="+", metavar="LOGIN", help="the director first, then anyone else whose approval counts")
    p.add_argument("--kit-version", default="", help="full commit SHA to pin (default: this kit's own)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("rulesets", help="create or update the rulesets of layer 2 or 3 (run by an admin)")
    p.add_argument("layer", choices=["2", "3"])
    p.add_argument("repo", nargs="?", help="owner/name (default: the current repository)")
    p.set_defaults(func=cmd_rulesets)

    p = sub.add_parser("junit-unittest", help="run Python unittest over a directory and write JUnit XML")
    p.add_argument("test_dir")
    p.add_argument("output")
    p.set_defaults(func=cmd_junit_unittest)

    p = sub.add_parser("doctor", help="check host hygiene, or the sandbox boundary with --inside")
    p.add_argument("--inside", action="store_true")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
