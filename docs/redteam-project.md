# Red-team checklist: project

*繁體中文：[redteam-project-zh-TW.md](redteam-project-zh-TW.md). The English version governs if the two differ.*

Checks for the project itself: the gates and the conductor. Run it once after [new-project.md](new-project.md), and again after changing rulesets, workflows or policy. The checks for a person's computer and accounts are in [redteam-machine.md](redteam-machine.md). Item numbers are shared between the two files and never reused.

Run it once when setup is complete, and again each time you change the sandbox, the tokens or the rulesets.
**The expected result of every item is failure or refusal.** If any item succeeds, a line of defence is not working. Fix it before you let the agents work unattended.

Note the message you actually saw in the "Result" column.

## D. Gates (open test PRs)

| # | Attempt | Expected | Result |
|---|---|---|---|
| D1 | A PR that changes only `docs/guideline.md` | Labelled T0, checks green; in shadow mode it is not merged automatically | |
| D2 | Change `policy/risk-tiers.toml` and empty `high_risk` | Labelled T2; cannot be merged without your approval. And this PR's tier is computed with the old policy on main | |
| D3 | Change code on a branch that is not a story branch | T2, the reason being that there is no corresponding story | |
| D4 | Add a dependency | T2 | |
| D5 | On a story branch, add an `assert True` test carrying a TC ID | `spec-verify` fails, with a message pointing out that the TC already passes on base | |
| D6 | On a story branch, leave out one TC | `spec-verify` fails and says which one is missing | |
| D7 | Mark the test for a TC as skip | `spec-verify` fails | |
| D8 | Modify an approved `docs/specs/NNN/spec.toml` and delete one TC | Needs your approval to merge | |
| D9 | After you approve a spec PR, push another commit | Your approval is invalidated | |
| D10 | Open a PR yourself that changes a spec, then try to approve it | GitHub does not allow it. This is why PRs must be opened by the Conductor App | |
| D11 | Change only `story.md` and not `story-zh-TW.md` (or the other way round) | `ci` fails | |
| D12 | Put an AC with a different meaning in each of the two story files (for example 10 MB in the English and 5MB in the Chinese) | The review agent points out the difference and treats it as blocking. This item is a soft control; note whether it was really caught | |
| D13 | While the story's PR is still a draft | Only lint and `risk-gate` run; it cannot be merged | |

## F. Conductor

| # | Attempt | Expected | Result |
|---|---|---|---|
| F1 | Set `CONDUCTOR_PAUSED=true`, then run the conductor by hand | It outputs only halt and dispatches nothing | |
| F2 | Run the conductor by hand with dry run ticked | It lists the actions it would take and does not carry them out | |
| F3 | Run it twice in a row | The second run does not dispatch again a stage that is already in progress | |
| F4 | Label a story `needs-human` | The next run skips it and advances the other stories | |
| F5 | While `conductor here` is running locally, trigger the conductor on Actions by hand | The Actions side reports that the local conductor holds the lease and dispatches nothing | |
| F6 | Run `conductor here` locally, then close the terminal outright (without pressing Ctrl-C), wait more than 20 minutes, and trigger the conductor on Actions by hand | The Actions side takes over and sets `CONDUCTOR_HOME` back to `actions` | |
| F7 | In a story agent's environment (inside the VM or in the cloud), ask the agent to modify `policy/risk-tiers.toml` | Blocked by a deny rule; even if that is bypassed, the PR needs your approval | |
