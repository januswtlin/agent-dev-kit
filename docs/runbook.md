# Runbook

*繁體中文：[runbook-zh-TW.md](runbook-zh-TW.md). The English version governs if the two differ.*

The steps from nothing to unattended operation. Do them in order; each section ends with a way to confirm it worked.
Anything marked **To verify** is a part of this template that has not yet been run on a real account. When you do it, check it against the official documentation of the day and write the result back into this document.

## 0. What you need

- A GitHub organization on the Team plan, with three seats: you, your colleague, and a machine user for the agents.
- Your Claude Max and ChatGPT subscriptions; your colleague's ChatGPT subscription. No API key is needed.
- On the Mac: Homebrew, `gh`, and Lima (or Docker Sandboxes).

## 1. Create the project repo

On GitHub, use this repo as a template to create a new private repo under the organization, then clone it to a location that iCloud does not sync:

```bash
mkdir -p ~/dev && cd ~/dev && gh repo clone OWNER/REPO
```

Replace `januswtlin` and `developer-two` with the real GitHub accounts in these files: `.github/CODEOWNERS`, `policy/roles.toml`.

Confirm:

```bash
make lint && make test
```

## 2. Three kinds of identity

### 2.1 Machine user (the agents' identity)

1. Register a new GitHub account, for example `yourname-agent`. GitHub allows one machine account per person.
2. Invite it to the repo as a collaborator with the **Write** role. Do not give it Maintain or Admin.
3. Sign in as this account and create two fine-grained personal access tokens, both limited to this one repo:

| Token | Permissions | Purpose |
|---|---|---|
| `AGENT_TOKEN` | Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Metadata: Read | The agent, inside the VM, pushes branches, comments and changes labels |
| `DISPATCH_TOKEN` | Issues: Read and write; Pull requests: Read and write; Metadata: Read | The conductor starts cloud tasks by commenting |

For both, do **not** tick Workflows, Administration, Commit statuses or Secrets.

`DISPATCH_TOKEN` **To verify**: when a comment starts a Codex cloud task, the commenter may have to be a user with a linked ChatGPT account. If so, this token must be issued from your own account instead, with the permissions in the table above.

### 2.2 Conductor GitHub App

Create an App under the organization's Settings > Developer settings > GitHub Apps:

- Repository permissions: Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Actions: Read and write; Variables: Read and write; Checks: Read; Commit statuses: Read; Metadata: Read.
- Subscribe to no webhooks, and untick Active.
- After creating it, generate a private key and install the App on this repo.

In the repo's Settings > Secrets and variables > Actions:

| Type | Name | Value |
|---|---|---|
| Variable | `CONDUCTOR_APP_ID` | The App's ID |
| Secret | `CONDUCTOR_APP_PRIVATE_KEY` | The full contents of the private key |

### 2.3 Humans

You and your colleague are repo admins. In the organization's Settings > Actions > General, confirm that **Allow GitHub Actions to create and approve pull requests** is off.

## 3. Secrets and variables

