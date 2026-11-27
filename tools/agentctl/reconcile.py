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
MECHANICAL_CHECKS = ["ci", "security", "spec-trace", "red-green", "risk-gate"]
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


@dataclass
class Dispatch:
    stage: str  # one of STAGES, or fix | resolve-conflict | triage
    at: float  # epoch seconds
    harness: str = ""
    attempt: int = 1


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


@dataclass(frozen=True)
class Action:
    kind: str  # dispatch | update-branch | enable-auto-merge | escalate | notify | halt | draft-next-sprint
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


def _in_flight(story: Story) -> bool:
    """True while the last dispatched session has not reported its outcome."""
    d = story.last_dispatch
    if d is None:
        return False
    if d.stage in STAGES:
        return d.stage not in story.stage_done
    if d.stage == "fix":
        # The fixing agent clears `done:review` when it finishes, to request a new review.
        return "review" in story.stage_done
    if d.stage == "resolve-conflict":
        return bool(story.pr and story.pr.conflicted)
    if d.stage == "triage":
        return story.triage_verdict is None and "needs-human" not in story.labels
    return False


def _human_blocked(story: Story) -> bool:
    if "needs-human" in story.labels or "blocked" in story.labels:
        return True
    return bool(story.pr and story.pr.awaiting_human_review and _checks_state(story.pr, MECHANICAL_CHECKS) != "failure")


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
        return [Action("halt", reason="kill switch is on")]

    # A broken plan stops the whole sprint: nothing is dispatched until a human fixes it.
    broken = None
    for story in sorted(stories.values(), key=lambda s: s.id):
        missing = sorted(d for d in story.deps if d not in stories)
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

    if state.main_red:
        if not state.main_fix_in_flight:
            return [Action("dispatch", stage="fix-main", harness="claude", attempt=1, reason="main is red"), *spec_work]
        return spec_work

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

    # 1. Advance stories already in progress.
    for story in sorted(stories.values(), key=lambda s: s.id):
        if story.done or not story.started or "needs-human" in story.labels or "blocked" in story.labels:
            continue
        d = story.last_dispatch

        if story.triage_verdict == "retry" and d is not None and d.stage == "triage":
            stage = next((s for s in STAGES if s not in story.stage_done), "review")
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

        next_stage = next((s for s in STAGES if s not in story.stage_done), None)

        if next_stage in ("design", "tests", "impl"):
            dispatch(story, next_stage, 1)
            continue

        if pr is None:
            actions.append(Action("escalate", story=story.id, reason="stages reported done but no pull request exists"))
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

        if next_stage == "review":
            dispatch(story, "review", 1)
            continue

        review = pr.checks.get(REVIEW_CHECK, "pending")
        if review == "failure":
            if story.fix_rounds < policy["max_fix_rounds"]:
                dispatch(story, "fix", 1, "agent review requested changes")
            else:
                actions.append(Action("escalate", story=story.id, reason="review still failing after the fix-round limit"))
            continue
        if review == "pending":
            waiting += 1
            continue

        if pr.behind:
            actions.append(Action("update-branch", story=story.id, reason="branch is behind main"))
            continue
        if pr.awaiting_human_review:
            continue  # T2: sits in the director's review queue
        if pr.auto_merge:
            waiting += 1
            continue
        if pr.tier in policy["auto_merge_tiers"]:
            actions.append(Action("enable-auto-merge", story=story.id))
        elif f"ready-to-merge/{story.id}" not in state.notified:
            actions.append(Action("notify", story=story.id, reason="all gates passed; shadow mode leaves the merge to a human"))

    # 2. Start new stories that are ready, within the WIP limit.
    open_stories = [s for s in stories.values() if s.started and not s.done]
    wip = sum(1 for s in open_stories if not _human_blocked(s))
    claimed: set[str] = set()
    for s in open_stories:
        claimed.update(s.touches)
    dependents = {sid: sum(1 for o in stories.values() if sid in o.deps) for sid in stories}

    candidates = [
        s for s in stories.values()
        if not s.started and not s.done
        and "needs-human" not in s.labels and "blocked" not in s.labels
        and all(stories[d].done for d in s.deps)
    ]
    candidates.sort(key=lambda s: (s.priority, -dependents[s.id], s.id))
    budget = policy["max_prs_per_day"] - state.prs_opened_today
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
    if total and finished == total:
        if "sprint-complete" not in state.notified:
            actions.append(Action("notify", reason="sprint complete; development stops until the next sprint is approved"))
    elif total and finished / total >= policy["draft_next_sprint_at"] and not state.next_sprint_drafted:
        actions.append(Action("draft-next-sprint", reason=f"{finished}/{total} stories merged"))

    stalled_before_spec_work = not (waiting > 0 or bool(actions))
    actions.extend(spec_work)
    # Anything done in this run (including an escalation, which already notifies a
    # human) counts as movement; the stall notice is for a run with nothing left to do.
    progressing = not stalled_before_spec_work
    if total and finished < total and not progressing and "sprint-stalled" not in state.notified:
        actions.append(Action("notify", reason="every remaining story is blocked on a human; development has stopped"))

    return actions
