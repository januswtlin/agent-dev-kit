"""GitHub adapter for the conductor: observe state, execute actions.

Everything goes through the `gh` CLI. All conductor memory is kept on GitHub
itself as hidden marker comments, labels and issue links, so this module holds
no state between runs.

Trust rules for what is read back:
  - marker comments count only when written by the conductor itself or by a
    human listed in policy/roles.toml. An agent can comment on issues, so a
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

from .reconcile import PR, Action, Dispatch, State, Story
from .specs import load_all

MARKER_RE = re.compile(r"<!-- conductor (\{.*?\}) -->", re.DOTALL)
NOTIFIED_RE = re.compile(r"<!-- conductor-notified ([\w:/.-]+) -->")
BRANCH_PREFIXES = ("story/", "spec/", "sprint/", "chore/")
STORY_BRANCH_RE = re.compile(r"^story/(\d{3})(?:-[A-Za-z0-9._-]*)?$")
SAFE_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,120}$")
NAME_RE = re.compile(r"^[a-z][a-z-]{1,30}$")


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


def variable(name: str) -> str:
    """A repository variable, read live. Falls back to the environment (tests, old gh)."""
    try:
        return gh("variable", "get", name).strip()
    except (subprocess.CalledProcessError, OSError):
        return os.environ.get(name, "")


def active_sprint(repo_root: Path) -> tuple[str, dict]:
    """The highest-numbered sprint file on the default branch is the active sprint."""
    files = sorted(p for p in (repo_root / "docs/sprints").glob("[0-9][0-9][0-9].toml"))
    if not files:
        raise SystemExit("no sprint file in docs/sprints/")
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


def trusted_authors(roles: dict) -> set[str]:
    """Logins whose marker comments are believed: the conductor and the humans."""
    logins = {str(h) for h in roles.get("humans", [])}
    for bot in (os.environ.get("CONDUCTOR_BOT", ""), variable("CONDUCTOR_BOT")):
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


def select_pr(prs: list[dict], story_id: str, default_branch: str) -> dict | None:
    """The story's pull request: open first, else merged; same repository, default base."""
    mine = [p for p in prs
            if (m := STORY_BRANCH_RE.match(p.get("headRefName", ""))) and m.group(1) == story_id
            and p.get("baseRefName") == default_branch and not p.get("isCrossRepository")]
    for state in ("OPEN", "MERGED"):
        candidates = [p for p in mine if p.get("state") == state]
        if candidates:
            return max(candidates, key=lambda p: p["number"])
    return None


def unopened_branches(branches: list[tuple[str, str]], prs: list[dict], default_branch: str) -> list[str]:
    """Agent branches that have no pull request for their current tip yet."""
    result = []
    for name, sha in branches:
        if not name.startswith(BRANCH_PREFIXES) or not SAFE_BRANCH_RE.match(name):
            continue
        covered = any(p.get("headRefName") == name and not p.get("isCrossRepository")
                      and (p.get("state") == "OPEN" or p.get("headRefOid") == sha) for p in prs)
        if not covered:
            result.append(name)
    return sorted(result)


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


