import copy
import unittest

from agentctl.reconcile import PR, Dispatch, State, Story, plan

NOW = 1_000_000.0
GREEN = {"ci": "success", "security": "success", "spec-verify": "success", "risk-gate": "success"}
DONE = {"design", "tests", "impl"}
ROLES = {
    "developers": {
        "alice": {"stages": {"design": ["claude"], "tests": ["claude"], "impl": ["claude", "codex"],
                             "review": ["codex", "claude"], "triage": ["claude"]}},
        "bob": {"stages": {s: ["codex"] for s in ["design", "tests", "impl", "review", "triage"]}},
    }
}


def story(sid, **kw):
    kw.setdefault("assignee", "alice")
    kw.setdefault("touches", [f"module-{sid}"])
    return Story(id=sid, **kw)


def state(*stories, **kw):
    return State(stories={s.id: s for s in stories}, now=NOW, **kw)


def run(st, **policy):
    return plan(st, policy, ROLES)


def kinds(actions):
    return [(a.kind, a.story, a.stage) for a in actions]


class StartingWork(unittest.TestCase):
    def test_starts_ready_stories_in_priority_order_up_to_wip(self):
        st = state(story("003", priority=1), story("001", priority=2), story("002", priority=2))
        self.assertEqual(kinds(run(st, wip_limit=2)), [("dispatch", "003", "design"), ("dispatch", "001", "design")])

    def test_ties_go_to_the_story_that_unblocks_more_work(self):
        st = state(story("001"), story("002"), story("003", depends_on=["002"]))
        self.assertEqual(kinds(run(st, wip_limit=1)), [("dispatch", "002", "design")])

    def test_waits_for_dependencies_to_merge(self):
        st = state(story("001"), story("002", depends_on=["001"], priority=1))
        self.assertEqual(kinds(run(st)), [("dispatch", "001", "design")])
        st.stories["001"].pr = PR(1, merged=True)
        self.assertEqual(kinds(run(st)), [("dispatch", "002", "design")])

    def test_runtime_blocked_by_links_are_added_to_the_approved_graph(self):
        st = state(story("001", blocked_by=["002"]), story("002", priority=5))
        self.assertEqual(kinds(run(st)), [("dispatch", "002", "design")])

    def test_overlapping_touches_are_serialised(self):
        st = state(story("001", touches=["orders", "db:orders"]), story("002", touches=["db:orders"]),
                   story("003", touches=["catalog"]))
        self.assertEqual(kinds(run(st, wip_limit=3)), [("dispatch", "001", "design"), ("dispatch", "003", "design")])

    def test_story_in_progress_claims_its_touches(self):
        running = story("001", touches=["orders"], last_dispatch=Dispatch("design", NOW - 60))
        st = state(running, story("002", touches=["orders"]))
        self.assertEqual(run(st), [])

    def test_daily_pr_budget_caps_new_starts(self):
        st = state(story("001"), story("002"), prs_opened_today=9)
        self.assertEqual(len(run(st, wip_limit=5, max_prs_per_day=10)), 1)

    def test_reviewer_differs_from_implementer_and_same_vendor_developer_still_works(self):
        done = {"design", "tests", "impl"}
        st = state(story("001", stage_done=done, pr=PR(1, checks=GREEN), impl_harness="codex",
                         last_dispatch=Dispatch("impl", NOW - 60, "codex")))
        self.assertEqual(run(st)[0].harness, "claude")
        st.stories["001"].assignee = "bob"
        self.assertEqual(run(st)[0].harness, "codex")


