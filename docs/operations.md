# Operations

*繁體中文：[operations-zh-TW.md](operations-zh-TW.md). The English version governs if the two differ.*

Running a project once it is set up. Setting up is in [new-project.md](new-project.md) and [new-machine.md](new-machine.md).

## 1. Day to day

You decide where the conductor runs. While you are at the computer, let it run in a terminal. That uses no Actions allowance and responds faster:

```bash
bin/agentctl conductor here
```

Before you leave, press Ctrl-C, or run this in another terminal:

```bash
bin/agentctl conductor away
```

It does not matter if you forget to hand over. Once the lease has gone 20 minutes without being renewed, the scheduled run on Actions takes over automatically. To see where it is running now:

```bash
bin/agentctl conductor status
```

Running locally needs the trigger URL and token used for dispatching. Create `.env.conductor` in the project root (it is already listed in `.gitignore`), containing lines such as `CLAUDE_TRIGGER_URL=...` and `CLAUDE_TRIGGER_TOKEN=...`.

| Situation | What to do |
|---|---|
| You want to pause everything | Set the variable `CONDUCTOR_PAUSED` to `true` |
| You want to know the current state | Look at the Director's brief issue, or run `bin/agentctl status --markdown` |
| You want to know what the conductor will do next | `gh workflow run conductor.yml -f dry_run=true`, then read the run log |
| A story has been labelled `needs-human` | Read the triage explanation and options on the issue, decide, then remove the label; if the spec needs changing, change the spec |
| A harness's quota is exhausted | Set `CONDUCTOR_QUOTA`; when it expires the conductor resumes using the harness automatically |
| You want a story left alone for now | Add the `blocked` label to its issue |
| You want to release | Put a `v*` tag on the commit you want on main and push it |
| You want to know how much Actions has been used | `bin/agentctl budget --dry-run`, or look at the first line of the brief |
| You need to change the pipeline itself | Ask the agent directly in a session; the work happens on a `chore/` branch and you approve the PR |
| You suspect something is wrong | Pause, then run [redteam-project.md](redteam-project.md) and [redteam-machine.md](redteam-machine.md) |

## 2. Turning on auto-merge

Stay in shadow mode for at least one sprint. Each time the conductor notifies you that a PR "can be merged", spend a minute making your own judgement and note whether you agree. After you have agreed consistently for a while, set this in `policy/conductor.toml`:

```toml
auto_merge_tiers = ["T0"]
```

After a further while, add `"T1"`. A change to this file is itself T2 and needs your approval.

## 3. Adding a person

1. They join the organization and become a repo admin.
2. In `policy/roles.toml`, add them to `humans` and give them a `[developers.LOGIN.stages]` table. In `.github/CODEOWNERS`, add them to the paths they may approve. Add them to `directors` and to the product paths only if they are to approve product decisions.
3. They follow [new-machine.md](new-machine.md) from start to finish: their own agent App, their own secrets (stored with their login as the suffix), their sandbox and their own cloud accounts.
4. For stories assigned to them: set them as the assignee on the story issue, and the conductor will use their harness configuration, their credentials and their subscription.
5. Product decisions stay with the directors: only they are owners of `docs/specs/`, `docs/sprints/` and `docs/product/`.