def collect(repo_root: Path, roles: dict, read_only: bool = False) -> tuple[State, dict]:
    """Build the State the planner needs, plus a context dict for the executor."""
    sprint_id, sprint = active_sprint(repo_root)
    specs = load_all(repo_root / "docs/specs")
    view = gh_json("repo", "view", "--json", "nameWithOwner,defaultBranchRef")
    repo = view["nameWithOwner"]
    default_branch = (view.get("defaultBranchRef") or {}).get("name") or "main"
    default_owner = str(sprint.get("assignee", "default"))
    owners = {str(k): str(v) for k, v in (sprint.get("owners") or {}).items()}
    authors = trusted_authors(roles)

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

    roadmap = repo_root / "docs/product/roadmap.md"
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
        if not re.fullmatch(r"\d{3}", sid):
            raise SystemExit(f"sprint {sprint_id}: '{sid}' is not a story id (three digits)")
        spec = specs.get(sid)
        title = f"Story {sid}: {spec.title if spec else '(spec missing)'}"
        issue = ensure_issue(f"story:{sid}", title, f"Runtime state for story {sid}. Spec: docs/specs/{sid}-*/", read_only)
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
        p = select_pr(prs, sid, default_branch)
        if p:
            pr_labels = {label["name"] for label in p.get("labels", [])}
            tier = next((name.split(":", 1)[1] for name in pr_labels if name.startswith("tier:")), "T1")
            pr = PR(
                number=p["number"],
                merged=p.get("state") == "MERGED",
                checks={(c.get("name") or c.get("context") or ""): _check_state(c) for c in p.get("statusCheckRollup") or []},
                behind=p.get("mergeStateStatus") == "BEHIND",
                conflicted=p.get("mergeable") == "CONFLICTING",
                auto_merge=bool(p.get("autoMergeRequest")),
                awaiting_human_review=p.get("reviewDecision") in ("REVIEW_REQUIRED", "CHANGES_REQUESTED"),
                tier=tier,
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
    merged_elsewhere = {m.group(1) for p in prs if p.get("state") == "MERGED" and p.get("baseRefName") == default_branch
                        and not p.get("isCrossRepository") and (m := STORY_BRANCH_RE.match(p.get("headRefName", "")))} - set(stories)

    raw = gh("api", "--paginate", f"repos/{repo}/branches?per_page=100", "--jq", '.[] | [.name, .commit.sha] | @tsv', check=False)
    branches = [tuple(line.split("\t", 1)) for line in raw.splitlines() if "\t" in line]

    main_checks = gh_json("api", f"repos/{repo}/commits/{default_branch}/check-runs", "--jq", ".check_runs", default=[]) or []
    main_red = any(c.get("name") == "ci" and c.get("conclusion") == "failure" for c in main_checks)
    fix_main = gh_json("issue", "list", "--label", "fix-main", "--state", "open", "--json", "number", default=[])

    try:
        quota = json.loads(variable("CONDUCTOR_QUOTA") or "{}")
    except json.JSONDecodeError:
        quota = {}
    state = State(
        stories=stories,
        now=time.time(),
        paused=variable("CONDUCTOR_PAUSED").lower() in ("1", "true", "yes"),
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
        unopened_branches=unopened_branches(branches, prs, default_branch),
        approved_prs=approved_decision_prs(prs, default_branch),
    )
    context = {"repo": repo, "default_branch": default_branch, "sprint": sprint_id,
               "sprint_issue": sprint_issue["number"],
               "issues": {sid: issue["number"] for sid, issue in issues.items()}, "specs": specs,
               "prs": {sid: s.pr.number for sid, s in stories.items() if s.pr and not s.pr.merged},
               "shas": {sid: s.pr.head_sha for sid, s in stories.items() if s.pr},
               "assignees": {sid: s.assignee for sid, s in stories.items() if s.assignee != "default"}}
    return state, context


PROMPT_FILE = {"fix": "impl", "resolve-conflict": "impl", "fix-main": "impl"}


def _prompt(action: Action, context: dict) -> str:
    spec = context["specs"].get(action.story)
    lines = [f"Follow prompts/{PROMPT_FILE.get(action.stage, action.stage)}.md exactly. Read AGENTS.md first."]
    if action.stage in PROMPT_FILE:
        lines.append(f"You are dispatched as `{action.stage}`; see the matching section at the end of that file.")
    if spec:
        lines.append(f"Story: {action.story}. Spec: docs/specs/{spec.path.name}/. Branch: story/{action.story}-{spec.slug}.")
        lines.append(f"Story issue: #{context['issues'][action.story]}.")
    else:
        lines.append(f"Sprint: {context['sprint']}. Sprint issue: #{context['sprint_issue']}.")
    if action.stage == "product-owner":
        lines.append("Mode: async. Take the first unchecked line of docs/product/roadmap.md.")
    if action.stage == "fix-main":
        lines.append("The default branch is failing its checks. Find the cause, fix it on a branch named chore/fix-main and push.")
    lines.append(f"Attempt: {action.attempt}." + (f" Reason for this run: {action.reason}." if action.reason else ""))
    return "\n".join(lines)


def developer_key(login: str) -> str:
    """A GitHub login as it appears in secret names and runner labels: ALICE_SMITH."""
    return re.sub(r"[^A-Za-z0-9]", "_", login or "").upper()


def secret(name: str, developer: str = "") -> str:
    """A credential for one developer's subscription, falling back to a shared one.

    Each developer's stories run on that developer's own subscriptions, so the
    trigger URLs and tokens are per developer: NAME_<LOGIN> wins over NAME.
    On GitHub Actions they arrive together in CONDUCTOR_SECRETS (the secrets
    context as JSON); in a terminal they come from the environment.
    """
    try:
        pool = json.loads(os.environ.get("CONDUCTOR_SECRETS") or "{}")
    except json.JSONDecodeError:
        pool = {}
    for key in ([f"{name}_{developer_key(developer)}"] if developer else []) + [name]:
        value = pool.get(key) or os.environ.get(key)
        if value:
            return value
    return ""


def preflight(action: Action, context: dict, roles: dict) -> None:
    """Raise now if this dispatch cannot be sent from here.

    Checked before anything is written, so a stage that has to wait (for the
    local conductor, for another developer's machine) leaves no marker and no
    comment behind, however many passes it waits.
    """
    if not NAME_RE.match(action.stage) or not NAME_RE.match(action.harness):
        raise SystemExit(f"refusing to dispatch: bad stage or harness name ({action.stage!r}, {action.harness!r})")
    harness = roles.get("harness", {}).get(action.harness, {})
    developer = context.get("assignees", {}).get(action.story, "")
    who = f" and developer '{developer}'" if developer else ""
    via = harness.get("via", "workflow")
    local = os.environ.get("CONDUCTOR_LOCAL_DEVELOPER", "")
    if local and developer and developer != local:
        # A conductor on one person's Mac holds that person's credentials only.
        raise Deferred(f"story {action.story} belongs to {developer}; this conductor runs for {local}")
    if action.stage == "review" and harness.get("review_workflow"):
        if not context.get("prs", {}).get(action.story):
            raise SystemExit(f"story {action.story} has no open pull request to review")
    elif via == "sbx":
        if os.environ.get("GITHUB_ACTIONS") or not local:
            raise Deferred(f"harness '{action.harness}' runs in a local sandbox; waiting for `agentctl conductor here`")
        if not os.environ.get("AGENTCTL_TRUSTED_SCRIPTS"):
            raise SystemExit("AGENTCTL_TRUSTED_SCRIPTS is not set; local sandboxes are started by `agentctl conductor here`")
    elif via == "comment":
        if not secret(harness.get("token_env", "DISPATCH_TOKEN"), developer):
            raise SystemExit(f"no dispatch token configured for harness '{action.harness}'{who}")
    elif via == "http":
        if not secret(harness.get("url_env", "CLAUDE_TRIGGER_URL"), developer).startswith("https://"):
            raise SystemExit(f"no https trigger URL configured for harness '{action.harness}'{who}")
    elif via != "workflow":
        raise SystemExit(f"unknown dispatch method '{via}' for harness '{action.harness}'")


def _send(action: Action, context: dict, roles: dict) -> None:
    """Hand the work to a harness. `via` is configured per harness in policy/roles.toml."""
    harness = roles.get("harness", {}).get(action.harness, {})
    developer = context.get("assignees", {}).get(action.story, "")
    via = harness.get("via", "workflow")
    prompt = _prompt(action, context)
    issue = str(context["issues"].get(action.story, context["sprint_issue"]))
    pr = context.get("prs", {}).get(action.story)

    if action.stage == "review" and harness.get("review_workflow"):
        # A review that runs as a workflow job is published by a job the implementing
        # agent has no way to influence.
        gh("workflow", "run", harness["review_workflow"], "--ref", context["default_branch"],
           "-f", f"pr={pr}", "-f", f"story={action.story}", "-f", f"developer={developer_key(developer)}")
    elif via == "sbx":
        # A clone-mode Docker Sandbox on a developer's Mac. Only a conductor running on
        # THAT developer's Mac can start one; from anywhere else the stage waits.
        script = Path(os.environ["AGENTCTL_TRUSTED_SCRIPTS"]) / "sandbox" / "sbx.sh"
        subprocess.Popen([str(script), "job", action.harness, action.story or "sprint", action.stage, prompt],
                         cwd="/", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    elif via == "workflow":
        # Self-hosted runner in a developer's VM. Not part of the supported setup path.
        gh("workflow", "run", "agent-job.yml", "--ref", context["default_branch"],
           "-f", f"story={action.story}", "-f", f"stage={action.stage}",
           "-f", f"harness={action.harness}", "-f", f"prompt={prompt}", "-f", f"developer={developer}")
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
    story = STORY_BRANCH_RE.match(branch)
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
        if number.isdigit():
            gh("pr", "merge", number, "--auto", "--squash")
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