class Progressing(unittest.TestCase):
    def test_moves_through_stages(self):
        s = story("001", last_dispatch=Dispatch("design", NOW - 60), stage_done={"design"})
        self.assertEqual(kinds(run(state(s))), [("dispatch", "001", "tests")])

    def test_waits_while_a_session_is_running(self):
        self.assertEqual(run(state(story("001", last_dispatch=Dispatch("impl", NOW - 60), stage_done={"design", "tests"}))), [])

    def test_review_waits_for_mechanical_checks(self):
        done = {"design", "tests", "impl"}
        pending = dict(GREEN, ci="pending")
        s = story("001", stage_done=done, pr=PR(1, checks=pending), last_dispatch=Dispatch("impl", NOW - 60))
        self.assertEqual(run(state(s)), [])

    def test_failing_checks_send_it_back_for_a_fix(self):
        done = {"design", "tests", "impl"}
        s = story("001", stage_done=done, pr=PR(1, checks=dict(GREEN, **{"spec-verify": "failure"})),
                  last_dispatch=Dispatch("impl", NOW - 60))
        self.assertEqual(kinds(run(state(s))), [("dispatch", "001", "fix")])

    def test_review_rejection_loops_then_escalates(self):
        done = {"design", "tests", "impl", "review"}
        checks = dict(GREEN, **{"agent-review": "failure"})
        s = story("001", stage_done=done, pr=PR(1, checks=checks), last_dispatch=Dispatch("review", NOW - 60), fix_rounds=2)
        self.assertEqual(kinds(run(state(s))), [("dispatch", "001", "fix")])
        s.fix_rounds = 3
        self.assertEqual(kinds(run(state(s))), [("escalate", "001", "")])

    def test_a_fix_is_in_flight_until_the_branch_moves(self):
        # Mechanical failure before any review: the fix must not be launched again on every pass.
        failing = dict(GREEN, ci="failure")
        s = story("001", stage_done=DONE, pr=PR(1, checks=failing, head_sha="aaa"),
                  last_dispatch=Dispatch("fix", NOW - 60, "claude", 1, "aaa"), fix_rounds=1)
        self.assertEqual(run(state(s)), [])
        s.pr.head_sha = "bbb"  # the fix was pushed; the checks on the new commit fail again
        self.assertEqual(kinds(run(state(s))), [("dispatch", "001", "fix")])
        s.pr.checks = GREEN  # or they pass, and the new commit has no review verdict yet
        self.assertEqual(kinds(run(state(s))), [("dispatch", "001", "review")])

    def test_every_new_commit_needs_its_own_review(self):
        s = story("001", stage_done=DONE | {"review"}, pr=PR(1, checks=GREEN, head_sha="bbb"),
                  last_dispatch=Dispatch("review", NOW - 5000, "codex", 1, "aaa"))
        # A stale done:review label and an old review dispatch do not stand in for a verdict on bbb.
        self.assertEqual(kinds(run(state(s))), [("dispatch", "001", "review")])
        s.last_dispatch = Dispatch("review", NOW - 60, "codex", 1, "bbb")
        self.assertEqual(run(state(s)), [])  # that review is running

    def test_updates_branch_then_merges(self):
        done = {"design", "tests", "impl", "review"}
        checks = dict(GREEN, **{"agent-review": "success"})
        s = story("001", stage_done=done, pr=PR(1, checks=checks, behind=True), last_dispatch=Dispatch("review", NOW - 60))
        self.assertEqual(kinds(run(state(s), auto_merge_tiers=["T0", "T1"])), [("update-branch", "001", "")])
        s.pr.behind = False
        self.assertEqual(kinds(run(state(s), auto_merge_tiers=["T0", "T1"])), [("enable-auto-merge", "001", "")])
        s.pr.auto_merge = True
        self.assertEqual(run(state(s), auto_merge_tiers=["T0", "T1"]), [])

    def test_shadow_mode_never_merges(self):
        done = {"design", "tests", "impl", "review"}
        checks = dict(GREEN, **{"agent-review": "success"})
        s = story("001", stage_done=done, pr=PR(1, checks=checks), last_dispatch=Dispatch("review", NOW - 60))
        actions = run(state(s))
        self.assertEqual(kinds(actions), [("notify", "001", "")])
        self.assertEqual(run(state(s, notified={"ready-to-merge/001"}))[0].reason,
                         "every remaining story is blocked on a human; development has stopped")

    def test_draft_is_marked_ready_after_impl_and_not_before(self):
        early = story("001", stage_done={"design", "tests"}, pr=PR(1, draft=True), last_dispatch=Dispatch("tests", NOW - 60))
        self.assertEqual(kinds(run(state(early))), [("dispatch", "001", "impl")])
        done = story("001", stage_done={"design", "tests", "impl"}, pr=PR(1, draft=True), last_dispatch=Dispatch("impl", NOW - 60))
        self.assertEqual(kinds(run(state(done))), [("mark-ready", "001", "")])
        done.pr.draft = False  # checks have not reported yet
        self.assertEqual(run(state(done)), [])

    def test_a_red_risk_gate_is_a_wait_for_a_person_not_a_ready_notice(self):
        checks = dict(GREEN, **{"agent-review": "success", "risk-gate": "failure"})
        t2 = story("001", stage_done=DONE, pr=PR(1, checks=checks, tier="T2"), last_dispatch=Dispatch("review", NOW - 60))
        actions = run(state(t2, story("002")), wip_limit=1)
        # No "ready to merge" for 001, and it does not hold the only WIP slot either.
        self.assertEqual(kinds(actions), [("dispatch", "002", "design")])

    def test_merge_conflict_gets_a_resolution_task(self):
        s = story("001", stage_done={"design", "tests", "impl"}, pr=PR(1, checks=GREEN, conflicted=True),
                  last_dispatch=Dispatch("impl", NOW - 60))
        self.assertEqual(kinds(run(state(s))), [("dispatch", "001", "resolve-conflict")])


