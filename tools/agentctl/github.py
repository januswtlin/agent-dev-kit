"""GitHub adapter for the conductor: observe state, execute actions.

Everything goes through the `gh` CLI. All conductor memory is kept on GitHub
itself as hidden marker comments, labels and issue links, so this module holds
no state between runs.

Trust rules for what is read back:
  - marker comments count only when written by the conductor itself or by a
    human listed in [roles] of agentdev.toml. An agent can comment on issues, so a
    marker from anyone else is ignored.
  - a story's pull request is the open (else the merged) one from this
    repository into the default branch. Closed, cross-repository or
    other-base pull requests are never picked up.
  - who a story runs for comes from the approved sprint file, not from issue
    assignees, which change when a story is escalated.

NOTE: this adapter has not been exercised against a live repository yet.
The pure scheduling logic it feeds (reconcile.plan) is unit-tested; the calls
here are to be validated in the spike described in docs/new-project.md.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import tomllib
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config, ids
from .reconcile import PR, Action, Dispatch, State, Story
from .specs import load_all

MARKER_RE = re.compile(r"<!-- conductor (\{.*?\}) -->", re.DOTALL)
NOTIFIED_RE = re.compile(r"<!-- conductor-notified ([\w:/.-]+) -->")
BRANCH_PREFIXES = ("story/", "spec/", "sprint/", "chore/")
SAFE_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,120}$")
NAME_RE = re.compile(r"^[a-z][a-z-]{1,30}$")
# The installed kit this module belongs to (tools/agentctl/github.py -> kit root).
KIT_ROOT = Path(__file__).resolve().parents[2]


class Deferred(Exception):
    """This action cannot be carried out from here; another conductor run will do it."""


def gh(*args: str, check: bool = True, token: str | None = None) -> str:
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    return subprocess.run(["gh", *args], check=check, capture_output=True, text=True, env=env).stdout


def gh_json(*args: str, default=None):
    try:
        return json.loads(gh(*args) or "null")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return default


class Unreadable(OSError):
    """A repository variable could not be read. Not the same as "it is not set"."""


def variable(name: str) -> str:
    """A repository variable, read live. Empty when it is not set.

    A failed read raises. The kill switch is a variable, and a network error must
    never read as "not paused".
    """
    try:
        return gh("api", f"repos/{{owner}}/{{repo}}/actions/variables/{name}", "--jq", ".value").strip()
    except subprocess.CalledProcessError as exc:
        if "HTTP 404" in (exc.stderr or ""):
            return ""
        raise Unreadable(f"cannot read the repository variable {name}: {(exc.stderr or '').strip()[-200:]}") from exc


def active_sprint(sprints_dir: Path) -> tuple[str, dict]:
    """The highest-numbered sprint file on the default branch is the active sprint."""
    files = sorted((p for p in sprints_dir.glob("*.toml") if p.stem.isdigit()), key=lambda p: int(p.stem))
    if not files:
        raise SystemExit(f"no sprint file in {sprints_dir}")
    with open(files[-1], "rb") as fh:
        return files[-1].stem, tomllib.load(fh)


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _check_state(item: dict) -> str:
    value = (item.get("conclusion") or item.get("state") or "").upper()
    if value in ("SUCCESS", "NEUTRAL", "SKIPPED"):
        return "success"
    if value in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"):
        return "failure"
    return "pending"


def check_name(item: dict) -> str:
    """A check's name without its caller: the kit's workflows are reusable, and
    GitHub reports their jobs as "<caller job> / <job>" ("ci / spec-verify")."""
    return (item.get("name") or item.get("context") or "").rsplit(" / ", 1)[-1]


ISSUE_FIELDS = "number,labels,comments"


def find_issue(label: str) -> dict | None:
    found = gh_json("issue", "list", "--label", label, "--state", "all", "--limit", "1", "--json", ISSUE_FIELDS, default=[])
    return found[0] if found else None


def ensure_issue(label: str, title: str, body: str, read_only: bool) -> dict:
    """The issue carrying `label`. Created when missing, unless this is a dry run."""
    issue = find_issue(label)
    if issue or read_only:
        return issue or {"number": 0, "labels": [], "comments": []}
    gh("label", "create", label, "--force", check=False)
    gh("issue", "create", "--title", title, "--body", body, "--label", label)
    return find_issue(label) or {"number": 0, "labels": [], "comments": []}


def trusted_authors(roles: dict, extra_bot: str = "") -> set[str]:
    """Logins whose marker comments are believed: the conductor and the humans.

    The bot is accepted with and without its "[bot]" suffix, because GitHub's
    two APIs spell a bot's login differently. A person whose login equals the
    App's slug would therefore be believed too; they would also have to be a
    collaborator on this repository to comment at all.
    """
    logins = {str(h) for h in roles.get("humans", [])}
    for bot in (os.environ.get("CONDUCTOR_BOT", ""), extra_bot):
        if bot:
            logins.add(bot)
            logins.add(bot.removesuffix("[bot]"))
    return logins


def _comments_by(issue: dict, authors: set[str]) -> list[str]:
    return [c.get("body", "") for c in issue.get("comments", [])
            if (c.get("author") or {}).get("login") in authors]


def read_markers(bodies: list[str]) -> list[dict]:
    """Dispatch markers in order, without the ones a later marker cancelled."""
    markers, cancelled = [], set()
    for body in bodies:
        for raw in MARKER_RE.findall(body):
            try:
                marker = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "cancel" in marker:
                cancelled.add(marker["cancel"])
            elif "stage" in marker and "at" in marker:
                markers.append(marker)
    return [m for m in markers if m.get("id") not in cancelled]


def select_pr(prs: list[dict], story_id: str, default_branch: str, branch: str | None = None) -> dict | None:
    """The story's pull request: open first, else merged; same repository, default base.

    With `branch` (the name the spec gives the story's branch), only that exact
    branch counts: story/012-anything-else is not story 012's pull request.
    """
    mine = [p for p in prs
            if (m := ids.STORY_BRANCH_RE.match(p.get("headRefName", ""))) and m.group(1) == story_id
            and (branch is None or p.get("headRefName") == branch)
            and p.get("baseRefName") == default_branch and not p.get("isCrossRepository")]
    for state in ("OPEN", "MERGED"):
        candidates = [p for p in mine if p.get("state") == state]
        if candidates:
            return max(candidates, key=lambda p: p["number"])
    return None


def unopened_branches(branches: list[tuple[str, str]], prs: list[dict], default_branch: str,
                      story_branches: set[str] | None = None) -> list[str]:
    """Agent branches that have no pull request into the default branch for their tip yet.

    A pull request into some other base does not count: it would otherwise keep
    the real one from ever being opened. With `story_branches`, a story/ branch
    is only picked up when it is one of those names (the ones the specs define).
    """
    result = []
    for name, sha in branches:
        if not name.startswith(BRANCH_PREFIXES) or not SAFE_BRANCH_RE.match(name):
            continue
        if story_branches is not None and name.startswith("story/") and name not in story_branches:
            continue
        covered = any(p.get("headRefName") == name and not p.get("isCrossRepository")
                      and p.get("baseRefName") == default_branch
                      and (p.get("state") == "OPEN" or p.get("headRefOid") == sha) for p in prs)
        if not covered:
            result.append(name)
    return sorted(result)


def tier_of(checks: dict[str, str]) -> str:
    """The risk tier of a commit, from the statuses the risk-gate workflow put on it.

    Not from the pull request's `tier:` label: an agent's token can edit labels,
    and the tier decides whether the conductor may merge. A commit status is on
    one commit and needs a permission no agent token has. The most restrictive
    tier found wins; none found is treated as T2.
    """
    found = [name.split("/", 1)[1] for name, state in checks.items()
             if name.startswith("risk-tier/") and state == "success" and name.split("/", 1)[1] in ("T0", "T1", "T2")]
    return max(found) if found else "T2"


def approved_decision_prs(prs: list[dict], default_branch: str) -> list[int]:
    """Open spec/sprint pull requests into the default branch that a human approved.

    "Approved" is GitHub's own review decision, which with code owner review
    required means an owner approved the current commit. A pull request nobody
    has to review has no decision and is never picked up here.
    """
    return sorted(p["number"] for p in prs
                  if p.get("state") == "OPEN" and p.get("headRefName", "").startswith(("spec/", "sprint/"))
                  and p.get("baseRefName") == default_branch and not p.get("isCrossRepository")
                  and p.get("reviewDecision") == "APPROVED" and not p.get("autoMergeRequest"))


def collect(repo_root: Path, cfg: dict, read_only: bool = False) -> tuple[State, dict]:
    """Build the State the planner needs, plus a context dict for the executor."""
    roles = cfg["roles"]
    sprint_id, sprint = active_sprint(config.path(cfg, repo_root, "sprints"))
    specs = load_all(config.path(cfg, repo_root, "specs"))
    view = gh_json("repo", "view", "--json", "nameWithOwner,defaultBranchRef")
    repo = view["nameWithOwner"]
    default_branch = (view.get("defaultBranchRef") or {}).get("name") or "main"
    default_owner = str(sprint.get("assignee", "default"))
    owners = {str(k): str(v) for k, v in (sprint.get("owners") or {}).items()}
    # The variables are read first and together. Fail closed: when one of them
    # cannot be read, the pass behaves as if the kill switch were on, and still
    # gets far enough to withdraw auto-merge.
    pause_reason = "kill switch is on"
    extra_bot, quota = "", {}
    try:
        paused = variable("CONDUCTOR_PAUSED").lower() in ("1", "true", "yes")
        extra_bot = variable("CONDUCTOR_BOT")
        quota = json.loads(variable("CONDUCTOR_QUOTA") or "{}")
    except Unreadable as exc:
        paused, quota, pause_reason = True, {}, f"treated as paused: {exc}"
    except json.JSONDecodeError:
        quota = {}
    authors = trusted_authors(roles, extra_bot)

    prs = gh_json(
        "pr", "list", "--state", "all", "--limit", "300", "--json",
        "number,headRefName,headRefOid,baseRefName,isCrossRepository,state,isDraft,mergedAt,createdAt,"
        "mergeable,mergeStateStatus,labels,autoMergeRequest,reviewDecision,statusCheckRollup", default=[],
    ) or []
    today = datetime.now(timezone.utc).date()
    prs_today = sum(1 for p in prs if p["headRefName"].startswith("story/")
                    and datetime.fromtimestamp(_epoch(p["createdAt"]), timezone.utc).date() == today)

    sprint_issue = ensure_issue(f"sprint:{sprint_id}", f"Sprint {sprint_id}",
                                "Conductor notifications for this sprint.", read_only)
    sprint_bodies = _comments_by(sprint_issue, authors)
    notified = {key for body in sprint_bodies for key in NOTIFIED_RE.findall(body)}
    po_markers = [m for m in read_markers(sprint_bodies) if m.get("stage") == "product-owner"]
    last_po = float(po_markers[-1]["at"]) if po_markers else None

    roadmap = config.path(cfg, repo_root, "roadmap")
    roadmap_text = re.sub(r"<!--.*?-->", "", roadmap.read_text(encoding="utf-8"), flags=re.DOTALL) if roadmap.exists() else ""
    unchecked = len(re.findall(r"^- \[ \] \S", roadmap_text, re.MULTILINE))
    open_spec_prs = sum(1 for p in prs if p["state"] == "OPEN" and p["headRefName"].startswith("spec/"))
    # A line is ticked inside its spec branch, so on main it stays unchecked until
    # that pull request merges. Each open spec pull request accounts for one line.
    roadmap_pending = max(0, unchecked - open_spec_prs)

    issue_to_story: dict[int, str] = {}
    issues: dict[str, dict] = {}
    for sid in sprint.get("stories", []):
        sid = str(sid)
        # Story ids end up in branch names, sandbox names and log paths.
        if not ids.is_story(sid):
            raise SystemExit(f"sprint {sprint_id}: '{sid}' is not a story id ({ids.DIGITS} digits)")
        spec = specs.get(sid)
        title = f"Story {sid}: {spec.title if spec else '(spec missing)'}"
        issue = ensure_issue(f"story:{sid}", title, f"Runtime state for story {sid}. Spec: {cfg['paths']['specs']}/{sid}-*/", read_only)
        issues[sid] = issue
        if issue["number"]:
            issue_to_story[issue["number"]] = sid

    stories: dict[str, Story] = {}
    for sid, issue in issues.items():
        spec = specs.get(sid)
        labels = {label["name"] for label in issue.get("labels", [])}
        markers = read_markers(_comments_by(issue, authors))
        last = markers[-1] if markers else None
        impl = [m for m in markers if m.get("stage") == "impl"]

        pr = None
        p = select_pr(prs, sid, default_branch, f"story/{sid}-{spec.slug}" if spec else None)
        if p:
            checks = {check_name(c): _check_state(c) for c in p.get("statusCheckRollup") or []}
            pr = PR(
                number=p["number"],
                merged=p.get("state") == "MERGED",
                checks=checks,
                behind=p.get("mergeStateStatus") == "BEHIND",
                conflicted=p.get("mergeable") == "CONFLICTING",
                auto_merge=bool(p.get("autoMergeRequest")),
                awaiting_human_review=p.get("reviewDecision") in ("REVIEW_REQUIRED", "CHANGES_REQUESTED"),
                tier=tier_of(checks),
                draft=bool(p.get("isDraft")),
                head_sha=p.get("headRefOid", ""),
            )

        blocked_by: list[str] = []
        if issue["number"]:
            blocked = gh_json("api", f"repos/{repo}/issues/{issue['number']}/dependencies/blocked_by", default=[]) or []
            blocked_by = sorted({issue_to_story[b["number"]] for b in blocked
                                 if b.get("state") == "open" and b.get("number") in issue_to_story})

        stories[sid] = Story(
            id=sid,
            priority=spec.priority if spec else 100,
            depends_on=list(spec.depends_on) if spec else [],
            blocked_by=blocked_by,
            touches=list(spec.touches) if spec else [],
            assignee=owners.get(sid, default_owner),
            labels=labels & {"needs-human", "blocked"},
            pr=pr,
            stage_done={name.split(":", 1)[1] for name in labels if name.startswith("done:")},
            last_dispatch=Dispatch(last["stage"], float(last["at"]), last.get("harness", ""), int(last.get("attempt", 1)),
                                   last.get("sha", "")) if last else None,
            impl_harness=impl[-1].get("harness", "") if impl else "",
            fix_rounds=sum(1 for m in markers if m.get("stage") == "fix" and int(m.get("attempt", 1)) == 1),
            triage_count=sum(1 for m in markers if m.get("stage") == "triage"),
            triage_verdict="retry" if "triage:retry" in labels else None,
        )

    # Stories merged in an earlier sprint satisfy a dependency without being in this one.
    # Only the branch the spec names counts, as everywhere else.
    by_branch = {f"story/{sid}-{spec.slug}": sid for sid, spec in specs.items()}
    merged_elsewhere = {by_branch[p["headRefName"]] for p in prs
                        if p.get("state") == "MERGED" and p.get("baseRefName") == default_branch
                        and not p.get("isCrossRepository") and p.get("headRefName") in by_branch} - set(stories)

    raw = gh("api", "--paginate", f"repos/{repo}/branches?per_page=100", "--jq", '.[] | [.name, .commit.sha] | @tsv', check=False)
    branches = [tuple(line.split("\t", 1)) for line in raw.splitlines() if "\t" in line]

    main_checks = gh_json("api", f"repos/{repo}/commits/{default_branch}/check-runs", "--jq", ".check_runs", default=[]) or []
    main_red = any(check_name(c) == "ci" and c.get("conclusion") == "failure" for c in main_checks)
    fix_main = gh_json("issue", "list", "--label", "fix-main", "--state", "open", "--json", "number", default=[])

    story_branches = {f"story/{sid}-{spec.slug}" for sid, spec in specs.items()}
    state = State(
        stories=stories,
        now=time.time(),
        paused=paused,
        pause_reason=pause_reason,
        armed_prs=sorted(p["number"] for p in prs if p.get("state") == "OPEN" and p.get("autoMergeRequest")),
        main_red=main_red,
        main_fix_in_flight=bool(fix_main),
        prs_opened_today=prs_today,
        quota_until={k: float(v) for k, v in quota.items()},
        notified=notified,
        next_sprint_drafted=f"next-sprint/{sprint_id}" in notified,
        roadmap_pending=roadmap_pending,
        open_spec_prs=open_spec_prs,
        last_po_dispatch=last_po,
        merged_elsewhere=merged_elsewhere,
        unopened_branches=unopened_branches(branches, prs, default_branch, story_branches),
        approved_prs=approved_decision_prs(prs, default_branch),
    )
    context = {"repo": repo, "default_branch": default_branch, "sprint": sprint_id, "config": cfg,
               "sprint_issue": sprint_issue["number"],
               "issues": {sid: issue["number"] for sid, issue in issues.items()}, "specs": specs,
               "prs": {sid: s.pr.number for sid, s in stories.items() if s.pr and not s.pr.merged},
               "shas": {sid: s.pr.head_sha for sid, s in stories.items() if s.pr},
               "pr_shas": {str(p["number"]): p.get("headRefOid", "") for p in prs if p.get("state") == "OPEN"},
               "assignees": {sid: s.assignee for sid, s in stories.items() if s.assignee != "default"}}
    return state, context


PROMPT_FILE = {"fix": "impl", "resolve-conflict": "impl", "fix-main": "impl"}


def _prompt(action: Action, context: dict) -> str:
    from . import prompts

    cfg = context["config"]
    spec = context["specs"].get(action.story)
    lines = [prompts.render(PROMPT_FILE.get(action.stage, action.stage), cfg), "", "---", "",
             "Follow the instructions above exactly. Read AGENTS.md first."]
    if action.stage in PROMPT_FILE:
        lines.append(f"You are dispatched as `{action.stage}`; see the matching section at the end of the instructions.")
    if spec:
        lines.append(f"Story: {action.story}. Spec: {cfg['paths']['specs']}/{spec.path.name}/. Branch: story/{action.story}-{spec.slug}.")
        lines.append(f"Story issue: #{context['issues'][action.story]}.")
    else:
        lines.append(f"Sprint: {context['sprint']}. Sprint issue: #{context['sprint_issue']}.")
    if action.stage == "product-owner":
        lines.append(f"Mode: async. Take the first unchecked line of {cfg['paths']['roadmap']}.")
    if action.stage == "fix-main":
        lines.append("The default branch is failing its checks. Find the cause, fix it on a branch named chore/fix-main and push.")
    sha = context.get("shas", {}).get(action.story, "")
    if action.stage == "review" and sha:
        lines.append(f"Review commit {sha} and no other. If the head of the pull request is a different commit "
                     "when you start, stop and report nothing: a review of the new commit will be asked for.")
    lines.append(f"Attempt: {action.attempt}." + (f" Reason for this run: {action.reason}." if action.reason else ""))
    return "\n".join(lines)


def developer_key(login: str) -> str:
    """A GitHub login as it appears in secret names and runner labels: ALICE_SMITH."""
    return re.sub(r"[^A-Za-z0-9]", "_", login or "").upper()


def secret(name: str, developer: str = "") -> str:
    """A credential for one developer's subscription.

    Each developer's stories run on that developer's own subscriptions, so the
    trigger URLs and tokens are per developer: NAME_<LOGIN>. The plain NAME is
    used for a story that names no developer (sprint assignee "default"), and on
    a developer's own Mac for that developer's stories. It is never a fallback
    for another named developer: that would run their story on someone else's
    subscription without anyone noticing.
    On GitHub Actions the secrets arrive together in CONDUCTOR_SECRETS (the
    secrets context as JSON); in a terminal they come from the environment.
    """
    try:
        pool = json.loads(os.environ.get("CONDUCTOR_SECRETS") or "{}")
    except json.JSONDecodeError:
        pool = {}
    keys = [f"{name}_{developer_key(developer)}"] if developer else [name]
    if developer and developer == os.environ.get("CONDUCTOR_LOCAL_DEVELOPER"):
        keys.append(name)
    for key in keys:
        value = pool.get(key) or os.environ.get(key)
        if value:
            return value
    return ""


def preflight(action: Action, context: dict, roles: dict) -> None:
    """Raise now if this dispatch cannot be sent from here.

    Checked before anything is written, so a stage that has to wait (for another
    developer's machine) leaves no marker and no comment behind, however many
    passes it waits.
    """
    if not NAME_RE.match(action.stage) or not NAME_RE.match(action.harness):
        raise SystemExit(f"refusing to dispatch: bad stage or harness name ({action.stage!r}, {action.harness!r})")
    harness = roles.get("harness", {}).get(action.harness, {})
    developer = context.get("assignees", {}).get(action.story, "")
    who = f" and developer '{developer}'" if developer else ""
    via = harness.get("via", "")
    local = os.environ.get("CONDUCTOR_LOCAL_DEVELOPER", "")
    if local and developer and developer != local:
        # A conductor on one person's Mac holds that person's credentials only.
        raise Deferred(f"story {action.story} belongs to {developer}; this conductor runs for {local}")
    if action.stage == "review" and harness.get("review_workflow"):
        if not context.get("prs", {}).get(action.story):
            raise SystemExit(f"story {action.story} has no open pull request to review")
        # On Actions the conductor can see whether the review job will find its token.
        token_env = harness.get("review_token_env", "CLAUDE_CODE_OAUTH_TOKEN")
        if os.environ.get("CONDUCTOR_SECRETS") and not secret(token_env, developer):
            raise SystemExit(f"no {token_env} configured for the review{who}")
    elif via == "sbx":
        if not local:
            raise SystemExit(f"harness '{action.harness}' runs in a local sandbox, which only `agentctl conductor` starts")
    elif via == "comment":
        if not secret(harness.get("token_env", "DISPATCH_TOKEN"), developer):
            raise SystemExit(f"no dispatch token configured for harness '{action.harness}'{who}")
    elif via == "http":
        if not secret(harness.get("url_env", "CLAUDE_TRIGGER_URL"), developer).startswith("https://"):
            raise SystemExit(f"no https trigger URL configured for harness '{action.harness}'{who}")
    elif via not in ("sbx", "comment", "http"):
        raise SystemExit(f"unknown dispatch method '{via}' for harness '{action.harness}'")


def _send(action: Action, context: dict, roles: dict) -> None:
    """Hand the work to a harness. `via` is configured per harness in [roles.harness]."""
    harness = roles.get("harness", {}).get(action.harness, {})
    developer = context.get("assignees", {}).get(action.story, "")
    via = harness.get("via", "")
    prompt = _prompt(action, context)
    issue = str(context["issues"].get(action.story, context["sprint_issue"]))
    pr = context.get("prs", {}).get(action.story)

    if action.stage == "review" and harness.get("review_workflow"):
        # A review that runs as a workflow job is published by a job the implementing
        # agent has no way to influence.
        # The commit is the one recorded in the dispatch marker. The job refuses to
        # review any other, so a push made while it was queued gets its own review.
        gh("workflow", "run", harness["review_workflow"], "--ref", context["default_branch"],
           "-f", f"pr={pr}", "-f", f"story={action.story}", "-f", f"developer={developer_key(developer)}",
           "-f", f"sha={context.get('shas', {}).get(action.story, '')}")
    elif via == "sbx":
        # A clone-mode Docker Sandbox on this Mac, started by the kit's own copy of the
        # script: the installed kit, never a file from the project's tree.
        script = KIT_ROOT / "sandbox" / "sbx.sh"
        subprocess.Popen([str(script), "job", action.harness, action.story or "sprint", action.stage, prompt],
                         cwd="/", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    elif via == "comment":
        # Cloud agents that start from a mention (for example Codex cloud). The comment
        # must come from the developer whose subscription runs the task.
        token = secret(harness.get("token_env", "DISPATCH_TOKEN"), developer)
        mention = harness.get("mention", "@codex")
        # Once the story has a pull request, the mention goes there so the agent has the diff in context.
        gh("issue", "comment", str(pr or issue), "--body", f"{mention} {prompt}", token=token)
    elif via == "http":
        # Cloud scheduled task with an API trigger (for example Claude Code on the web).
        url = secret(harness.get("url_env", "CLAUDE_TRIGGER_URL"), developer)
        token = secret(harness.get("token_env", "CLAUDE_TRIGGER_TOKEN"), developer)
        request = urllib.request.Request(
            url, data=json.dumps({"text": prompt}).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        urllib.request.urlopen(request, timeout=30).read()


def execute(actions: list[Action], context: dict, roles: dict, dry_run: bool = False) -> int:
    """Carry out the actions. One failing action does not stop the others.

    Returns the number of actions that failed.
    """
    failures = 0
    for action in actions:
        print(("DRY-RUN " if dry_run else "") + str(action))
        if dry_run or action.kind == "halt":
            continue
        try:
            _execute_one(action, context, roles)
        except Deferred as exc:
            print(f"  deferred: {exc}")
        except (subprocess.CalledProcessError, OSError, KeyError, SystemExit) as exc:
            failures += 1
            detail = (getattr(exc, "stderr", "") or str(exc)).strip().splitlines()[-1:] or [type(exc).__name__]
            print(f"  FAILED: {detail[0]}")
    return failures


def _dispatch(action: Action, context: dict, roles: dict) -> None:
    """Record the dispatch, then send it; withdraw the record if sending fails.

    Recording first means a crash between the two steps leaves a marker without a
    session (the stage is retried after its timeout) rather than a session without
    a marker (the same work launched twice).
    """
    preflight(action, context, roles)
    issue = str(context["issues"].get(action.story, context["sprint_issue"]))
    marker_id = uuid.uuid4().hex[:12]
    marker = {"id": marker_id, "stage": action.stage, "at": time.time(), "harness": action.harness,
              "attempt": action.attempt, "sha": context.get("shas", {}).get(action.story, "")}
    if action.story:
        # A completion label left over from an earlier round must not count for this one.
        gh("issue", "edit", issue, "--remove-label", f"done:{action.stage}", check=False)
        if action.stage == "triage" or action.reason == "triage asked for a retry":
            gh("issue", "edit", issue, "--remove-label", "triage:retry", check=False)
    gh("issue", "comment", issue, "--body",
       f"<!-- conductor {json.dumps(marker)} -->\nDispatching **{action.stage}** to {action.harness} (attempt {action.attempt}). {action.reason}")
    try:
        _send(action, context, roles)
    except BaseException:
        cancel = json.dumps({"cancel": marker_id})
        gh("issue", "comment", issue, "--body", f"<!-- conductor {cancel} -->\nThat dispatch did not start.", check=False)
        raise


def _open_pr(branch: str, context: dict) -> None:
    if not SAFE_BRANCH_RE.match(branch):
        raise SystemExit(f"refusing to open a pull request for branch {branch!r}")
    repo, base = context["repo"], context["default_branch"]
    story = ids.STORY_BRANCH_RE.match(branch)
    if story:
        spec = context["specs"].get(story.group(1))
        title = f"Story {story.group(1)}: {spec.title}" if spec else f"Story {story.group(1)}"
    else:
        title = branch
    # Story branches open as drafts: a draft only gets lint, and the conductor marks
    # it ready once the implementation stage is done.
    args = ["api", f"repos/{repo}/pulls", "-f", f"title={title}", "-f", f"head={branch}", "-f", f"base={base}",
            "-f", f"body=Opened by the conductor for branch `{branch}`.", "-F", f"draft={'true' if story else 'false'}",
            "--jq", ".number"]
    gh(*args)


def _execute_one(action: Action, context: dict, roles: dict) -> None:
    sprint_issue = str(context["sprint_issue"])
    issue = str(context["issues"].get(action.story, context["sprint_issue"]))
    pr = context.get("prs", {}).get(action.story)
    mention = " ".join(f"@{h}" for h in roles.get("humans", []))

    if action.kind == "dispatch":
        if action.stage == "fix-main":
            preflight(action, context, roles)
            _send(action, context, roles)
            gh("label", "create", "fix-main", "--force", check=False)
            gh("issue", "create", "--title", "main is red", "--label", "fix-main",
               "--body", "The conductor stopped dispatching until main is green again.")
        else:
            _dispatch(action, context, roles)
    elif action.kind == "draft-next-sprint":
        planner = Action("dispatch", stage="planner", harness=roles.get("planner", "claude"), attempt=1, reason=action.reason)
        _dispatch(planner, context, roles)
        gh("issue", "comment", sprint_issue, "--body",
           f"<!-- conductor-notified next-sprint/{context['sprint']} -->\nDrafting the next sprint.")
    elif action.kind == "open-pr":
        _open_pr(action.reason, context)
    elif action.kind == "mark-ready":
        if pr:
            gh("pr", "ready", str(pr))
    elif action.kind == "update-branch":
        if pr:
            gh("api", "--method", "PUT", f"repos/{context['repo']}/pulls/{pr}/update-branch")
    elif action.kind == "enable-auto-merge":
        number = str(pr) if pr else action.reason.lstrip("#")
        sha = context.get("pr_shas", {}).get(number, "")
        if number.isdigit() and sha:
            # Only the commit this decision was made about. If the branch moved in the
            # meantime, GitHub refuses and the next pass decides again.
            gh("pr", "merge", number, "--auto", "--squash", "--match-head-commit", sha)
    elif action.kind == "disable-auto-merge":
        number = str(pr) if pr else action.reason.lstrip("#")
        if number.isdigit():
            gh("pr", "merge", number, "--disable-auto")
    elif action.kind == "escalate":
        # Mention, do not assign: assignees are not how the conductor knows whose story it is,
        # but changing them would still be confusing.
        gh("label", "create", "needs-human", "--force", check=False)
        gh("issue", "edit", issue, "--add-label", "needs-human")
        marker = "" if action.story else "<!-- conductor-notified sprint-escalated -->\n"
        gh("issue", "comment", issue, "--body", f"{marker}{mention} Needs a human decision: {action.reason}")
    elif action.kind == "notify":
        key = f"ready-to-merge/{action.story}" if action.story else (
            "sprint-complete" if "complete" in action.reason else "sprint-stalled")
        gh("issue", "comment", sprint_issue, "--body", f"<!-- conductor-notified {key} -->\n{mention} {action.reason}"
           + (f" (story {action.story})" if action.story else ""))
