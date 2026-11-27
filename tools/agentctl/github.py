"""GitHub adapter for the conductor: observe state, execute actions.

Everything goes through the `gh` CLI. All conductor memory is kept on GitHub
itself as hidden marker comments, labels and issue links, so this module holds
no state between runs.

NOTE: this adapter has not been exercised against a live repository yet.
The pure scheduling logic it feeds (reconcile.plan) is unit-tested; the calls
here are to be validated in the spike described in docs/runbook.md.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import tomllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .reconcile import PR, Action, Dispatch, State, Story
from .specs import load_all

MARKER_RE = re.compile(r"<!-- conductor (\{.*?\}) -->", re.DOTALL)
NOTIFIED_RE = re.compile(r"<!-- conductor-notified ([\w:/.-]+) -->")


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


def ensure_issue(label: str, title: str, body: str) -> dict:
    found = gh_json("issue", "list", "--label", label, "--state", "all", "--limit", "1",
                    "--json", "number,labels,comments,assignees", default=[])
    if found:
        return found[0]
    gh("label", "create", label, "--force", check=False)
    gh("issue", "create", "--title", title, "--body", body, "--label", label)
    return gh_json("issue", "list", "--label", label, "--state", "all", "--limit", "1",
                   "--json", "number,labels,comments,assignees", default=[{}])[0]


def collect(repo_root: Path) -> tuple[State, dict]:
    """Build the State the planner needs, plus a context dict for the executor."""
    sprint_id, sprint = active_sprint(repo_root)
    specs = load_all(repo_root / "docs/specs")
    repo = gh_json("repo", "view", "--json", "nameWithOwner")["nameWithOwner"]
    default_assignee = sprint.get("assignee", "default")

    prs = gh_json(
        "pr", "list", "--state", "all", "--limit", "200", "--json",
        "number,headRefName,state,isDraft,mergedAt,createdAt,mergeable,mergeStateStatus,labels,"
        "autoMergeRequest,reviewDecision,statusCheckRollup", default=[],
    )
    today = datetime.now(timezone.utc).date()
    prs_today = sum(1 for p in prs if p["headRefName"].startswith("story/") and _epoch(p["createdAt"]) and
                    datetime.fromtimestamp(_epoch(p["createdAt"]), timezone.utc).date() == today)

    sprint_issue = ensure_issue(f"sprint:{sprint_id}", f"Sprint {sprint_id}", "Conductor notifications for this sprint.")
    notified = set()
    last_po = None
    for comment in sprint_issue.get("comments", []):
        notified.update(NOTIFIED_RE.findall(comment.get("body", "")))
        for raw in MARKER_RE.findall(comment.get("body", "")):
            try:
                marker = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if marker.get("stage") == "product-owner":
                last_po = float(marker["at"])

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
        spec = specs.get(sid)
        title = f"Story {sid}: {spec.title if spec else '(spec missing)'}"
        issue = ensure_issue(f"story:{sid}", title, f"Runtime state for story {sid}. Spec: docs/specs/{sid}-*/")
        issues[sid] = issue
        issue_to_story[issue["number"]] = sid

    stories: dict[str, Story] = {}
    for sid, issue in issues.items():
        spec = specs.get(sid)
        labels = {label["name"] for label in issue.get("labels", [])}
        markers = []
        for comment in issue.get("comments", []):
            for raw in MARKER_RE.findall(comment.get("body", "")):
                try:
                    markers.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
        last = markers[-1] if markers else None
        impl = [m for m in markers if m.get("stage") == "impl"]

        pr = None
        mine = [p for p in prs if p["headRefName"].startswith(f"story/{sid}-") or p["headRefName"] == f"story/{sid}"]
        if mine:
            p = max(mine, key=lambda x: x["number"])
            pr_labels = {label["name"] for label in p.get("labels", [])}
            tier = next((name.split(":", 1)[1] for name in pr_labels if name.startswith("tier:")), "T1")
            pr = PR(
                number=p["number"],
                merged=bool(p.get("mergedAt")),
                checks={(c.get("name") or c.get("context") or ""): _check_state(c) for c in p.get("statusCheckRollup") or []},
                behind=p.get("mergeStateStatus") == "BEHIND",
                conflicted=p.get("mergeable") == "CONFLICTING",
                auto_merge=bool(p.get("autoMergeRequest")),
                awaiting_human_review=p.get("reviewDecision") == "REVIEW_REQUIRED",
                tier=tier,
                draft=bool(p.get("isDraft")),
            )

        blocked = gh_json("api", f"repos/{repo}/issues/{issue['number']}/dependencies/blocked_by", default=[]) or []
        blocked_by = sorted({issue_to_story[b["number"]] for b in blocked
                             if b.get("state") == "open" and b.get("number") in issue_to_story})

        assignees = [a["login"] for a in issue.get("assignees", [])]
        stories[sid] = Story(
            id=sid,
            priority=spec.priority if spec else 100,
            depends_on=[d for d in (spec.depends_on if spec else [])],
            blocked_by=blocked_by,
            touches=list(spec.touches) if spec else [],
            assignee=assignees[0] if assignees else default_assignee,
            labels=labels & {"needs-human", "blocked"},
            pr=pr,
            stage_done={name.split(":", 1)[1] for name in labels if name.startswith("done:")},
            last_dispatch=Dispatch(last["stage"], float(last["at"]), last.get("harness", ""), int(last.get("attempt", 1))) if last else None,
            impl_harness=impl[-1].get("harness", "") if impl else "",
            fix_rounds=sum(1 for m in markers if m.get("stage") == "fix" and int(m.get("attempt", 1)) == 1),
            triage_count=sum(1 for m in markers if m.get("stage") == "triage"),
            triage_verdict="retry" if "triage:retry" in labels else None,
        )

    # Stories outside the sprint that sprint stories depend on count as done when merged earlier.
    main_checks = gh_json("api", f"repos/{repo}/commits/HEAD/check-runs", "--jq", ".check_runs", default=[]) or []
    main_red = any(c.get("name") == "ci" and c.get("conclusion") == "failure" for c in main_checks)
    fix_main = gh_json("issue", "list", "--label", "fix-main", "--state", "open", "--json", "number", default=[])

    quota = json.loads(os.environ.get("CONDUCTOR_QUOTA") or "{}")
    state = State(
        stories=stories,
        now=time.time(),
        paused=os.environ.get("CONDUCTOR_PAUSED", "").lower() in ("1", "true", "yes"),
        main_red=main_red,
        main_fix_in_flight=bool(fix_main),
        prs_opened_today=prs_today,
        quota_until={k: float(v) for k, v in quota.items()},
        notified=notified,
        next_sprint_drafted=f"next-sprint/{sprint_id}" in notified,
        roadmap_pending=roadmap_pending,
        open_spec_prs=open_spec_prs,
        last_po_dispatch=last_po,
    )
    context = {"repo": repo, "sprint": sprint_id, "sprint_issue": sprint_issue["number"],
               "issues": {sid: issue["number"] for sid, issue in issues.items()}, "specs": specs,
               "prs": {sid: s.pr.number for sid, s in stories.items() if s.pr},
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


class Deferred(Exception):
    """This action cannot be carried out from here; another conductor run will do it."""


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


def _send(action: Action, context: dict, roles: dict) -> None:
    """Hand the work to a harness. `via` is configured per harness in policy/roles.toml."""
    harness = roles.get("harness", {}).get(action.harness, {})
    developer = context.get("assignees", {}).get(action.story, "")
    via = harness.get("via", "workflow")
    prompt = _prompt(action, context)
    issue = str(context["issues"].get(action.story, context["sprint_issue"]))

    if action.stage == "review" and harness.get("review_workflow"):
        # A review that runs as a workflow job can set the agent-review status itself,
        # which the implementing agent has no permission to do.
        pr = gh_json("pr", "list", "--search", f"head:story/{action.story}", "--json", "number", default=[])
        if not pr:
            raise SystemExit(f"story {action.story} has no open pull request to review")
        gh("workflow", "run", harness["review_workflow"], "-f", f"pr={pr[0]['number']}", "-f", f"story={action.story}",
           "-f", f"developer={developer_key(developer)}")
    elif via == "sbx":
        # A clone-mode Docker Sandbox on this Mac. Only the local conductor can start
        # one; on GitHub Actions the stage waits until a conductor runs here again.
        if os.environ.get("GITHUB_ACTIONS"):
            raise Deferred(f"harness '{action.harness}' runs in a local sandbox; waiting for `agentctl conductor here`")
        script = Path(os.environ.get("AGENTCTL_TRUSTED_SCRIPTS") or ".") / "sandbox" / "sbx.sh"
        subprocess.Popen([str(script), "job", action.harness, action.story or "sprint", action.stage, prompt],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    elif via == "workflow":
        # GitHub-hosted (claude-code-action) or self-hosted runner in the sandbox VM.
        gh("workflow", "run", "agent-job.yml", "-f", f"story={action.story}", "-f", f"stage={action.stage}",
           "-f", f"harness={action.harness}", "-f", f"prompt={prompt}", "-f", f"developer={developer}")
    elif via == "comment":
        # Cloud agents that start from a mention (for example Codex cloud). The comment
        # must come from the developer whose subscription runs the task.
        token = secret(harness.get("token_env", "DISPATCH_TOKEN"), developer) or None
        mention = harness.get("mention", "@codex")
        # Once the story has a pull request, the mention goes there so the agent has the diff in context.
        target = str(context.get("prs", {}).get(action.story) or issue)
        gh("issue", "comment", target, "--body", f"{mention} {prompt}", token=token)
    elif via == "http":
        # Cloud scheduled task with an API trigger (for example Claude Code on the web).
        url = secret(harness.get("url_env", "CLAUDE_TRIGGER_URL"), developer)
        if not url:
            raise SystemExit(f"no trigger URL configured for harness '{action.harness}'" + (f" and developer '{developer}'" if developer else ""))
        token = secret(harness.get("token_env", "CLAUDE_TRIGGER_TOKEN"), developer)
        request = urllib.request.Request(
            url, data=json.dumps({"text": prompt}).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        urllib.request.urlopen(request, timeout=30).read()
    else:
        raise SystemExit(f"unknown dispatch method '{via}' for harness '{action.harness}'")


def execute(actions: list[Action], context: dict, roles: dict, dry_run: bool = False) -> int:
    """Carry out the actions. One failing action does not stop the others.

    A dispatch that fails leaves no marker, so the next run plans it again.
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