class Exceptions(unittest.TestCase):
    def stalled(self, attempt=1, **kw):
        return story("001", stage_done={"design"}, last_dispatch=Dispatch("tests", NOW - 3 * 3600, "claude", attempt), **kw)

    def test_stalled_stage_is_retried_then_triaged_then_escalated(self):
        self.assertEqual([(a.stage, a.attempt) for a in run(state(self.stalled(1)))], [("tests", 2)])
        self.assertEqual(kinds(run(state(self.stalled(2)))), [("dispatch", "001", "triage")])
        self.assertEqual(kinds(run(state(self.stalled(2, triage_count=1)))), [("escalate", "001", "")])

    def test_triage_retry_verdict_restarts_the_stage(self):
        s = story("001", stage_done={"design"}, last_dispatch=Dispatch("triage", NOW - 60), triage_count=1, triage_verdict="retry")
        self.assertEqual([(a.stage, a.attempt) for a in run(state(s))], [("tests", 1)])

    def test_triage_session_is_waited_for(self):
        s = story("001", stage_done={"design"}, last_dispatch=Dispatch("triage", NOW - 60), triage_count=1)
        self.assertEqual(run(state(s)), [])

    def test_human_blocked_story_does_not_block_others_or_use_a_slot(self):
        blocked = story("001", labels={"needs-human"}, last_dispatch=Dispatch("impl", NOW - 60))
        st = state(blocked, story("002"))
        self.assertEqual(kinds(run(st, wip_limit=1)), [("dispatch", "002", "design")])

    def test_t2_waiting_for_approval_does_not_use_a_slot(self):
        done = {"design", "tests", "impl", "review"}
        checks = dict(GREEN, **{"agent-review": "success"})
        waiting = story("001", stage_done=done, pr=PR(1, checks=checks, awaiting_human_review=True, tier="T2"),
                        last_dispatch=Dispatch("review", NOW - 60))
        self.assertEqual(kinds(run(state(waiting, story("002")), wip_limit=1)), [("dispatch", "002", "design")])

    def test_everything_blocked_stops_and_notifies_once(self):
        a = story("001", labels={"needs-human"}, last_dispatch=Dispatch("impl", NOW - 60))
        b = story("002", depends_on=["001"])
        actions = run(state(a, b))
        self.assertEqual([a.kind for a in actions], ["notify"])
        self.assertIn("blocked on a human", actions[0].reason)
        self.assertEqual(run(state(a, b, notified={"sprint-stalled"})), [])

    def test_kill_switch(self):
        self.assertEqual([a.kind for a in run(state(story("001"), paused=True))], ["halt"])

    def test_red_main_stops_dispatch_and_asks_for_one_fix(self):
        self.assertEqual(kinds(run(state(story("001"), main_red=True))), [("dispatch", "", "fix-main")])
        self.assertEqual(run(state(story("001"), main_red=True, main_fix_in_flight=True)), [])

    def test_quota_exhausted_falls_back_then_waits_without_raising_a_false_stall(self):
        s = story("001", stage_done={"design", "tests"}, last_dispatch=Dispatch("tests", NOW - 60))
        st = state(s, quota_until={"alice/claude": NOW + 3600})
        self.assertEqual(run(st)[0].harness, "codex")
        st.quota_until["alice/codex"] = NOW + 3600
        self.assertEqual(run(st), [])
        st.quota_until = {"alice/claude": NOW - 1, "alice/codex": NOW - 1}
        self.assertEqual(run(st)[0].harness, "claude")

    def test_dependency_cycle_and_unknown_dependency_escalate(self):
        cyc = run(state(story("001", depends_on=["002"]), story("002", blocked_by=["001"])))
        self.assertEqual(cyc[0].kind, "escalate")
        self.assertIn("cycle", cyc[0].reason)
        self.assertEqual(run(state(story("001", depends_on=["404"])))[0].kind, "escalate")
        self.assertEqual(run(state(story("001", depends_on=["404"]), notified={"sprint-escalated"})), [])


