# Setting up a new project

*繁體中文：[new-project-zh-TW.md](new-project-zh-TW.md). The English version governs if the two differ.*

Done once for each project, by someone who administers the GitHub organization. It ends with a project that is ready for people to join.

What each person then does on their own computer is in [new-machine.md](new-machine.md). Running the project day to day is in [operations.md](operations.md).

Anything marked **To verify** has not yet been run on a real account or machine. When you do it, check it against the official documentation of the day and write the result back into this document.

Do the sections in order. Each one depends on the ones before it.

If you are the first person on the project, the order across the two setup documents is:

1. Sections 1 to 5 of this document: the repo, the conductor's identity, the secrets and variables, the rulesets.
2. All of [new-machine.md](new-machine.md): your agent identity, your secrets, your sandbox, your cloud accounts. It needs the repo, the `conductor` environment and the clone that sections 1 to 5 create.
3. Back here for section 7 (the spike), section 8 and section 9.

## 1. What you need

- A GitHub organization on a plan that enforces rulesets on private repos (Team or above), with one seat per person. Agents and the conductor are GitHub Apps and take no seat.
- Python 3.11 or newer on the computer you run these steps from. The tooling uses `tomllib` and starts as `python3 -I`. Check:

```bash
python3 --version
```

- A recent `gh`, logged in as a repo admin. The conductor and the scripts use `gh variable get` and `gh variable set`, which older releases lack. No exact minimum version is known. If this prints a usage text, your `gh` is new enough; if it reports an unknown command, upgrade:

```bash
gh variable get --help
```

- `git` able to push to GitHub over HTTPS as you. Section 2 pushes to `main` once, and the spike pushes a branch. If you have not set this up, let `gh` do it:

```bash
gh auth setup-git
```

## 2. Create the project repo

Create a new private repo under the organization with this template's contents on its `main` branch, in a location on your Mac that iCloud does not sync. `OWNER/REPO` is the new repo; `TEMPLATE_OWNER/agent-dev-template` is where you got this template.

If the template repo is marked as a template on GitHub and its `main` branch holds these files:

```bash
mkdir -p ~/dev && cd ~/dev && gh repo create OWNER/REPO --private --template TEMPLATE_OWNER/agent-dev-template --clone
```

