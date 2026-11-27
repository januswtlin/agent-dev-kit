# Setting up a new project

*繁體中文：[new-project-zh-TW.md](new-project-zh-TW.md). The English version governs if the two differ.*

Done once for each project, by someone who administers the GitHub organization. It ends with a project that is ready for people to join.

What each person then does on their own computer is in [new-machine.md](new-machine.md). Running the project day to day is in [operations.md](operations.md).

Anything marked **To verify** has not yet been run on a real account or machine. When you do it, check it against the official documentation of the day and write the result back into this document.

## 1. What you need

- A GitHub organization on a plan that enforces rulesets on private repos (Team or above), with one seat per person. Agents and the conductor are GitHub Apps and take no seat.

## 2. Create the project repo

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

## 3. Project identities

The project has two kinds of identity of its own: the conductor, and the people. Each person's agent identity is theirs and is set up in [new-machine.md](new-machine.md).

### Conductor GitHub App

Create an App under the organization's Settings > Developer settings > GitHub Apps:

- Repository permissions: Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Actions: Read and write; Variables: Read and write; Checks: Read; Commit statuses: Read; Metadata: Read.
- Subscribe to no webhooks, and untick Active.
- After creating it, generate a private key and install the App on this repo.

In the repo's Settings > Secrets and variables > Actions:

| Type | Name | Value |
|---|---|---|
| Variable | `CONDUCTOR_APP_ID` | The App's ID |
| Secret | `CONDUCTOR_APP_PRIVATE_KEY` | The full contents of the private key |

### Humans

Everyone on the project is a repo admin. In the organization's Settings > Actions > General, confirm that **Allow GitHub Actions to create and approve pull requests** is off.

## 4. Secrets and variables

In the repo's Settings > Secrets and variables > Actions. These belong to the project. The secrets that belong to one person's subscription are in [new-machine.md](new-machine.md), section 3.

| Type | Name | Source | When it is needed |
|---|---|---|---|
| Variable | `REVIEW_BOTS` | A JSON array of the Codex review bot's accounts, for example `["chatgpt-codex-connector[bot]"]` **To verify** | Codex review |
| Variable | `CONDUCTOR_PAUSED` | `true` or empty | Kill switch |
| Variable | `CONDUCTOR_QUOTA` | JSON, for example `{"alice/codex": 1795800000}`; the value is the epoch second at which the quota resets | Marking a harness's quota as exhausted by hand |
| Variable | `OLLAMA_MODEL` | For example `devstral` | When using Ollama |
| Variable | `LIGHT_RUNNER` | The label of a 1-core runner **To verify**; if unset, `ubuntu-latest` is used | When you want to lower the cost of light jobs |
| Variable | `CI_RUNNER` | Maintained automatically by `agentctl budget`; no need to set it by hand | Budget overflow |
| Variable | `CONDUCTOR_HOME`, `CONDUCTOR_LEASE`, `ACTIONS_USAGE` | Maintained automatically by `agentctl` | Where the conductor runs, and the usage estimate |

## 5. Rulesets and repo settings

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

## 6. Set up the first person

At least one person has to follow [new-machine.md](new-machine.md) from start to finish before the spike: their agent identity, their sandbox, and their cloud accounts.

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

Run every item in [redteam-project.md](redteam-project.md). If any item succeeds, fix it first.

## 9. The first real sprint

1. Add a few lines of requirements to `docs/product/roadmap.md` and merge them through a PR; or discuss them one by one in PO chat.
2. Approve the spec PRs the PO opens.
3. The planner drafts the next sprint when the current one is nearly complete. For the first sprint you have to ask it by hand: open a Claude Code session and ask it to draft sprint 001 following `prompts/planner.md`.
4. Approve the sprint PR. The conductor takes over from here.

Auto-merge starts switched off. When and how to turn it on is in [operations.md](operations.md), section 2.
