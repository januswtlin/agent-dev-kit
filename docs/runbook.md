# Runbook

*繁體中文：[runbook-zh-TW.md](runbook-zh-TW.md). The English version governs if the two differ.*

The steps from nothing to unattended operation. Do them in order; each section ends with a way to confirm it worked.
Anything marked **To verify** is a part of this template that has not yet been run on a real account. When you do it, check it against the official documentation of the day and write the result back into this document.

## 0. What you need

- A GitHub organization on a plan that enforces rulesets on private repos (Team or above), with one seat per person. Agents and the conductor are GitHub Apps and take no seat.
- At least one AI coding subscription for each person whose stories agents will work on, for example Claude Max or ChatGPT. No API key is needed.
- On each person's Mac: Homebrew, `gh`, and Lima (or Docker Sandboxes).

## 1. Create the project repo

On GitHub, use this repo as a template to create a new private repo under the organization, then clone it to a location that iCloud does not sync:

```bash
mkdir -p ~/dev && cd ~/dev && gh repo clone OWNER/REPO
```

Fill in who is on the project. The first login is the director, who approves product decisions. Every login given can approve a T2 change. One person is enough:

```bash
scripts/init.sh DIRECTOR_LOGIN OTHER_LOGIN
```

Then open `policy/roles.toml` and set, for each person, which harness does which stage. The file has examples for one vendor, two vendors and a local model.

Confirm:

```bash
make lint && make test
```

## 2. Three kinds of identity

### 2.1 Agent GitHub App (one per developer)

Each developer creates a GitHub App for their own agents, so that a commit or a comment shows whose agent made it. Under your account's Settings > Developer settings > GitHub Apps:

- Name it after yourself, for example `yourname-agent`.
- Repository permissions: Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Metadata: Read. Nothing else. In particular, **not** Workflows, Administration, Commit statuses, Secrets or Variables.
- Subscribe to no webhooks, and untick Active.
- After creating it, generate a private key and install the App on this repo only.

Keep the App's ID and the private key file. Section 5 puts them in the VM. **To verify**: `agentctl app-token` has not been run against the real API yet.

To start cloud tasks by commenting, each developer also needs one personal token, `DISPATCH_TOKEN`: a fine-grained personal access token limited to this repo, with Issues: Read and write; Pull requests: Read and write; Metadata: Read. It comes from the developer's own account because the comment may have to be made by the user whose ChatGPT account is linked (**To verify**).

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

Everyone on the project is a repo admin. In the organization's Settings > Actions > General, confirm that **Allow GitHub Actions to create and approve pull requests** is off.

## 3. Secrets and variables

| Type | Name | Source | When it is needed |
|---|---|---|---|
| Secret | `DISPATCH_TOKEN` | 2.1 | When Codex is started by a comment |
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` | Run `claude setup-token` on your machine | Claude review |
| Secret | `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN` | The scheduled task created in section 6 | Claude cloud sessions |
| Variable | `REVIEW_BOTS` | A JSON array of the Codex review bot's accounts, for example `["chatgpt-codex-connector[bot]"]` **To verify** | Codex review |
| Variable | `CONDUCTOR_PAUSED` | `true` or empty | Kill switch |
| Variable | `CONDUCTOR_QUOTA` | JSON, for example `{"alice/codex": 1795800000}`; the value is the epoch second at which the quota resets | Marking a harness's quota as exhausted by hand |
| Variable | `OLLAMA_MODEL` | For example `devstral` | When using Ollama |
| Variable | `LIGHT_RUNNER` | The label of a 1-core runner **To verify**; if unset, `ubuntu-latest` is used | When you want to lower the cost of light jobs |
| Variable | `CI_RUNNER` | Maintained automatically by `agentctl budget`; no need to set it by hand | Budget overflow |
| Variable | `CONDUCTOR_HOME`, `CONDUCTOR_LEASE`, `ACTIONS_USAGE` | Maintained automatically by `agentctl` | Where the conductor runs, and the usage estimate |

Secrets that belong to one person's subscription (`DISPATCH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN`) can be stored per developer by appending the login in upper case, with any other character as `_`: `DISPATCH_TOKEN_ALICE`. The conductor uses the developer's own secret for that developer's stories and falls back to the plain name. With one person, the plain names are enough.

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

Fix every FAIL. The local sandbox is Docker Sandboxes in clone mode. Install `sbx` as its documentation describes (docs.docker.com/ai/sandboxes), then sign in:

```bash
sbx login
```

Put your agent App's ID and private key (section 2.1) on the Mac. They stay on the host, where nothing in a sandbox can read them. Use your App's ID in place of `APP_ID` and the name of the key file you downloaded:

```bash
mkdir -p ~/.config/agent-app && echo APP_ID > ~/.config/agent-app/app-id
```

```bash
mv ~/Downloads/YOUR_APP.private-key.pem ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