| Type | Name | Source | When it is needed |
|---|---|---|---|
| Secret | `AGENT_TOKEN` | 2.1 | When using the self-hosted runner |
| Secret | `DISPATCH_TOKEN` | 2.1 | When Codex is started by a comment |
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` | Run `claude setup-token` on your machine | Claude review |
| Secret | `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN` | The scheduled task created in section 6 | Claude cloud sessions |
| Variable | `REVIEW_BOTS` | A JSON array of the Codex review bot's accounts, for example `["chatgpt-codex-connector[bot]"]` **To verify** | Codex review |
| Variable | `CONDUCTOR_PAUSED` | `true` or empty | Kill switch |
| Variable | `CONDUCTOR_QUOTA` | JSON, for example `{"januswtlin/codex": 1795800000}`; the value is the epoch second at which the quota resets | Marking a harness's quota as exhausted by hand |
| Variable | `OLLAMA_MODEL` | For example `devstral` | When using Ollama |
| Variable | `LIGHT_RUNNER` | The label of a 1-core runner **To verify**; if unset, `ubuntu-latest` is used | When you want to lower the cost of light jobs |
| Variable | `CI_RUNNER` | Maintained automatically by `agentctl budget`; no need to set it by hand | Budget overflow |
| Variable | `CONDUCTOR_HOME`, `CONDUCTOR_LEASE`, `ACTIONS_USAGE` | Maintained automatically by `agentctl` | Where the conductor runs, and the usage estimate |

`CLAUDE_CODE_OAUTH_TOKEN` is tied to your personal subscription. `policy/roles.toml` is already set up so that only stories assigned to you use Claude.

## 4. Rulesets and repo settings

The template's contents must be on `main` first (the workflows behind the required checks have to exist) before you apply the rulesets. Run as an admin:

```bash
scripts/apply-rulesets.sh
```

In Settings > General > Pull Requests: turn on Allow auto-merge, allow squash merging only, and turn on Automatically delete head branches.

Confirm:

```bash
gh api repos/OWNER/REPO/rulesets --jq '.[].name'
```

It should list `main` and `release-tags`. **To verify**: whether the current API accepts the fields in `.github/rulesets/*.json`. If the API reports unknown fields, adjust them according to the error message and write the result back.

## 5. Mac and sandbox

```bash
bin/agentctl doctor
```

Fix every FAIL. Then create the VM:

```bash
brew install lima
```

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh check
```

Enter the VM, sign in to the two harnesses, and set the agent's git identity and token:

```bash
sandbox/vm.sh shell
```

The following run inside the VM:

```bash
claude
```

```bash
codex login
```

```bash
gh auth login --with-token
```

Paste `AGENT_TOKEN`, then press Ctrl-D. Next:

```bash
gh auth setup-git && git config --global user.name "yourname-agent" && git config --global user.email "yourname-agent@users.noreply.github.com"
```

Copy the `vm` profile from `codex/config.example.toml` into `~/.codex/config.toml` inside the VM.

Install the deny rules meant for story agents as user-level settings inside the VM. These rules forbid editing the guardrail paths and approved specs. They should apply to story agents only, so they are not kept in the repo's shared settings:

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

The cloud environments need the same rules (**To verify**: how each of the two cloud services sets user-level rules).

If you use Docker Sandboxes instead (stricter isolation, recommended): **To verify** its commands. The forms found during research were `sbx run claude`, `sbx run codex` and `sbx policy allow network <domain>`. Once confirmed, add the hosts in `sandbox/allowlist.txt` one by one and run the same checklist.

For installing the self-hosted runner, see `sandbox/runner/README.md`. It is optional. Decide whether to install it after the cloud paths have been confirmed.

## 6. Cloud agents

### Claude Code on the web

1. At claude.ai/code, connect GitHub and authorise this repo. If possible, connect the machine user's account (**To verify**).
2. Create an environment: set the network to restricted and add no secrets.
3. Create a scheduled task, choose API as the trigger, and set the prompt to "Carry out the instructions in the message you receive". Store its trigger URL and token as `CLAUDE_TRIGGER_URL` and `CLAUDE_TRIGGER_TOKEN`.

**To verify**: the request format of the API trigger. `_send` in `tools/agentctl/github.py` currently assumes a POST with a Bearer token and the body `{"text": "..."}`. Adjusting that one function to match the actual documentation is enough.

PO chat: in the Claude app, open a Claude Code session with this repo attached, type `/po`, then state the requirement.

### Codex cloud

1. At chatgpt.com/codex, connect GitHub and authorise this repo.
2. Create an environment: for the agent phase, turn the network off or set it to an allowlist, and add no secrets.
3. Turn on automatic reviews. The review rules are read from the Code Review Rules section of `AGENTS.md`.

**To verify**: whether commenting `@codex <instruction>` on a PR or issue starts an arbitrary task; and whether the review result appears as a PR review or as a comment. The `bridge` job of the `agent-review` workflow must be adjusted to match.

## 7. Spike: first prove one full loop completes

Before committing to real stories, use a toy story to verify the whole path. The goal is to see this sequence happen without issuing any manual command:

1. Create `docs/specs/001-hello/` (a small feature with one AC and two TCs) and `docs/sprints/001.toml` (`stories = ["001"]`), and merge them through a PR.
2. The conductor runs and dispatches `design`. First use a dry run to see what it intends to do:

```bash
gh workflow run conductor.yml -f dry_run=true
```

3. The agent pushes `story/001-hello`, `open-pr` opens the PR, and the checks start running.
4. `done:design`, `done:tests` (at this point `red-green` should be red, because there is no implementation yet) and `done:impl` appear in that order.
5. `agent-review` is dispatched and writes the status.
6. All six checks are green. In shadow mode the conductor notifies you that the PR can be merged; you press merge.
7. `evidence` posts the traceability table to the story issue.

Have Claude and Codex each do the implementation once. If any step gets stuck, note where it stuck and the error message:

| Where it gets stuck | What to do |
|---|---|
| The conductor fails while reading state | Fix `collect` in `tools/agentctl/github.py`. It has not yet been run against the real API |
| A harness cannot be triggered from the cloud | In `policy/roles.toml`, change it to `via = "workflow"` and use the self-hosted runner instead |
| The agent did not add the `done:*` label | Check whether the agent identity has write access to Issues; strengthen the prompt if necessary |
| `agent-review` stays pending | Check `CLAUDE_CODE_OAUTH_TOKEN`, `REVIEW_BOTS`, and the action's input parameters |
| The PR was opened but the checks did not run | The PR must be opened by the Conductor App, not by `GITHUB_TOKEN` |

Also note these numbers and fill them into the table in section 6 of the guideline: how many minutes one run of the test suite takes, how many full gate runs one story triggers from start to merge, and how much the Actions Usage page shows this story consumed.

## 8. Red-team

Run every item in [redteam-checklist.md](redteam-checklist.md). If any one of them succeeds, fix it first.

## 9. The first real sprint

1. Add a few lines of requirements to `docs/product/roadmap.md` and merge them through a PR; or discuss them one by one in PO chat.
2. Approve the spec PRs the PO opens.
3. The planner drafts the next sprint when the current one is nearly complete. For the first sprint you have to ask it by hand: open a Claude Code session and ask it to draft sprint 001 following `prompts/planner.md`.
4. Approve the sprint PR. The conductor takes over from here.

### Turning on auto-merge

Stay in shadow mode for at least one sprint. Each time the conductor notifies you that a PR "can be merged", spend a minute making your own judgement and note whether you agree. After you have agreed consistently for a while, set this in `policy/conductor.toml`:

```toml
auto_merge_tiers = ["T0"]
```

After a further while, add `"T1"`. A change to this file is itself T2 and needs your approval.

## 10. Your colleague joins

1. They join the organization and become a repo admin.
2. In `policy/roles.toml`, replace `developer-two` with their account. If they are also to approve particular paths, add them to `.github/CODEOWNERS` and `humans`.
3. They do section 5 on their own Mac and connect the repo in Codex cloud.
4. For stories assigned to them: set them as the assignee on the story issue, and the conductor will use their harness configuration and their subscription.
5. Product decisions are still approved by you alone: the owners of `docs/specs/`, `docs/sprints/` and `docs/product/` list only you.

## 11. Day-to-day operation

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
| You suspect something is wrong | Pause, then run the red-team checklist once |

## 12. Ollama (do this later)

Ollama is installed on the Mac (it needs the GPU). The VM reaches it through port 11434 on the host gateway, and `sandbox/egress.sh` already allows this port.

- An M2 with 24GB of memory: choose a model in the 14 to 15GB class (for example devstral 24b, gpt-oss 20b). A 19GB-class model with a large context will be very tight. For model names and sizes, go by the Ollama model library of the day.
- Always raise the context window. The default is very small, and the agent will silently lose the instructions at the start.
- Position it for T0-type work: documentation, lint fixes, test skeletons. Its output must pass every gate all the same.
- In `policy/roles.toml`, add `"ollama"` to the stages you want to hand to it. It can only run through the self-hosted runner.