Otherwise (for example while the template's contents are still on a branch that has not been merged), copy that branch yourself. `TEMPLATE_BRANCH` is the branch that holds the files:

```bash
mkdir -p ~/dev && cd ~/dev && git clone --branch TEMPLATE_BRANCH https://github.com/TEMPLATE_OWNER/agent-dev-template REPO
```

```bash
cd REPO && gh repo create OWNER/REPO --private && git remote set-url origin https://github.com/OWNER/REPO.git
```

```bash
git branch -M main && git push -u origin main
```

Either way, go into the clone and confirm it is the template and not an empty repo. Every later command is run from there:

```bash
cd ~/dev/REPO && ls AGENTS.md policy/roles.toml sandbox/sbx.sh
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

`scripts/init.sh` only edits local files (`.github/CODEOWNERS` and `policy/roles.toml`). Commit them and push to `main`:

```bash
git add .github/CODEOWNERS policy/roles.toml && git commit -m "Fill in who is on the project" && git push origin main
```

The push starts the `ci` workflow on `main`. Wait for it and confirm it is green; this is the baseline every later pull request is compared with, and section 5 makes these checks mandatory:

```bash
gh run list --workflow ci.yml --branch main --limit 1
```

If it is red, fix it now with another direct push. After section 5 a fix needs a pull request.

This is the one time `main` is pushed to directly, and it must happen now, before the rulesets in section 5 exist. Once they are applied, `main` only changes through pull requests, and a pull request that touches these two files needs the approval of a code owner and of a human listed in `policy/roles.toml` as it is on `main`. While `main` still contains the placeholder `DIRECTOR_LOGIN`, nobody is a code owner and nobody is such a human, so nobody could approve the pull request that fixes it.

## 3. Project identities

The project has two kinds of identity of its own: the conductor, and the people. Each person's agent identity is theirs and is set up in [new-machine.md](new-machine.md).

### Conductor GitHub App

The conductor opens and merges pull requests, comments on and labels issues, dispatches workflows, reads checks, and reads and writes repository variables. Create an App under the organization's Settings > Developer settings > GitHub Apps:

- Repository permissions: Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Actions: Read and write; Variables: Read and write; Checks: Read; Commit statuses: Read; Metadata: Read.
- Subscribe to no webhooks, and untick Active.
- After creating it, generate a private key and install the App on this repo. Note the App's numeric ID. Keep the downloaded key file outside the project directory: a sandbox can read every file in that directory, including ignored ones.

Next, create the GitHub environment that holds the pipeline's secrets. Do this before you set `CONDUCTOR_APP_ID`: the conductor's job is skipped while that variable is empty, and it should not run before the environment is restricted.

1. In the repo's Settings > Environments, create an environment named exactly `conductor`.
2. Under Deployment branches and tags, choose Selected branches and tags and add one rule that allows the default branch (`main`) only.
3. In that environment, add the environment secret `CONDUCTOR_APP_PRIVATE_KEY` with the full contents of the private key. Or from the command line:

```bash
gh secret set CONDUCTOR_APP_PRIVATE_KEY --env conductor < PATH_TO_PRIVATE_KEY.pem
```

Why an environment and not a repository secret: the jobs that hold credentials (`reconcile` in `conductor.yml`, `brief` in `brief.yml`, `claude` in `agent-review.yml`) declare `environment: conductor`. A run started from any other ref, a manual dispatch of a branch included, is refused the secrets by GitHub itself. A repository secret has no such rule. **To verify**: that environments with deployment branch rules are available for private repos on the Team plan, the exact names of these settings, and that GitHub does not create the environment without a branch rule if a workflow names it first.

Last, in the repo's Settings > Secrets and variables > Actions > Variables, add the repository variable, or run:

```bash
gh variable set CONDUCTOR_APP_ID --body APP_ID
```

From this moment the conductor runs on GitHub Actions. It has nothing to dispatch yet: the template's sprint file (`docs/sprints/000.toml`) lists no stories. It does open a pull request for any branch pushed under `story/`, `spec/`, `sprint/` or `chore/`. Do not merge a sprint file that lists stories until section 5 is done and one person has finished [new-machine.md](new-machine.md).

| Type | Name | Where | Value |
|---|---|---|---|
| Environment secret | `CONDUCTOR_APP_PRIVATE_KEY` | Environment `conductor` | The full contents of the private key |
| Repository variable | `CONDUCTOR_APP_ID` | Settings > Secrets and variables > Actions > Variables | The App's numeric ID |

### Humans

Everyone on the project is a repo admin. In the organization's Settings > Actions > General, confirm that **Allow GitHub Actions to create and approve pull requests** is off.

## 4. Secrets and variables

Two different places:

- **Secrets** are environment secrets of `conductor` (Settings > Environments > conductor). This holds for `CONDUCTOR_APP_PRIVATE_KEY` above and for every secret that belongs to one person's subscription (`DISPATCH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN`, with a `_LOGIN` suffix for stories that the sprint file gives to a named person). Those are described in [new-machine.md](new-machine.md), section 3. Do not create any of them as repository secrets: the jobs read the environment, and a repository secret would also be readable by a workflow run from a branch.
- **Variables** are repository variables (Settings > Secrets and variables > Actions > Variables). They hold nothing secret. The project's variables are:

| Type | Name | Source | When it is needed |
|---|---|---|---|
| Variable | `REVIEW_BOTS` | A JSON array of the accounts whose pull request reviews count as the agent review, for example `["chatgpt-codex-connector[bot]"]` **To verify**. If a review stage runs in a local sandbox (`via = "sbx"` and no `review_workflow`), add that developer's agent App login here too, for example `"yourname-agent[bot]"`: the sandbox's token cannot write the status itself, so its review is converted by the `bridge` job, which only listens to these accounts | Codex review; a review in a local sandbox |
| Variable | `CONDUCTOR_PAUSED` | `true` to pause; `false` or unset otherwise | Kill switch |
| Variable | `CONDUCTOR_QUOTA` | JSON, for example `{"alice/codex": 1795800000}`; the value is the epoch second at which the quota resets | Marking a harness's quota as exhausted by hand |
| Variable | `OLLAMA_MODEL` | For example `devstral` | When using Ollama |
| Variable | `LIGHT_RUNNER` | The label of a 1-core runner **To verify**; if unset, `ubuntu-latest` is used | When you want to lower the cost of light jobs |
| Variable | `CI_RUNNER` | Maintained automatically by `agentctl budget`; no need to set it by hand. Overflow is off by default, so it stays on the GitHub-hosted runner | Where `ci` and `security` run |
| Variable | `CONDUCTOR_HOME`, `CONDUCTOR_LEASE`, `ACTIONS_USAGE` | Maintained automatically by `agentctl` | Where the conductor runs, and the usage estimate |
| Variable | `CONDUCTOR_BOT` | Normally unset. The conductor works out its own login (`APP-SLUG[bot]`) from the App, on Actions and locally. A login put in this variable is trusted as an additional author of conductor marker comments | Only if markers written under another login must still be believed. Anyone named here can steer the conductor, so leave it unset otherwise |

## 5. Rulesets and repo settings

The template's contents and the commit from section 2 must be on `main` first (the workflows behind the required checks have to exist, and the code owners have to be real logins), and the `ci` run on `main` must be green (section 2), before you apply the rulesets. Run as an admin, with the Conductor App's numeric ID:

```bash
CONDUCTOR_APP_ID=APP_ID scripts/apply-rulesets.sh
```

The script refuses to run without `CONDUCTOR_APP_ID`. It creates or updates three rulesets:

- `main`: no deletion, no force-push, changes only through a pull request with a code owner review where one is required, and the five required checks. It has no bypass for anyone.
- `main-merge`: only repo admins and the Conductor App may update the default branch. An agent's token can push branches, and this ruleset is what stops it from merging a pull request even when every check on it is green. The admins and the Conductor App still have to satisfy everything in `main`.
- `release-tags`: only repo admins may create, move or delete a `v*` tag.

In Settings > General > Pull Requests: turn on Allow auto-merge, allow squash merging only, and turn on Automatically delete head branches. Allow auto-merge is not optional: once a code owner has approved a spec or sprint pull request, the conductor enables auto-merge on it at its next pass, and that is what merges it. It does this whatever `auto_merge_tiers` says, because the decision was a person's. It never does it for a `chore/` pull request; a person merges those.

Confirm:

```bash
gh api repos/OWNER/REPO/rulesets --jq '.[].name'
```

It should list `main`, `main-merge` and `release-tags`. **To verify**: whether the current API accepts the fields in `.github/rulesets/*.json`; that `main` and `main-merge` layer as described (the bypass in `main-merge` does not weaken `main`); that the App's ID is the right `actor_id` for an Integration bypass; and that `integration_id: 15368` in `main.json` is the GitHub Actions app that produces the required checks. If the API reports unknown fields, adjust them according to the error message and write the result back.

## 6. Set up the first person

At least one person has to follow [new-machine.md](new-machine.md) from start to finish before the spike: their agent identity, their secrets, their sandbox, and their cloud accounts. Do that now, then come back here.

## 7. Spike: first prove one full loop completes

Before committing to real stories, use a toy story to verify the whole path. The spike is sprint 001. The goal is to see this sequence happen without issuing any manual command beyond the ones shown here.

Nobody opens a pull request by hand. An agent, or here you, pushes a branch. The workflow `notify` runs on that push; it holds no secrets and does nothing. The conductor reacts to its completion and opens the pull request as the Conductor App. A pull request you opened yourself you could not approve.

1. Create the spike's spec and sprint on a branch named `sprint/001`:

```bash
git switch -c sprint/001
```

```bash
cp -R docs/specs/_template docs/specs/001-hello
```

```bash
cp docs/sprints/_template.toml docs/sprints/001.toml
```

   Fill in the three spec files (a small feature with one AC and two TCs) and the sprint file (`stories = ["001"]`). For `assignee`, leave `default` if the secrets of the person from section 6 are stored under the plain names (`DISPATCH_TOKEN`). Set it to their login only if their secrets carry the suffix (`DISPATCH_TOKEN_ALICE`): a story given to a named person uses that person's suffixed secrets and never falls back to the plain ones.

   Keep the toy feature in Python. As shipped, `make test` runs Python's `unittest` over the `tests/` directory and writes the result file the gates read, so the spike needs no other test runner. A test carries its TC id in its name, for example `test_tc_001_01_says_hello`. To use another stack, first change the `project-*` targets in the `Makefile` on a `chore/` branch and merge that, so that the runner is on `main` before the story starts; red-green runs the story's tests on `main`.

   Then check, commit and push:

```bash
make lint
```

```bash
git add docs/specs/001-hello docs/sprints/001.toml && git commit -m "Add the spike story and sprint 001" && git push -u origin sprint/001
```

2. Wait for the conductor to open the pull request for `sprint/001`. It is opened ready for review. Wait until `ci`, `security`, `spec-verify` and `agent-review` are green. `risk-gate` is red at this point, and that is correct: a spec and a sprint file are T2, and `risk-gate` only passes once a person listed in `policy/roles.toml` has approved the current commit.
3. Pause the conductor. Otherwise the merge of the sprint file starts a live run at once. This also means the conductor will not merge this one pull request for you: a paused conductor dispatches nothing, opens nothing and enables no auto-merge:

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

4. Approve the pull request. `risk-gate` runs again on your review and turns green. Then merge it yourself, this once. The merge triggers conductor runs; while paused each one prints only `halt`:

```bash
gh pr merge sprint/001 --squash
```

5. Ask for a dry run. While paused it also prints only `halt (kill switch is on)`, because a paused conductor does not compute a plan. This confirms the kill switch works:

```bash
gh workflow run conductor.yml -f dry_run=true
```

6. To see the plan, unpause and ask for a dry run straight away. Unpausing starts nothing by itself: the next live run comes with the next event or with the scheduled run (every four hours). If an event arrives in between, the live run comes first; that is harmless here.

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

```bash
gh workflow run conductor.yml -f dry_run=true
```

   Read the run log. It should list a dispatch of `design` for story 001 and nothing surprising. A dry run creates nothing, not even the tracking issues.
7. Start the live run:

```bash
gh workflow run conductor.yml
```

8. The conductor dispatches `design`. The agent pushes `story/001-hello`, `notify` runs, and the conductor opens the pull request as a draft. A draft only gets lint and `risk-gate`.
9. `done:design`, `done:tests` and `done:impl` appear in that order. After `done:impl` the conductor marks the pull request ready, and the full gates run for the first time.
10. `agent-review` is dispatched for the head commit and writes the status on it. A review that did not finish is published as failure, never left as a pass. If the branch moved while the review was waiting to start, that run stops without a verdict and the conductor asks for a review of the new commit.
11. All five checks are green, and the head commit also carries a status named `risk-tier/T1` (or `T0`): that status, not the `tier:` label, is what the conductor goes by. In shadow mode the conductor notifies you that the pull request can be merged; you press merge.
12. `evidence` posts the traceability table to the story issue.

Have Claude and Codex each do the implementation once. If any step gets stuck, note where it stuck and the error message:

| Where it gets stuck | What to do |
|---|---|
| The conductor fails while reading state | Fix `collect` in `tools/agentctl/github.py`. It has not yet been run against the real API |
| The `reconcile` job fails at the App token step, or is refused the environment | Check that the environment `conductor` exists, that its branch rule allows `main`, and that `CONDUCTOR_APP_PRIVATE_KEY` is a secret of that environment, not a repository secret |
| A branch was pushed but no pull request appears | Check that `notify` ran for the push and that a `conductor` run followed it. The conductor opens nothing while `CONDUCTOR_PAUSED` is `true`, and no more than `max_prs_per_day` story pull requests a day. Branch names must start with `story/`, `spec/`, `sprint/` or `chore/` |
| The pull request was opened but the checks did not run | It must be opened by the Conductor App, not with `GITHUB_TOKEN`. Check that the `reconcile` job used the App token. The checks also only run for pull requests into `main` |
| An approved spec or sprint pull request does not merge | The conductor enables auto-merge at its next pass after the approval, not at the moment you approve. Check that a `conductor` run followed your review (on Actions it is started by `risk-gate` re-running), that the conductor is not paused, that Allow auto-merge is on (section 5), that the approval came from a code owner, and that all five checks are green on the commit you approved. A push after your approval invalidates it. A `chore/` pull request is never merged by the conductor: merge it yourself |
| A harness cannot be triggered from the cloud | In `policy/roles.toml`, change it to `via = "sbx"`. Its stages then run in a Docker Sandbox on the developer's Mac and wait until `bin/agentctl conductor here` runs there. This is a T2 change on a `chore/` branch |
| The agent did not add the `done:*` label | Check whether the agent identity has write access to Issues; strengthen the prompt if necessary |
| `agent-review` stays pending | For a Claude review, look at the `agent-review` workflow run: the `publish` job sets failure when the review did not finish, so pending means the run never started, could not resolve the pull request, or stopped because the branch had moved (the conductor then asks again). Check that `CLAUDE_CODE_OAUTH_TOKEN` is a secret of the `conductor` environment, under the plain name for a story of `default` and with the login suffix for a story given to a named person, and check the action's input parameters (`--tools` among them). For a Codex review, or a review in a local sandbox, check `REVIEW_BOTS` |
| A dispatch fails with "no dispatch token configured" or "no https trigger URL configured" for a named developer | The sprint file gives the story to that person, so only their suffixed secret is used. Add it to the `conductor` environment, or give the story to `default` |
| `spec-verify` fails at "Keep only plain result files" | The result artifact contained a symbolic link. Look at what the test step wrote under `reports/` |
| Red-green fails with "its test did not run on base" | The story's test files were not picked up when the tests were run on `main`. Check `test_paths` in `policy/project.toml` and that the TC id is in the test's name |
| The conductor never enables auto-merge on a green story pull request although its tier is in `auto_merge_tiers` | It reads the tier from the commit status `risk-tier/T?` that `risk-gate` writes. Check that the status is on the head commit |

Also note these numbers and fill them into the table in section 6 of the guideline: how many minutes one run of the test suite takes, how many full gate runs one story triggers from start to merge, and how much the Actions Usage page shows this story consumed.

## 8. Red-team

Run every item in [redteam-project.md](redteam-project.md). If an item does not give its expected result, fix that first.

## 9. The first real sprint

The spike used sprint 001, so the first real sprint is sprint 002.

1. Add a few lines of requirements to `docs/product/roadmap.md` and merge them through a PR; or discuss them one by one in PO chat.
2. The PO pushes a `spec/` branch for each story and the conductor opens the pull request. Approve it. Approving is enough: at its next pass the conductor enables auto-merge, and the pull request merges once the checks are green.
3. The planner drafts the next sprint when the current one is nearly complete. For the first real sprint you have to ask it by hand: open a Claude Code session and ask it to draft sprint 002 following `prompts/planner.md`.
4. Approve the sprint pull request. It merges the same way, and the conductor takes over from here.

Automatic merging of story pull requests starts switched off (shadow mode). When and how to turn it on is in [operations.md](operations.md), section 2.
