"""Conductor core: a pure function from observed state to the next actions.

No LLM and no stored state. Every run reads the whole picture (sprint, specs,
issues, PRs, checks) and returns what should happen next, so a crashed,
repeated or missed run converges on the same result. Judgement calls are
delegated to short-lived agent sessions (triage), whose verdicts are written
back to GitHub and read here as plain state.

Ordering intelligence lives in the approved plan (priority, depends_on,
touches). This module only computes which stories are ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .specs import find_cycle

STAGES = ["design", "tests", "impl", "review"]
MECHANICAL_CHECKS = ["ci", "security", "spec-verify", "risk-gate"]
REVIEW_CHECK = "agent-review"


@dataclass
class PR:
    number: int
    merged: bool = False
    checks: dict[str, str] = field(default_factory=dict)  # name -> success | failure | pending
    behind: bool = False
    conflicted: bool = False
    auto_merge: bool = False
    awaiting_human_review: bool = False
    tier: str = "T1"
    # Story pull requests open as drafts. A draft only gets the cheap checks; the
    # full gates run once the conductor marks it ready, after the impl stage.
    draft: bool = False
    head_sha: str = ""


@dataclass
class Dispatch:
    stage: str  # one of STAGES, or fix | resolve-conflict | triage
    at: float  # epoch seconds
    harness: str = ""
    attempt: int = 1
    sha: str = ""  # the pull request's head when this was dispatched


@dataclass
class Story:
    id: str
    priority: int = 100
    depends_on: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)  # added at runtime by triage (issue links)
    touches: list[str] = field(default_factory=list)
    assignee: str = ""
    labels: set[str] = field(default_factory=set)  # needs-human, blocked
    pr: PR | None = None
    stage_done: set[str] = field(default_factory=set)
    last_dispatch: Dispatch | None = None
    impl_harness: str = ""
    fix_rounds: int = 0
    triage_count: int = 0
    triage_verdict: str | None = None  # "retry" once a triage session asked for another attempt

    @property
    def done(self) -> bool:
        return bool(self.pr and self.pr.merged)

    @property
    def started(self) -> bool:
        return self.pr is not None or self.last_dispatch is not None or bool(self.stage_done)

    @property
    def deps(self) -> set[str]:
        return set(self.depends_on) | set(self.blocked_by)


@dataclass
class State:
    stories: dict[str, Story]
    now: float
    paused: bool = False
    main_red: bool = False
    main_fix_in_flight: bool = False
    prs_opened_today: int = 0
    quota_until: dict[str, float] = field(default_factory=dict)  # "developer/harness" -> epoch
    notified: set[str] = field(default_factory=set)  # one-shot notifications already sent
    next_sprint_drafted: bool = False
    roadmap_pending: int = 0  # roadmap lines that have no spec yet
    open_spec_prs: int = 0  # spec pull requests waiting for the director
    last_po_dispatch: float | None = None
    merged_elsewhere: set[str] = field(default_factory=set)  # stories merged in an earlier sprint
    unopened_branches: list[str] = field(default_factory=list)  # agent branches with no pull request yet
    approved_prs: list[int] = field(default_factory=list)  # spec/sprint pull requests a human has approved
    armed_prs: list[int] = field(default_factory=list)  # open pull requests with auto-merge switched on
    pause_reason: str = "kill switch is on"


@dataclass(frozen=True)
class Action:
    # dispatch | open-pr | mark-ready | update-branch | enable-auto-merge | disable-auto-merge |
    # escalate | notify | halt | draft-next-sprint
    kind: str
    story: str = ""
    stage: str = ""
    harness: str = ""
    attempt: int = 0
    reason: str = ""

    def __str__(self) -> str:
        parts = [self.kind]
        if self.story:
            parts.append(f"story={self.story}")
        if self.stage:
            parts.append(f"stage={self.stage}")
        if self.harness:
            parts.append(f"harness={self.harness}")
        if self.attempt:
            parts.append(f"attempt={self.attempt}")
        if self.reason:
            parts.append(f"({self.reason})")
        return " ".join(parts)


DEFAULT_POLICY = {
    "wip_limit": 2,
    "max_prs_per_day": 10,
    "max_attempts": 2,
    "max_fix_rounds": 3,
    "max_triage": 1,
    "draft_next_sprint_at": 0.8,
    "max_open_spec_prs": 3,  # do not pile more unapproved specs than this on the director
    "auto_merge_tiers": [],  # shadow mode until T0/T1 are switched on
    "stage_timeout_minutes": {"default": 90, "triage": 30, "product-owner": 60},
}


def _timeout(policy: dict, stage: str) -> float:
    timeouts = policy.get("stage_timeout_minutes", {})
    return 60.0 * timeouts.get(stage, timeouts.get("default", 90))


BUILD_STAGES = ["design", "tests", "impl"]  # report by label; review reports by commit status


def _in_flight(story: Story) -> bool:
    """True while the last dispatched session has not reported its outcome.

    Sessions that work on an existing pull request (fix, conflict resolution,
    review) are tied to the commit they were dispatched for: they are done when
    the branch has moved on, or, for a review, when that commit has a verdict.
    Tying them to a label instead would let a stale label hide a running session,
    or a missing one launch the same fix again on every pass.
    """
    d = story.last_dispatch
    if d is None:
        return False
    pr = story.pr
    if d.stage in BUILD_STAGES:
        return d.stage not in story.stage_done
    if d.stage in ("fix", "resolve-conflict"):
        return bool(pr and d.sha and pr.head_sha == d.sha)
    if d.stage == "review":
        return bool(pr and d.sha and pr.head_sha == d.sha and pr.checks.get(REVIEW_CHECK, "pending") == "pending")
    if d.stage == "triage":
        return story.triage_verdict is None and "needs-human" not in story.labels
    return False


def _human_blocked(story: Story) -> bool:
    """Waiting for a person: an explicit label, a requested review, or a T2 approval."""
    if "needs-human" in story.labels or "blocked" in story.labels:
        return True
    pr = story.pr
    if not pr or pr.draft:
        return False
    mechanical = _checks_state(pr, [c for c in MECHANICAL_CHECKS if c != "risk-gate"])
    if mechanical != "success" or pr.checks.get(REVIEW_CHECK, "pending") != "success":
        return False
    # Everything a machine can decide is green; what is left is a person's approval.
    return pr.awaiting_human_review or pr.checks.get("risk-gate", "pending") == "failure"


def _checks_state(pr: PR, names: list[str]) -> str:
    states = [pr.checks.get(n, "pending") for n in names]
    if "failure" in states:
        return "failure"
    if "pending" in states:
        return "pending"
    return "success"


def pick_harness(story: Story, stage: str, roles: dict, state: State) -> str | None:
    """First configured harness for this developer and stage whose quota is available.

    The reviewer should differ from the implementer whenever the developer has a choice.
    """
    dev = roles.get("developers", {}).get(story.assignee) or roles.get("developers", {}).get("default", {})
    role = "impl" if stage in ("fix", "resolve-conflict") else stage
    candidates = list(dev.get("stages", {}).get(role, []))
    if not candidates:
        return None
    if stage == "review" and story.impl_harness:
        others = [h for h in candidates if h != story.impl_harness]
        candidates = others + [h for h in candidates if h == story.impl_harness]
    for harness in candidates:
        if state.quota_until.get(f"{story.assignee}/{harness}", 0) <= state.now:
            return harness
    return None


def plan(state: State, policy: dict | None = None, roles: dict | None = None) -> list[Action]:
    policy = {**DEFAULT_POLICY, **(policy or {})}
    roles = roles or {"developers": {"default": {"stages": {s: ["claude"] for s in [*STAGES, "triage"]}}}}
    stories = state.stories
    actions: list[Action] = []

    if state.paused:
        # Auto-merge that is already switched on would otherwise carry on by itself:
        # GitHub merges such a pull request the moment its checks turn green.
        return [Action("halt", reason=state.pause_reason),
                *(Action("disable-auto-merge", reason=f"#{number}") for number in state.armed_prs)]

    # A broken plan stops the whole sprint: nothing is dispatched until a human fixes it.
    broken = None
    for story in sorted(stories.values(), key=lambda s: s.id):
        missing = sorted(d for d in story.deps if d not in stories and d not in state.merged_elsewhere)
        if missing:
            broken = f"story {story.id} depends on story {missing[0]}, which is not in the sprint"
            break
    cycle = find_cycle({s.id: sorted(s.deps) for s in stories.values()})
    if cycle:
        broken = "dependency cycle: " + " -> ".join(cycle)
    if broken:
        return [] if "sprint-escalated" in state.notified else [Action("escalate", reason=broken)]

    # Spec drafting is not development work: it continues while main is red or the
    # sprint is finished, so the director returns to specs that are ready to approve.
    spec_work: list[Action] = []
    po_busy = state.last_po_dispatch is not None and state.now - state.last_po_dispatch < _timeout(policy, "product-owner")
    if state.roadmap_pending > 0 and state.open_spec_prs < policy["max_open_spec_prs"] and not po_busy:
        spec_work.append(Action("dispatch", stage="product-owner", harness=roles.get("planner", "claude"), attempt=1,
                                reason=f"{state.roadmap_pending} roadmap item(s) without a spec"))

    # Pushed branches get their pull request from the conductor, so that its author
    # is the conductor and a human can approve it.
    budget = policy["max_prs_per_day"] - state.prs_opened_today
    opened: list[Action] = []
    for branch in state.unopened_branches:
        is_story = branch.startswith("story/")
        if is_story and budget <= 0:
            continue
        opened.append(Action("open-pr", reason=branch))
        budget -= 1 if is_story else 0
    # A spec or sprint pull request is the director's decision. Once they approved it,
    # letting it merge is not a judgement the conductor makes, so shadow mode does not apply.
    for number in state.approved_prs:
        opened.append(Action("enable-auto-merge", reason=f"#{number}"))

    if state.main_red:
        if not state.main_fix_in_flight:
            return [Action("dispatch", stage="fix-main", harness=roles.get("planner", "claude"), attempt=1, reason="main is red"),
                    *opened, *spec_work]
        return [*opened, *spec_work]

    def satisfied(dep: str) -> bool:
        return dep in state.merged_elsewhere or (dep in stories and stories[dep].done)

    waiting = 0  # stories legitimately waiting on a running session, a check or quota

    def dispatch(story: Story, stage: str, attempt: int, reason: str = "") -> None:
        nonlocal waiting
        harness = pick_harness(story, stage, roles, state)
        if harness is None:
            waiting += 1  # quota exhausted on every configured harness; try again next run
            return
        actions.append(Action("dispatch", story=story.id, stage=stage, harness=harness, attempt=attempt, reason=reason))

    def retry_or_give_up(story: Story, why: str) -> None:
        d = story.last_dispatch
        assert d is not None
        if d.stage != "triage" and d.attempt < policy["max_attempts"]:
            dispatch(story, d.stage, d.attempt + 1, why)
        elif d.stage != "triage" and story.triage_count < policy["max_triage"]:
            dispatch(story, "triage", 1, why)
        else:
            actions.append(Action("escalate", story=story.id, reason=why))

    # Which started stories may be given new work in this pass. Normally all of
    # them: the WIP limit and the `touches` rule are applied when a story starts.
    # But stories that were parked (waiting for a dependency added later) or
    # blocked on a person gave their slot away, and several can come back at once.
    # Then the lowest ids go first, within the limit and without two that touch
    # the same thing; the rest wait until one of those is merged.
    admitted: set[str] = set()
    slots, held = 0, set()
    for story in sorted(stories.values(), key=lambda s: s.id):
        if (story.done or not story.started or "needs-human" in story.labels or "blocked" in story.labels
                or not all(satisfied(dep) for dep in story.deps)):
            continue
        if _human_blocked(story):
            admitted.add(story.id)  # waits for a person; holds its claim but no slot
            held.update(story.touches)
        elif slots < policy["wip_limit"] and not (held & set(story.touches)):
            admitted.add(story.id)
            slots += 1
            held.update(story.touches)

    # 1. Advance stories already in progress.
    for story in sorted(stories.values(), key=lambda s: s.id):
        if story.done or not story.started:
            continue

        # Auto-merge stays on the pull request once enabled, whatever is pushed
        # afterwards. So it is withdrawn the moment the pull request is no longer
        # exactly what the decision was about, and enabled again if it earns it.
        # Checked first: a label or a pending dependency must not shelter it.
        armed = story.pr
        if armed is not None and armed.auto_merge:
            eligible = (not armed.draft and not armed.awaiting_human_review
                        and not story.labels & {"needs-human", "blocked"}
                        and all(satisfied(dep) for dep in story.deps)
                        and _checks_state(armed, MECHANICAL_CHECKS) == "success"
                        and armed.checks.get(REVIEW_CHECK, "pending") == "success"
                        and armed.tier in policy["auto_merge_tiers"])
            if not eligible:
                actions.append(Action("disable-auto-merge", story=story.id, reason="no longer meets what auto-merge was enabled for"))
                continue

        if "needs-human" in story.labels or "blocked" in story.labels:
            continue
        d = story.last_dispatch

        if not all(satisfied(dep) for dep in story.deps):
            continue  # a dependency was added after it started (triage); it waits for that story

        if story.id not in admitted:
            waiting += 1  # over the limit after several stories came back at once
            continue

        if story.triage_verdict == "retry" and d is not None and d.stage == "triage":
            stage = next((s for s in BUILD_STAGES if s not in story.stage_done), "review")
            dispatch(story, stage, 1, "triage asked for a retry")
            continue

        if _in_flight(story):
            assert d is not None
            if state.now - d.at < _timeout(policy, d.stage):
                waiting += 1
            else:
                retry_or_give_up(story, f"{d.stage} stalled (attempt {d.attempt})")
            continue

        pr = story.pr
        if pr is not None and pr.conflicted:
            dispatch(story, "resolve-conflict", 1, "merge conflict with main")
            continue

        next_stage = next((s for s in BUILD_STAGES if s not in story.stage_done), None)
        if next_stage:
            dispatch(story, next_stage, 1)
            continue

        if pr is None:
            if any(b.startswith(f"story/{story.id}") for b in state.unopened_branches):
                waiting += 1  # its pull request is being opened in this same run
            else:
                actions.append(Action("escalate", story=story.id, reason="stages reported done but no branch or pull request exists"))
            continue

        if pr.draft:
            # Implementation is done: ask for the full gates. They are skipped on a
            # draft to save CI time, so there is nothing to wait for until this happens.
            actions.append(Action("mark-ready", story=story.id))
            continue

        mechanical = _checks_state(pr, [c for c in MECHANICAL_CHECKS if c != "risk-gate"])
        if mechanical == "failure":
            if story.fix_rounds < policy["max_fix_rounds"]:
                dispatch(story, "fix", 1, "required checks are failing")
            else:
                actions.append(Action("escalate", story=story.id, reason="checks still failing after the fix-round limit"))
            continue
        if mechanical == "pending":
            waiting += 1
            continue

        # The review verdict is a status on the commit, so a new push needs a new review.
        review = pr.checks.get(REVIEW_CHECK, "pending")
        if review == "pending":
            dispatch(story, "review", 1)
            continue
        if review == "failure":
            if story.fix_rounds < policy["max_fix_rounds"]:
                dispatch(story, "fix", 1, "agent review requested changes")
            else:
                actions.append(Action("escalate", story=story.id, reason="review still failing after the fix-round limit"))
            continue

        if pr.behind:
            actions.append(Action("update-branch", story=story.id, reason="branch is behind main"))
            continue
        risk = pr.checks.get("risk-gate", "pending")
        if risk == "pending":
            waiting += 1
            continue
        if pr.awaiting_human_review or risk == "failure":
            continue  # T2 or an owned path: it sits in a person's review queue
        if pr.auto_merge:
            waiting += 1
            continue
        if pr.tier in policy["auto_merge_tiers"]:
            actions.append(Action("enable-auto-merge", story=story.id))
        elif f"ready-to-merge/{story.id}" not in state.notified:
            actions.append(Action("notify", story=story.id, reason="all gates passed; shadow mode leaves the merge to a human"))

    # 2. Start new stories that are ready, within the WIP limit.
    # A started story that waits for a dependency added later (by triage) is parked:
    # it holds no WIP slot and no claim on what it touches. Otherwise the very story
    # it waits for could never start when the two touch the same thing.
    open_stories = [s for s in stories.values() if s.started and not s.done]
    active = [s for s in open_stories if all(satisfied(d) for d in s.deps)]
    wip = sum(1 for s in active if not _human_blocked(s))
    claimed: set[str] = set()
    for s in active:
        claimed.update(s.touches)
    dependents = {sid: sum(1 for o in stories.values() if sid in o.deps) for sid in stories}

    candidates = [
        s for s in stories.values()
        if not s.started and not s.done
        and "needs-human" not in s.labels and "blocked" not in s.labels
        and all(satisfied(d) for d in s.deps)
    ]
    candidates.sort(key=lambda s: (s.priority, -dependents[s.id], s.id))
    for story in candidates:
        if wip >= policy["wip_limit"] or budget <= 0:
            break
        if claimed & set(story.touches):
            continue  # would conflict with work in progress; run it after that merges
        before = len(actions)
        dispatch(story, STAGES[0], 1)
        if len(actions) > before:
            wip += 1
            budget -= 1
            claimed.update(story.touches)

    # 3. Sprint-level signals.
    total = len(stories)
    finished = sum(1 for s in stories.values() if s.done)
    # Drafting is checked first and on its own: a short sprint can go from below the
    # threshold to complete in one merge, and must still get its successor drafted.
    if total and finished / total >= policy["draft_next_sprint_at"] and not state.next_sprint_drafted:
        actions.append(Action("draft-next-sprint", reason=f"{finished}/{total} stories merged"))
    if total and finished == total and "sprint-complete" not in state.notified:
        actions.append(Action("notify", reason="sprint complete; development stops until the next sprint is approved"))

    stalled_before_spec_work = not (waiting > 0 or bool(actions))
    actions[:0] = opened
    actions.extend(spec_work)
    # Anything done in this run (including an escalation, which already notifies a
    # human) counts as movement; the stall notice is for a run with nothing left to do.
    progressing = not stalled_before_spec_work
    if total and finished < total and not progressing and "sprint-stalled" not in state.notified:
        actions.append(Action("notify", reason="every remaining story is blocked on a human; development has stopped"))

    return actions