class PullRequestsAndDependencies(unittest.TestCase):
    def test_pushed_branches_get_a_pull_request_from_the_conductor(self):
        st = state(story("001", last_dispatch=Dispatch("design", NOW - 60)),
                   unopened_branches=["chore/fix-main", "spec/014-refunds", "story/001-add"], prs_opened_today=10)
        actions = run(st, max_prs_per_day=10)
        # Spec and chore branches always get one; a story branch waits for tomorrow's budget.
        self.assertEqual([a.reason for a in actions if a.kind == "open-pr"], ["chore/fix-main", "spec/014-refunds"])

    def test_only_approved_spec_and_sprint_pull_requests_are_set_to_merge(self):
        actions = run(state(story("001", last_dispatch=Dispatch("design", NOW - 60)), approved_prs=[31, 40]))
        self.assertEqual([(a.kind, a.reason) for a in actions], [("enable-auto-merge", "#31"), ("enable-auto-merge", "#40")])

    def test_story_waits_while_its_pull_request_is_being_opened(self):
        s = story("001", stage_done=DONE, last_dispatch=Dispatch("impl", NOW - 60))
        self.assertEqual(kinds(run(state(s, unopened_branches=["story/001-add"]))), [("open-pr", "", "")])
        self.assertEqual(run(state(s))[0].kind, "escalate")  # no branch either: something is wrong

    def test_a_dependency_merged_in_an_earlier_sprint_is_satisfied(self):
        st = state(story("012", depends_on=["007"]), merged_elsewhere={"007"})
        self.assertEqual(kinds(run(st)), [("dispatch", "012", "design")])
        self.assertEqual(run(state(story("012", depends_on=["007"])))[0].kind, "escalate")

    def test_triage_retry_waits_for_a_dependency_added_by_triage(self):
        blocked = story("001", stage_done={"design"}, blocked_by=["002"], triage_count=1, triage_verdict="retry",
                        last_dispatch=Dispatch("triage", NOW - 60))
        st = state(blocked, story("002"))
        self.assertEqual(kinds(run(st)), [("dispatch", "002", "design")])
        st.stories["002"].pr = PR(2, merged=True)
        self.assertEqual(kinds(run(st)), [("dispatch", "001", "tests")])