def _execute_one(action: Action, context: dict, roles: dict) -> None:
    sprint_issue = str(context["sprint_issue"])
    issue = str(context["issues"].get(action.story, context["sprint_issue"]))

    if action.kind in ("dispatch", "draft-next-sprint"):
        if action.kind == "draft-next-sprint":
            action = Action("dispatch", stage="planner", harness=roles.get("planner", "claude"), attempt=1, reason=action.reason)
            gh("issue", "comment", sprint_issue, "--body", f"<!-- conductor-notified next-sprint/{context['sprint']} -->\nDrafting the next sprint.")
        if action.stage == "fix-main":
            gh("label", "create", "fix-main", "--force", check=False)
            gh("issue", "create", "--title", "main is red", "--label", "fix-main",
               "--body", "The conductor stopped dispatching until main is green again.")
        _send(action, context, roles)
        if action.stage == "triage" or action.reason == "triage asked for a retry":
            gh("issue", "edit", issue, "--remove-label", "triage:retry", check=False)
        marker = json.dumps({"stage": action.stage, "at": time.time(), "harness": action.harness, "attempt": action.attempt})
        gh("issue", "comment", issue, "--body",
           f"<!-- conductor {marker} -->\nDispatched **{action.stage}** to {action.harness} (attempt {action.attempt}). {action.reason}")
    elif action.kind == "mark-ready":
        number = context.get("prs", {}).get(action.story)
        if number:
            gh("pr", "ready", str(number))
    elif action.kind == "update-branch":
        pr = gh_json("pr", "list", "--search", f"head:story/{action.story}", "--json", "number", default=[])
        if pr:
            gh("pr", "update-branch", str(pr[0]["number"]), check=False)
    elif action.kind == "enable-auto-merge":
        pr = gh_json("pr", "list", "--search", f"head:story/{action.story}", "--json", "number", default=[])
        if pr:
            gh("pr", "merge", str(pr[0]["number"]), "--auto", "--squash")
    elif action.kind == "escalate":
        gh("label", "create", "needs-human", "--force", check=False)
        humans = ",".join(roles.get("humans", []))
        args = ["issue", "edit", issue, "--add-label", "needs-human"]
        if humans:
            args += ["--add-assignee", humans]
        gh(*args)
        marker = "" if action.story else "<!-- conductor-notified sprint-escalated -->\n"
        gh("issue", "comment", issue, "--body", f"{marker}Needs a human decision: {action.reason}")
    elif action.kind == "notify":
        key = f"ready-to-merge/{action.story}" if action.story else (
            "sprint-complete" if "complete" in action.reason else "sprint-stalled")
        mention = " ".join(f"@{h}" for h in roles.get("humans", []))
        gh("issue", "comment", sprint_issue, "--body", f"<!-- conductor-notified {key} -->\n{mention} {action.reason}"
           + (f" (story {action.story})" if action.story else ""))