Then:

```bash
sandbox/sbx.sh setup
```

This turns off SSH agent forwarding for sbx (a setting that applies to all your sandboxes), allows the hosts in `sandbox/allowlist.txt`, and installs the token helper outside the repo, from the tooling on the default branch. To let sandboxes reach Ollama on the Mac, run it as `AGENT_OLLAMA=1 sandbox/sbx.sh setup`.

Log in to your harnesses the way the sbx documentation describes for each. At the time of writing that is `sbx secret set openai --oauth` on the host for Codex, and `/login` inside the sandbox for Claude Code (**To verify**).

Start an interactive agent, then check the boundary from a second terminal:

```bash
sandbox/sbx.sh up claude
```

```bash
sandbox/sbx.sh check
```

The agent works on a private clone and delivers by pushing. To look at its work before it pushes, fetch from the remote that sbx adds to your repo (`REPO` is the directory name):

```bash
git fetch sandbox-agent-REPO-claude
```

**To verify** on a real Mac: everything in this section. In particular, confirm that `git push` from inside the sandbox succeeds and is attributed to your agent App, and record the result in the red-team checklist.

Fallback: Lima. Use it if sbx is not available to you, or for the self-hosted runner (`sandbox/runner/README.md`). It is weaker: the workspace is mounted read-write, traffic is filtered by address, and the App's key has to be inside the VM.

```bash
brew install lima
```

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh check
```

```bash
sandbox/vm.sh shell
```

The following run inside the VM. Sign in to your harnesses (`claude`, `codex login`), then give the VM your agent App's key:

```bash
mkdir -p ~/.config/agent-app && cat > ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

Paste the private key, then press Ctrl-D. Next, with your App's ID in place of `APP_ID` and your App's name in place of `yourname-agent`:

```bash
echo 'export AGENT_APP_ID=APP_ID AGENT_APP_KEY=$HOME/.config/agent-app/key.pem PATH=/workspace/sandbox/bin:$PATH' >> ~/.profile && . ~/.profile
```

```bash
git config --global credential.https://github.com.helper '!/workspace/bin/agentctl app-token --git-credential' && git config --global user.name "yourname-agent[bot]" && git config --global user.email "yourname-agent[bot]@users.noreply.github.com"
```

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

The last command installs the deny rules meant for story agents. Also copy the `vm` profile from `codex/config.example.toml` into `~/.codex/config.toml`. For the cloud environments, apply the same story-agent rules (**To verify**: how each cloud service sets user-level rules).

## 6. Cloud agents

### Claude Code on the web

1. At claude.ai/code, connect GitHub with your own account and authorise this repo only. A cloud agent then acts as you on GitHub. Section E of the red-team checklist checks what it can do with that; run it before letting cloud sessions work unattended.
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

3. The agent pushes `story/001-hello` and `open-pr` opens the PR as a draft. A draft only gets lint and `risk-gate`.
4. `done:design`, `done:tests` and `done:impl` appear in that order. After `done:impl` the conductor marks the PR ready, and the full gates run for the first time.
5. `agent-review` is dispatched and writes the status.
6. All five checks are green. In shadow mode the conductor notifies you that the PR can be merged; you press merge.
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

## 10. Adding a person

1. They join the organization and become a repo admin.
2. In `policy/roles.toml`, add them to `humans` and give them a `[developers.LOGIN.stages]` table. In `.github/CODEOWNERS`, add them to the paths they may approve. Add them to `directors` and to the product paths only if they are to approve product decisions.
3. They create their own agent App and `DISPATCH_TOKEN` (section 2.1), do section 5 on their own Mac, and connect their own accounts to the cloud services (section 6). Their secrets are stored with their login as the suffix (section 3).
4. For stories assigned to them: set them as the assignee on the story issue, and the conductor will use their harness configuration, their credentials and their subscription.
5. Product decisions stay with the directors: only they are owners of `docs/specs/`, `docs/sprints/` and `docs/product/`.

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

Ollama is installed on the Mac (it needs the GPU). A sandbox reaches it as `host.docker.internal:11434` once `AGENT_OLLAMA=1 sandbox/sbx.sh setup` has allowed that port. In the Lima fallback, `sandbox/egress.sh` already allows it through the host gateway.

- An M2 with 24GB of memory: choose a model in the 14 to 15GB class (for example devstral 24b, gpt-oss 20b). A 19GB-class model with a large context will be very tight. For model names and sizes, go by the Ollama model library of the day.
- Always raise the context window. The default is very small, and the agent will silently lose the instructions at the start.
- Position it for T0-type work: documentation, lint fixes, test skeletons. Its output must pass every gate all the same.
- In `policy/roles.toml`, add `"ollama"` to the stages you want to hand to it. It runs in a local sandbox, so those stages only start while the conductor is running on your Mac (`agentctl conductor here`).