class Parked(unittest.TestCase):
    def test_a_story_waiting_for_a_later_dependency_does_not_block_that_dependency(self):
        # Triage made the running story 001 depend on 002, and both touch the database.
        a = story("001", touches=["db"], blocked_by=["002"], stage_done={"design"},
                  last_dispatch=Dispatch("tests", NOW - 60))
        b = story("002", touches=["db"])
        self.assertEqual(kinds(run(state(a, b), wip_limit=1)), [("dispatch", "002", "design")])


class SprintLevel(unittest.TestCase):
    def test_sprint_complete_does_not_expand_scope(self):
        st = state(story("001", pr=PR(1, merged=True)), story("002", pr=PR(2, merged=True)))
        st.next_sprint_drafted = True
        actions = run(st)
        self.assertEqual([a.kind for a in actions], ["notify"])
        self.assertIn("sprint complete", actions[0].reason)
        self.assertEqual(run(state(*st.stories.values(), notified={"sprint-complete"}, next_sprint_drafted=True)), [])

    def test_a_sprint_that_completes_in_one_step_still_gets_its_successor_drafted(self):
        st = state(story("001", pr=PR(1, merged=True)))
        self.assertEqual([a.kind for a in run(st)], ["draft-next-sprint", "notify"])

    def test_next_sprint_is_drafted_once_near_the_end(self):
        merged = [story(f"00{i}", pr=PR(i, merged=True)) for i in range(1, 5)]
        last = story("005", last_dispatch=Dispatch("impl", NOW - 60), stage_done={"design", "tests"})
        self.assertEqual([a.kind for a in run(state(*merged, last))], ["draft-next-sprint"])
        self.assertEqual(run(state(*merged, last, next_sprint_drafted=True)), [])

    def test_specs_are_drafted_from_the_roadmap_without_flooding_the_director(self):
        done = state(story("001", pr=PR(1, merged=True)), notified={"sprint-complete"}, roadmap_pending=2,
                     next_sprint_drafted=True)
        self.assertEqual(kinds(run(done)), [("dispatch", "", "product-owner")])
        done.open_spec_prs = 3
        self.assertEqual(run(done), [])
        done.open_spec_prs = 0
        done.last_po_dispatch = NOW - 60
        self.assertEqual(run(done), [])

    def test_spec_drafting_continues_while_main_is_red_but_not_when_paused(self):
        red = state(story("001"), main_red=True, main_fix_in_flight=True, roadmap_pending=1)
        self.assertEqual(kinds(run(red)), [("dispatch", "", "product-owner")])
        red.paused = True
        self.assertEqual([a.kind for a in run(red)], ["halt"])

    def test_pausing_also_withdraws_auto_merge_that_is_already_switched_on(self):
        st = state(story("001"), paused=True, armed_prs=[4, 9])
        self.assertEqual([(a.kind, a.reason) for a in run(st)],
                         [("halt", "kill switch is on"), ("disable-auto-merge", "#4"), ("disable-auto-merge", "#9")])

    def test_spec_drafting_does_not_hide_a_stalled_sprint(self):
        blocked = story("001", labels={"needs-human"}, last_dispatch=Dispatch("impl", NOW - 60))
        actions = run(state(blocked, roadmap_pending=1))
        self.assertEqual([a.kind for a in actions], ["dispatch", "notify"])

    def test_same_state_gives_same_actions(self):
        st = state(story("001"), story("002", depends_on=["001"]), story("003", touches=["module-001"]))
        first = run(copy.deepcopy(st))
        self.assertEqual(first, run(copy.deepcopy(st)))
        self.assertEqual(first, run(st))


if __name__ == "__main__":
    unittest.main()
