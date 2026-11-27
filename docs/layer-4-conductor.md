# Layer 4: The conductor

*繁體中文：[layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md). The English version governs if the two differ.*

The conductor (`agentctl conductor`) moves work forward while you are away. It is a program with no memory and no language model. On every pass it reads the sprint, the specs, the issues, the pull requests and the check results from GitHub, works out the next thing that should happen, and does it: it dispatches a stage to an agent, opens a pull request, marks one ready, updates a branch, enables or withdraws auto-merge, or hands a decision to you. It runs in a terminal on one Mac, as the Conductor GitHub App. It does not merge anything on its own until you list a tier in `auto_merge_tiers`. It does not make the agents safe (layer 1), protect `main` (layer 2) or judge the code (layer 3). It needs all three. Adopt it last, in shadow mode. The design and its reasons are in [guideline.md](guideline.md).

Nothing here has been run against real GitHub, Docker Sandboxes, the vendors' cloud services or a Mac. Anything marked **To verify** describes behaviour of those services that the code relies on.

## 1. What this layer protects

The conductor's job is to keep work moving without a person watching, and to stop when it should. What it provides:

- **Deterministic order.** A story starts when the stories it depends on are merged, it is not blocked, its `touches` do not overlap those of stories in progress, and the limit on stories in progress is not exceeded. The same input gives the same plan. The planning of dependencies is done by an agent and approved by you with the sprint; the program only computes.
- **No lost and no doubled work, as far as GitHub allows.** All memory is on GitHub (labels, issue links, hidden marker comments). A dispatch is recorded before it is sent, so a crash leaves a marker without a session, which is retried after the stage's timeout, never a session without a marker. A marker is believed only when written by the conductor's own login or by a person in `[roles] humans`.
- **Fuses.** A kill switch, a limit on stories in progress, on pull requests per day, on retries of a stage, on fix rounds, on triage sessions, and on unapproved spec pull requests. Beyond a limit it escalates to you and does not retry without end.
- **Least privilege per stage.** Each dispatched stage gets only what it needs: design, tests and impl push branches but cannot open or review a pull request; review and triage can review but cannot push. See `agentctl stage-profile STAGE`. Opening pull requests is the conductor's job, so its author is the Conductor App and you can approve it.
- **Your decisions stay yours.** T2 changes, specs and sprints wait for a person. The conductor goes around a story that waits for you and works on another.

What it does not do:

- It does not make a wrong spec right. It builds what you approved.
- It does not judge code. The gates do, and `agent-review` is the weakest of them ([layer-3-ci.md](layer-3-ci.md)).
- It does not run when the Mac is asleep or the terminal is closed. Nothing advances then. There is no conductor in the cloud.
- It does not support two conductors for one project on different Macs.

## 2. Before you start

- Layers 1, 2 and 3 are in place and their checklists have been run: [layer-1-isolation.md](layer-1-isolation.md), [layer-2-github.md](layer-2-github.md), [layer-3-ci.md](layer-3-ci.md). In particular the layer-2 rulesets (`main`, `main-merge`, `tags`) are active and the layer-3 ruleset `main-checks` is applied (`agentctl rulesets 3`), CODEOWNERS is generated, `ci` has been green on `main`, and Allow auto-merge is on in the repository settings.
- The kit is installed on this Mac and `agentctl` runs from inside the project ([adopting.md](adopting.md)). The launcher runs the kit version pinned in `agentdev.toml` on the default branch.
- The Conductor GitHub App exists, is installed on the repository, and its private key is on this Mac outside the project directory (layer 2).
- `openssl` is on the path. It signs the request for the App's token.
- `git` has an `origin` remote that points at the GitHub repository, and the project is a clone with the default branch fetched. The conductor reads from `origin/main` (the default branch), not from your working directory.
- For each harness you use, its dispatch credential (section 3.1) and its cloud task or integration exist (section 3.4). For a local sandbox (`via = "sbx"`), `agentctl sandbox setup` has been run on this Mac for this project (layer 1).
- A sprint file and the specs it lists are on `main`, or you are about to create the spike's (section 3.9).
- Decide who the conductor works for. One conductor runs for one developer, set by `DEVELOPER`. See section 3.4 for what that means with several people.

## 3. Setup

### 3.1 The settings file

The conductor reads its credentials from a file outside the repository:

```
~/.config/agent-dev/OWNER-REPO/conductor.env
```

If `XDG_CONFIG_HOME` is set it replaces `~/.config`. `OWNER-REPO` is the repository's owner and name joined by a hyphen. The file must not be in the project directory: a clone-mode sandbox can read every file there, ignored ones included. Create it, with the permissions of a secret:

```bash
mkdir -p ~/.config/agent-dev/OWNER-REPO
```

```bash
touch ~/.config/agent-dev/OWNER-REPO/conductor.env && chmod 600 ~/.config/agent-dev/OWNER-REPO/conductor.env
```

It holds `KEY=VALUE` lines; blank lines and lines starting with `#` are ignored, and one level of quotes around a value is removed:

```ini
# The Conductor App. The key path must be absolute; "~" is not expanded.
CONDUCTOR_APP_ID=123456
CONDUCTOR_APP_KEY=/Users/YOU/.config/agent-dev/OWNER-REPO/conductor-app.pem
# Your GitHub login. This conductor does not dispatch a story that the sprint gives to someone else.
DEVELOPER=DIRECTOR_LOGIN
# Dispatch credentials, for the harnesses you use. Plain names: on your Mac they are yours.
CLAUDE_TRIGGER_URL=https://...
CLAUDE_TRIGGER_TOKEN=...
DISPATCH_TOKEN=...
```

`CONDUCTOR_APP_ID`, `CONDUCTOR_APP_KEY` and `DEVELOPER` are required. Without them `agentctl conductor` stops with a message that names the file and the missing keys. The dispatch credentials are needed only for the harnesses your roles use:

| Name | For | Where it comes from |
|---|---|---|
| `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN` | A harness with `via = "http"` (Claude Code on the web): the API trigger of a cloud scheduled task | The scheduled task's API trigger ([layer-1-isolation.md](layer-1-isolation.md), cloud agents) |
| `DISPATCH_TOKEN` | A harness with `via = "comment"` (for example Codex cloud): a GitHub token whose account is the one connected to the cloud task, used to post the mention | A fine-grained personal access token for that account, with issues and pull requests write on this repository |

The variable names come from `url_env` and `token_env` of the harness in `agentdev.toml`; change them there if you want other names. A harness with `via = "sbx"` needs no credential here: its sandbox gets a token from your agent App ([layer-1-isolation.md](layer-1-isolation.md)).

The conductor acts on GitHub as the Conductor App, not as you. It mints the App's token itself from the key on each pass. If it acted as you, you would be the author of the pull requests it opens, and GitHub does not let an author approve their own pull request.

Which credentials a story uses: for a story the sprint gives to `default`, the plain names. For a story the sprint gives to the developer whose login is `DEVELOPER`, the suffixed name first (`DISPATCH_TOKEN_ALICE`, the login in upper case with every other character as `_`), then the plain name. A story given to anyone else is not dispatched from this Mac at all (section 3.4).

The Claude review is not dispatched with these credentials. It runs as a workflow job on GitHub with a secret of the `conductor` environment ([layer-3-ci.md](layer-3-ci.md), section 3.7).

### 3.2 Repository variables the conductor reads

Set in the repository's Settings > Secrets and variables > Actions > Variables (or with `gh variable set`). They hold nothing secret.

| Variable | Meaning | When it is needed |
|---|---|---|
| `CONDUCTOR_PAUSED` | `true` pauses the conductor (section 3.8). Unset or `false` lets it run | Kill switch. Create it as `false` to see the App can read it (checklist F14) |
| `CONDUCTOR_QUOTA` | JSON, for example `{"default/codex": 1795800000}`: the epoch second at which that harness's quota is back. The key is `<developer>/<harness>`, with `default` for the stories of `default` | Marking a harness's quota as exhausted by hand. The conductor then uses the next harness in the list |
| `CONDUCTOR_BOT` | Normally unset. The conductor works out its own login (`APP-SLUG[bot]`) from the App. A login set here is also believed as an author of marker comments | Only if markers written under another login must still be believed. Anyone named there can steer the conductor |
| `REVIEW_BOTS` | Logins whose pull request reviews count as the agent review | See [layer-3-ci.md](layer-3-ci.md) |

### 3.3 Running it

Run it from inside the project, any branch checked out:

```bash
agentctl conductor
```

It prints `conductor is running here as APP-SLUG[bot], every 180s. Ctrl-C stops it.` and then does one pass every 180 seconds (`--interval SECONDS` changes it). Press Ctrl-C to stop it; it prints that nothing advances until it runs again. Leave it in a terminal that stays open (a terminal multiplexer on your Mac does).

What it guarantees about where it reads from:

- On every pass it fetches the default branch and reads the active sprint, the specs, the roadmap and `agentdev.toml` from a detached worktree of `origin/<default branch>` that it keeps inside the repository's git directory (`agentctl-main`). It never reads them from your working tree, so what you have checked out, or an agent's branch, cannot change what it does. The code that runs is the installed kit at the pinned version.
- The sandboxes it starts clone the repository from your project directory (`AGENT_PROJECT_DIR`).

A lock file (`conductor.lock`, in `~/.local/state/agent-dev/OWNER-REPO/`) keeps a second conductor for the same project on the same Mac from starting; it stops with "another conductor for this project is already running on this Mac". The lock is released when the process ends, however it ends. A conductor on another Mac is not supported and nothing stops it. (Known limitation.)

When a pass fails (for example the network is down), it prints `pass failed: ...` and the next pass runs on schedule. After three failed passes in a row it waits 15 minutes between passes until one succeeds, and prints that it does.

When the Mac sleeps or the lid is closed, nothing advances, and nothing is lost: on wake the next pass reads the situation again. Sessions already running in the cloud carry on.

### 3.4 Dry run

To see what it would do, without doing anything:

```bash
agentctl conductor --dry-run
```

It runs one pass, prints the plan with `DRY-RUN` in front of each action, and exits. It takes no lock, so it can run while the conductor runs, and it creates nothing on GitHub: no issue, label, comment, pull request or variable. It still mints the App's token and refreshes the local worktree of `origin/main`. While paused it prints only `halt`, because a paused conductor does not compute a plan.

Read a plan like this: `dispatch story=012 stage=design harness=claude attempt=1` is a stage that would start; `open-pr` is a pushed branch that would get its pull request; `enable-auto-merge`, `disable-auto-merge`, `mark-ready`, `update-branch` are what they say; `notify` and `escalate` are messages to you; `halt` is the pause.

### 3.5 Roles and harness routing

Everything about who does what is in `agentdev.toml`, over the kit's defaults (`tools/agentctl/defaults.toml`). A list replaces the default as a whole; tables merge key by key. A change to `agentdev.toml` is T2.

**Harnesses.** A harness says how a stage is started. Each is a table `[roles.harness.NAME]` with `via`:

| `via` | What it does | Needs |
|---|---|---|
| `http` | POSTs the prompt to the API trigger of a cloud scheduled task (Claude Code on the web) | `url_env`, `token_env` in `conductor.env`. The URL must start with `https://` |
| `comment` | Posts `<mention> <prompt>` as a comment on the story's pull request, or on its issue before one exists, as the account behind the token (Codex cloud reads `@codex`) | `token_env` in `conductor.env`; `mention` |
| `sbx` | Starts a fresh clone-mode Docker Sandbox on this Mac for the stage and removes it afterwards (`agentctl sandbox job ...`). Used for Ollama, and as the fallback for a cloud path that does not work | `agentctl sandbox setup` done on this Mac. Only runs while the conductor runs on this Mac |
| `review_workflow` (on a harness) | A review stage runs as a workflow job, so the job sets the `agent-review` status itself. The default for `claude` is `agentdev-agent-review.yml` | The `conductor` environment secret `CLAUDE_CODE_OAUTH_TOKEN` ([layer-3-ci.md](layer-3-ci.md)) |

The defaults define `claude` (`http`, with `review_workflow`), `codex` (`comment`, `@codex`) and `ollama` (`sbx`). The conductor sends the whole rendered stage prompt in each dispatch; prompts belong to the kit (`prompts/*.md`, filled in from `agentdev.toml`). To see one:

```bash
agentctl prompt impl
```

**Stages per developer.** For every stage, harnesses are tried in order; the first one whose quota is available is used. `default` covers a story with no assignee and anyone not listed:

```toml
[roles.developers.default.stages]
design = ["claude"]
tests = ["claude"]
impl = ["claude", "codex"]
review = ["codex", "claude"]
triage = ["claude"]
```

Fix rounds and conflict resolution use the `impl` list. For `review`, the conductor puts a harness other than the one that implemented the story first when the developer has a choice, so the reviewer and the implementer differ.

| Setup | Reviewer | What you give up |
|---|---|---|
| One person, one vendor | A fresh session of the same harness | Cross-vendor review. The mechanical checks carry the main guarantee |
| One person, several vendors | A different vendor from the implementer | Nothing, while quota lasts on both |
| Several people, each with their own AI | Whatever each person's own set allows | A person with one vendor gets same-vendor review on their stories |

If you use only Codex, list `codex` for every stage, set `planner = "codex"`, and have your reviews come from the Codex integration through the bridge (`REVIEW_BOTS`). If you use only Claude, the defaults need only a change to `impl` and `review` lists to name `claude` alone.

**People.** `[roles] directors` approve specs and sprints and own the guardrails in CODEOWNERS. `humans` is everyone whose approval counts for a T2 change; directors are included. `planner` is the harness that drafts specs and sprints when no developer is implied. `agentctl init DIRECTOR [HUMAN ...]` fills in the first two.

**Whose story is it.** It comes from the sprint file, never from an issue's assignee: `assignee` is the default for the sprint, and an `[owners]` table names another developer for single stories. A conductor dispatches the stories given to its own `DEVELOPER` and the stories of `default`. A story given to someone else is deferred, by whatever route its harness starts: nothing is written, and the plan prints `deferred`. It is dispatched by the conductor on that person's Mac, with `DEVELOPER` set to their login. Their `via = "sbx"` stages therefore only advance while their conductor runs. The other person's conductor does everything that is not a dispatch for your stories too (opening pull requests, marking them ready, updating branches), so there is no gap there, but two conductors for one project is exactly what is not supported. With more than one developer, decide before you start who runs the conductor, and give the sprint's stories to `default` or to that person. (Known limitation.)

### 3.6 Sprints and specs

The conductor reads these from the default branch, in the paths set by `[paths]` (defaults shown):

| What | Where | Notes |
|---|---|---|
| Roadmap | `docs/product/roadmap.md` | One requirement per line, as `- [ ] text` (unchecked: no spec yet) or `- [x] text` (spec exists). While there are unchecked lines, and fewer than `max_open_spec_prs` unapproved spec pull requests, the conductor dispatches the product-owner stage to draft one spec for the first unchecked line |
| Sprint | `docs/sprints/NNN.toml` | The highest-numbered file is the active sprint. Keys: `goal`, `length_days`, `stories` (list of ids), `assignee` (default `"default"`), optional `[owners]` (`"012" = "alice"`). Sprint 000 is the empty placeholder `agentctl init` creates; it dispatches nothing |
| Story | `docs/specs/NNN-slug/` | `story.md` and `story-<lang>.md` (the language you approve in), and `spec.toml` with `priority`, `size`, `risk`, `depends_on`, `touches`, the ACs, the TCs and `done_when`. `examples/specs/000-example/` in the kit is a worked example |

`depends_on` (stories that must be merged first) and `touches` (modules and shared resources the story changes, such as `db:orders`) are written by the planner and approved by you with the sprint. A story that depends on one not in the sprint, or a cycle, stops the sprint and escalates once. `touches` is a prediction and will miss things; the cost is a merge conflict, which the conductor hands to an agent to resolve.

Story ids are `[stories] id_digits` long (3 by default). For each story in the active sprint the conductor creates (once) a tracking issue labelled `story:NNN`, and a sprint issue labelled `sprint:NNN`; these hold its markers and notices. A story's branch is exactly `story/NNN-slug` with the slug from its spec; a branch `story/NNN-other` is ignored.

### 3.7 The stage flow

For each story, one stage at a time. Each stage is a new agent session with no memory; everything it needs is in the spec, the issue, the branch and the history.

| Order | Stage | What happens | Reported by |
|---|---|---|---|
| 1 | `design` | The design agent writes the design document and pushes `story/NNN-slug` | The agent adds the label `done:design` to the story issue |
| 2 | `tests` | The test agent writes tests from the story alone; they must fail at this point | `done:tests` |
| 3 | `impl` | The implementation agent makes the tests pass | `done:impl` |
| 4 | mark ready | The conductor opened the pull request as a draft when the branch was first pushed. After `done:impl` it marks it ready, and the full gates run for the first time | |
| 5 | `review` | When the mechanical checks are green, the review is dispatched for the head commit and sets `agent-review` | The status on the commit; `done:review` for the workflow route |
| 6 | merge | In shadow mode: you merge. After `auto_merge_tiers`: the conductor enables auto-merge. Then `evidence` posts the table on the story's issue | |

Other stages: `fix` (the checks fail, or the review asks for changes; up to `max_fix_rounds`), `resolve-conflict` (the branch conflicts with main), `triage` (a stage failed or stalled repeatedly), `fix-main` (main is red; one repair task, and nothing else is dispatched until main is green), `product-owner` (draft a spec from the roadmap), `planner` (draft the next sprint, once `draft_next_sprint_at` of the stories are merged).

Ties to a commit: a fix, a conflict resolution and a review are tied to the commit they were dispatched for. A fix counts as in flight until the branch moves. Every new commit needs its own review verdict. When a branch is behind main, the conductor updates it.

Pull requests: the conductor opens one for any pushed branch under `story/`, `spec/`, `sprint/` or `chore/` that has none into the default branch. A story gets a draft; the others get a pull request ready for review. It opens at most `max_prs_per_day` story pull requests a day (counted by UTC date).

**Spec and sprint pull requests** are your decision. Approve one as a code owner and, at its next pass, the conductor enables auto-merge on it, and it merges when the checks are green. That does not depend on `auto_merge_tiers`. A pull request nobody has to review has no review decision and is never picked up that way. A `chore/` pull request is never merged by the conductor: you merge it.

Waiting on you: a story whose pull request is T2 with everything else green, a requested review, or the label `needs-human` or `blocked` waits for a person. It holds no slot among the stories in progress, but it keeps its claim on what it `touches`. The conductor goes around it. When every unfinished story is waiting on a person, it stops and notifies you once. When the sprint is complete it notifies you and development stops until the next sprint is approved; only the drafting of specs goes on.

### 3.8 Fuses, the kill switch and escalation

Defaults are in `[conductor]` of `defaults.toml`:

| Setting | Default | Meaning |
|---|---|---|
| `wip_limit` | 2 | Stories in progress at once. Stories waiting on a person do not use a slot |
| `max_prs_per_day` | 10 | Story pull requests opened per day |
| `max_attempts` | 2 | Dispatches of the same stage before a triage session is asked |
| `max_fix_rounds` | 3 | Fix, review loops before a person is asked |
| `max_triage` | 1 | Triage sessions per story before a person is asked |
| `max_open_spec_prs` | 3 | Unapproved spec pull requests the product-owner stage may leave waiting |
| `draft_next_sprint_at` | 0.8 | Share of the sprint merged at which the next sprint is drafted |
| `stage_timeout_minutes` | default 90, design 45, review 45, triage 30, product-owner 60 | How long a dispatched stage may run before it counts as stalled |
| `max_parked_hours` | 72 | A story parked for a dependency that triage added is escalated when nothing has happened for longer than this |
| `max_dispatches_per_story` | 15 | Sessions of every stage together, counted since the story's last escalation. A story that would start a session beyond this is escalated instead; one whose last session finished it is not |
| `remind_after_hours` | 48 | A story waiting on a person (`needs-human`, `blocked`, a T2 or review approval) is mentioned again on the sprint issue, once per wait. The reminder does not suppress the "sprint stalled" notice |
| `auto_merge_tiers` | `[]` | Tiers the conductor may merge (section 3.10) |

**Stalled and failed stages.** A stage that has not reported when its timeout passes is dispatched again (attempt 2). After `max_attempts` a triage session is dispatched. The triage agent can only add a "blocked by" link, ask for a retry with an explanation, or escalate with options; it cannot change the spec, the sprint, code or tests. After `max_triage` the story is escalated.

**Escalation.** The conductor adds the label `needs-human` to the story issue and comments with a mention of every login in `[roles] humans`. It does not assign the issue to anyone. It goes around the story from then on. To resume: read the explanation and options on the issue, decide, remove the label, and change the spec by a normal spec pull request if it needs changing. Add `blocked` to leave a story alone on purpose. Escalation happens for: a stage failing after its retries and triage; checks or review still failing after `max_fix_rounds`; stages reported done but no branch or pull request; a broken sprint plan (missing dependency or cycle); a story parked longer than `max_parked_hours`; a story that used `max_dispatches_per_story` sessions. An escalation names the stories waiting for the escalated one ("Waiting for it: 002."). Those are not escalated themselves; settling the one frees them. When parked stories come back, one whose session is still running is admitted first and keeps what it touches, so a returning story never starts beside it.

**The kill switch.** Set the repository variable `CONDUCTOR_PAUSED` to `true`:

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

It is read live on every pass. While paused the conductor dispatches nothing and opens no pull request. It does one thing: it switches off auto-merge on every open pull request that has it on, because GitHub would otherwise merge such a pull request by itself when its checks turn green. That happens when the next pass runs, not at the moment you set the variable, so for an immediate stop also run, for each such pull request:

```bash
gh pr merge NUMBER --disable-auto
```

Sessions already running are not stopped. To resume:

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

`CONDUCTOR_PAUSED`, `CONDUCTOR_BOT` and `CONDUCTOR_QUOTA` are read first and together. A variable that cannot be read is not taken as unset: the pass behaves as if paused (it prints "treated as paused: cannot read the repository variable ..."). Dispatching stops at once; auto-merge already on is withdrawn only by a pass that could list the pull requests and call GitHub successfully. If GitHub's API is failing altogether, `gh pr merge NUMBER --disable-auto` is the fallback. (**To verify**: `--disable-auto` as the Conductor App.)

### 3.9 The spike: prove one full loop first

Before real stories, use a toy story to verify the whole path with the conductor in shadow mode. The spike is sprint 001. The goal is to see this sequence without a manual command beyond the ones shown. Do it with one person's setup complete, on one cloud path at a time, and have Claude and Codex each do the implementation once if you use both.

Nobody opens a pull request by hand: a branch is pushed, and the conductor opens the pull request as the Conductor App. A pull request you opened yourself you could not approve.

1. With the conductor not running, create the spike's spec and sprint on a branch `sprint/001`, from the templates `agentctl init` copied:

```bash
git switch -c sprint/001
```

```bash
cp -R docs/specs/_template docs/specs/001-hello
```

```bash
cp docs/sprints/_template.toml docs/sprints/001.toml
```

   Fill in the three spec files (a small feature with one AC and two TCs) and the sprint file (`stories = ["001"]`). Leave `assignee` as `default` if the credentials in `conductor.env` carry plain names. Use your login only if you also use suffixed names. A story given to a named person uses that person's suffixed names first, and falls back to the plain ones only on that person's own Mac.

   Keep the toy feature in the project's own language and make sure `[tests]` in `agentdev.toml` runs it and writes JUnit XML ([layer-3-ci.md](layer-3-ci.md), section 3.3). A test carries its TC id in its name, for example `test_tc_001_01_says_hello`. Then check, commit and push:

```bash
git add docs/specs/001-hello docs/sprints/001.toml && git commit -m "Add the spike story and sprint 001" && git push -u origin sprint/001
```

2. Pause, so that the merge of the sprint file does not start a live run, then start the conductor:

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

```bash
agentctl conductor
```

   Leave it running. Paused, it prints only `halt`.

3. Unpause for one pass only if you want it to open the pull request: the conductor opens nothing while paused. Alternatively open it by pushing and unpausing, then pause again before the merge. A simpler order: unpause, wait for the conductor to open the pull request for `sprint/001` (ready for review), then pause before approving.

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

   Wait until `ci`, `security`, `spec-verify` and `agent-review` are green. `risk-gate` is red at this point, and that is correct: a spec and a sprint file are T2 and `risk-gate` passes only once a person in `[roles] humans` has approved the current commit.

4. Pause, approve the pull request, and merge it yourself this once, so that the next step starts from a known state:

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

```bash
gh pr merge sprint/001 --squash
```

5. Ask for a plan while paused. It prints only `halt (kill switch is on)`. That confirms the kill switch works:

```bash
agentctl conductor --dry-run
```

6. Unpause and ask for a plan at once:

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

```bash
agentctl conductor --dry-run
```

   It should list a dispatch of `design` for story 001 and nothing surprising. The running conductor does its own pass within three minutes, so the live run may come first; that is harmless here.
7. The conductor dispatches `design`. The agent pushes `story/001-hello` and the conductor opens the pull request as a draft. On a draft, `ci` runs lint only, `risk-gate` runs, and `security` and `spec-verify` are skipped.
8. `done:design`, `done:tests` and `done:impl` appear in that order. After `done:impl` the conductor marks the pull request ready, and the full gates run for the first time.
9. `agent-review` is dispatched for the head commit and writes the status on it. A review that did not finish is published as failure, never left as a pass.
10. All five checks are green, and the head commit also carries a status `risk-tier/T1` (or `T0`). In shadow mode the conductor comments on the sprint issue that the pull request can be merged; you press merge.
11. `evidence` posts the traceability table to the story issue.

If any step gets stuck, note where and the error message:

| Where it gets stuck | What to do |
|---|---|
| The conductor stops at start with "must define ..." | `conductor.env` is missing or lacks `CONDUCTOR_APP_ID`, `CONDUCTOR_APP_KEY` or `DEVELOPER`. The message names the file |
| A pass fails reading state | Look at the `pass failed:` line. The reading code (`collect` in `tools/agentctl/github.py`) has not been run against the real API. Fix it in the kit and write the result back |
| It cannot get a token | The key path is not absolute, the App is not installed on the repository, or `openssl` is missing |
| A branch was pushed but no pull request appears | The conductor is paused or not running, the branch name does not start with `story/`, `spec/`, `sprint/` or `chore/`, a `story/` branch is not the exact name from a spec, or `max_prs_per_day` is reached. Wait one interval |
| The pull request was opened but the checks did not run | It must be opened by the Conductor App, not with `GITHUB_TOKEN`. The checks run only for pull requests into the default branch |
| An approved spec or sprint pull request does not merge | The conductor enables auto-merge at its next pass after the approval. Check that it runs and is not paused, that Allow auto-merge is on, that the approval came from a code owner, and that all five checks are green on the commit you approved. A push after your approval invalidates it |
| A harness cannot be triggered from the cloud | Change it to `via = "sbx"` in `agentdev.toml` (a T2 change on a `chore/` branch). Its stages then run in a Docker Sandbox on this Mac while the conductor runs |
| The plan says `deferred` | The story is given to another developer. Give it to `default` or to your login, or run the conductor on that developer's Mac |
| The dispatch fails with "no dispatch token configured" or "no https trigger URL configured" | The credential is missing from `conductor.env` for that harness and developer |
| The agent did not add the `done:*` label | The agent identity needs write access to issues. Strengthen the prompt if necessary |
| `agent-review` stays pending | See [layer-3-ci.md](layer-3-ci.md), section 3.7: the workflow's `publish` job sets failure when the review did not finish, so pending means the run never started, could not resolve the pull request, or stopped because the branch had moved. For a bot or sandbox review, check `REVIEW_BOTS` |
| `spec-verify` fails at "Keep only plain result files" | The results contained a symbolic link. Look at what the test step wrote under `reports/` |
| Red-green fails with "its test did not run on base" | The story's test files were not picked up on the base branch. Check `test_paths` and that the TC id is in the test's name |
| The conductor never enables auto-merge on a green story pull request although its tier is in `auto_merge_tiers` | It reads the tier from the commit status `risk-tier/T?`. Check that the status is on the head commit |

Also record the numbers [layer-3-ci.md](layer-3-ci.md) asks for (minutes per test run, full gate runs per story, Actions minutes per story).

The first real sprint is then sprint 002. Add a few lines to the roadmap and merge them, or discuss them in a chat with the product-owner agent. The product-owner stage pushes a `spec/` branch for each story and the conductor opens the pull request. Approve it. The planner drafts the next sprint when the current one is nearly complete; for the first real sprint, ask it by hand (a session following the `planner` prompt, `agentctl prompt planner`). Approve the sprint pull request, and the conductor takes over from there.

### 3.10 Turning on auto-merge in stages

`auto_merge_tiers = []` is shadow mode, the default. Every gate is computed and reported, but you press merge; the conductor only comments on the sprint issue that a story "can be merged". A new project's tests are not yet good enough to be the basis for merging.

Stay in shadow mode for at least one sprint. Each time the conductor says a pull request can be merged, spend a minute making your own judgement and note whether you agree. When you have agreed consistently, change `agentdev.toml` on a `chore/` branch:

```toml
[conductor]
auto_merge_tiers = ["T0"]
```

After a further while, add `"T1"`. The change is T2 and needs your approval. T2 is never accepted in this list. The credibility of auto-merge is capped by the quality of the tests, which is why it is done in stages.

How it works: when every gate has passed on a story pull request whose tier (the `risk-tier/*` commit status, not the label) is listed, the conductor enables auto-merge for that exact commit (`--match-head-commit`). If the branch has moved, GitHub refuses and the next pass decides again. GitHub keeps an auto-merge request across later pushes, so on every pass the conductor withdraws it from a pull request that no longer qualifies (a draft, a human review outstanding, a check or `agent-review` not green, or a tier not listed) and enables it again when it qualifies. It also withdraws it from every story pull request when main is red, when the sprint plan is broken (a missing dependency or a cycle), and when no story of the active sprint vouches for an armed story pull request. The tier it goes by is the `risk-tier/*` status whose description says "pull request #N into BRANCH" for that pull request into the default branch; a status computed for another pull request or base is not believed. Between a push and the next pass the request is still armed. GitHub itself still requires all five checks on the new commit, and `risk-gate` fails a T2 commit until a person approves. What that window can let through is a commit of a tier above the enabled ones but below T2 (T1 while only T0 is enabled) that also passes `ci`, `spec-verify` and `agent-review` before the conductor's next pass. (**To verify**: that GitHub keeps the request across a push; see D22.)

### 3.11 Adding a person

1. They join the organization and become a repository admin ([layer-2-github.md](layer-2-github.md)).
2. In `agentdev.toml`, add their login to `[roles] humans`, and give them a `[roles.developers.LOGIN.stages]` table. Regenerate CODEOWNERS (`agentctl codeowners > .github/CODEOWNERS`) and commit both in one pull request. Add them to `directors` only if they are to approve product decisions: only directors own `docs/specs/`, `docs/sprints/` and `docs/product/`. This is a T2 change.
3. They follow [layer-1-isolation.md](layer-1-isolation.md): their own agent App, their sandbox, their own cloud accounts. Their review token goes in the `conductor` environment as `CLAUDE_CODE_OAUTH_TOKEN_<LOGIN>`; their dispatch credentials go in the `conductor.env` on their own Mac, with `DEVELOPER` set to their login.
4. For stories that are theirs, name them in the sprint file's `[owners]` table or make them the sprint's `assignee`. Setting the assignee on the issue has no effect.
5. Decide who runs the conductor (section 3.5). Only one conductor may run for the project.

### 3.12 Day to day

You do four things: add a line to the roadmap or say one sentence to the product-owner agent; approve or answer spec pull requests; approve sprint pull requests; push release tags. You look at two places: the Director's brief (one fixed issue, updated daily, with a weekly audit section on Monday: merges per tier, reverts, escalations, and a random sample of pull requests merged without a human, for you to spot-check) and your GitHub notifications (pull requests that need your review and issues that mention you).

| Situation | What to do |
|---|---|
| You want to pause everything | Set `CONDUCTOR_PAUSED` to `true` (section 3.8) |
| You want to know the current state | The Director's brief issue, or `agentctl status --markdown` |
| You want to know what the conductor will do next | `agentctl conductor --dry-run` |
| A story has been labelled `needs-human` | Read the triage explanation and options on the issue, decide, remove the label. If the spec needs changing, change the spec |
| A harness's quota is exhausted | Set `CONDUCTOR_QUOTA` (section 3.2). When it expires the conductor uses the harness again |
| You want a story left alone for now | Add the `blocked` label to its issue |
| You want to release | Put a `v*` tag on the commit you want on `main` and push it. The release template fails unless `ci / ci`, `security / security` and `ci / spec-verify` are each present and green on that commit |
| You want to know how much Actions has been used | `agentctl budget --dry-run`, or the first line of the brief. It is an estimate |
| The Actions allowance is running out | See [layer-3-ci.md](layer-3-ci.md), section 3.8. Overflow is off; CI stops until next month or until you pay for more |
| A story should run on a particular person's subscriptions | Name them in the sprint file (`assignee`, `[owners]`) |
| A review stage has to run in a local sandbox | Give that harness `via = "sbx"` and no `review_workflow`, and add the reviewing developer's agent App login to `REVIEW_BOTS` |
| A `chore/` pull request is ready | Merge it yourself. The conductor never merges one |
| You need to change the pipeline itself | Ask the agent directly in a session; the work happens on a `chore/` branch and you approve the pull request |
| You closed the laptop | Nothing advances. On wake the next pass carries on. There is no hand-over to the cloud |
| You suspect something is wrong | Pause, then run the checklists of all four layers |

## 4. Checklist

Run it once when the setup is complete, and again after you change `agentdev.toml`, the kit version or the conductor's credentials. **Most items attempt something that must fail or be refused.** If such an attempt succeeds, a line of defence is not working. A few items check that the normal path works and expect success: D16, F2 and F17. D22 expects success in part. The "Expected" column says which.

Note the message you actually saw in the "Result" column. None of these items has been run against real GitHub, so a result that differs may also mean this checklist is wrong. Write that back too. Item ids are shared with the other layer documents and never reused. F5, F8 (the lease and the Actions conductor) no longer exist; their ids stay retired. F6, F10 and F17 are rewritten for the lock file and the single local conductor.

### D. Gates that involve the conductor

Items D1 to D8, D11 to D15, D17 to D19 and D21 are in [layer-3-ci.md](layer-3-ci.md); D9, D10 and D23 are in [layer-2-github.md](layer-2-github.md).

| # | Attempt | Expected | Result |
|---|---|---|---|
| D16 | Push a branch `spec/NNN-slug` with a new spec and wait. Then approve the PR and do nothing else | The conductor opens the PR, ready for review, without auto-merge. After your approval, the conductor's next pass enables auto-merge, and with green checks the PR merges. This one should SUCCEED. Before your approval auto-merge must not be enabled and it must not merge | |
| D20 | Tier label. Put only `T0` in `auto_merge_tiers` (`agentdev.toml`, on main). Take a story PR that is T1 with every check green. With the agent's token, change its label from `tier:T1` to `tier:T0`: `gh api repos/OWNER/REPO/issues/N/labels -f "labels[]=tier:T0"`, then `gh api --method DELETE repos/OWNER/REPO/issues/N/labels/tier:T1`. Run `agentctl conductor --dry-run` | The conductor does not plan `enable-auto-merge` for that PR. It reads `risk-tier/T1` from the commit status on the head commit, not the label, and reports that the merge is left to a human. Auto-merge stays off | |
| D22 | Auto-merge across a push. Put `T1` in `auto_merge_tiers`, or use a T0 change with `T0` enabled. Wait until the conductor has enabled auto-merge on a story PR whose head is eligible but which has not merged yet (hold one required check back, for example by leaving the branch behind `main`). Then push a new commit to the branch as the agent App, from an impl sandbox | Record whether GitHub keeps the auto-merge request after the push (`gh pr view N --json autoMergeRequest`). If it does, the conductor's next pass outputs `disable-auto-merge` for that story, because the new head does not yet have green checks and a review verdict, and afterwards the request is gone. It is enabled again only when the new head qualifies. The part that should SUCCEED is that last one. Between the push and that pass the request is armed: note how long that was | |

### F. Conductor

| # | Attempt | Expected | Result |
|---|---|---|---|
| F1 | Set `CONDUCTOR_PAUSED=true`, with the conductor running | Within one pass it prints halt, dispatches nothing and opens no PR. If an open PR has auto-merge on, it also switches that off (F13) | |
| F2 | Run `agentctl conductor --dry-run` | It lists the actions it would take and does not carry them out. It creates nothing: no issue, no label, no comment, no variable. This one should SUCCEED | |
| F3 | Run `agentctl conductor` over two passes with a story whose stage is in progress | The second pass does not dispatch again a stage that is already in progress | |
| F4 | Label a story `needs-human` | The next pass skips it and advances the other stories | |
| F6 | Kill the conductor outright (`kill -9` its PID, or close the terminal without Ctrl-C), then start it again at once | The lock does not stay behind: the new conductor starts. It does not dispatch again a stage whose marker is already on the issue. Nothing is lost | |
| F7 | In a story agent's sandbox, ask the agent to modify `agentdev.toml` | Blocked by a deny rule; even if that is bypassed, the PR is T2 and needs your approval | |
| F9 | Forge a marker with an agent identity. Run `agentctl conductor --dry-run` and pick a story for which it plans to dispatch `design`. With the agent's token, comment on its issue: `<!-- conductor {"id":"forged","stage":"design","at":EPOCH_NOW,"harness":"claude","attempt":1} -->`. Then run the dry run again | The comment is ignored: the dry run still plans to dispatch `design` for that story, as it did before the comment. The same comment written by a person listed in `[roles] humans` is believed, so delete the test comment afterwards | |
| F10 | While `agentctl conductor` runs in one terminal, start a second `agentctl conductor` for the same project on the same Mac | The second stops at once with "another conductor for this project is already running on this Mac" and the path of the lock file. The first carries on. (Two conductors on two Macs are not supported, and nothing prevents them: do not test that on a live project) | |
| F11 | While the conductor runs, set `CONDUCTOR_PAUSED` to `true` | Within one pass it prints `halt (kill switch is on)` and dispatches nothing. Apart from switching off auto-merge where it is on (F13), it does nothing else. It resumes within one pass after the variable is set back to `false` | |
| F12 | Interrupt a dispatch between the marker and the send. In `conductor.env`, point `CLAUDE_TRIGGER_URL` at an `https://` address that accepts the connection and never answers. Run the conductor. As soon as the comment "Dispatching ..." appears on the story issue, kill the process with `kill -9`. You have about 30 seconds before the send gives up by itself. Restore the URL and start the conductor again | The marker is on the issue and no session started. The following passes do not dispatch that stage again. After the stage's timeout in `[conductor.stage_timeout_minutes]` it is dispatched once more, as attempt 2. At no point do two sessions run for the same stage | |
| F13 | Pause with auto-merge already on. As an admin, enable auto-merge on an open test PR whose checks are not green yet: `gh pr merge N --auto --squash`. Set `CONDUCTOR_PAUSED=true` and look at the PR. Then let the conductor make a pass | Setting the variable alone changes nothing on the PR: auto-merge is still on. The pass outputs halt and `disable-auto-merge (#N)`. Afterwards `gh pr view N --json autoMergeRequest` shows none | |
| F14 | Pause read failure. This cannot easily be forced on real GitHub. It is covered by a unit test and by reading `variable()` in `tools/agentctl/github.py`: a failed read raises, and the conductor then behaves as paused. What to confirm here is that the Conductor App's token can read repository variables. Set `CONDUCTOR_PAUSED` to `false` and run `agentctl conductor --dry-run` | Look in the output for a `halt` line that says "treated as paused: cannot read the repository variable ...". It must not be there. Do not judge by the absence of dispatches: a plan with nothing to do also dispatches nothing. If the line is there, with HTTP 403, the App may not read repository variables, and every pass will behave as paused | |
| F15 | A credential that is missing. Pick a story that the sprint gives to `default`, whose next stage uses a `via = "http"` or `"comment"` harness. Remove its credential from `conductor.env` (`CLAUDE_TRIGGER_URL` or `DISPATCH_TOKEN`) and run the conductor. Then give a story to another developer in the sprint file and run it again. For a Claude review, repeat with the `conductor` environment secret `CLAUDE_CODE_OAUTH_TOKEN` (or `_<LOGIN>`) deleted. Restore everything afterwards | Missing credential: the dispatch fails with "no https trigger URL configured for harness '...'" or "no dispatch token configured ...", naming the developer when there is one. Nothing is written: no marker comment on the story issue. Story of another developer: the plan prints `deferred: story NNN belongs to ...; this conductor runs for ...` and nothing is written. Missing review secret: the workflow starts (this conductor cannot see GitHub's secrets), the review step fails, and `agent-review` on the head commit is failure. It never runs on the plain-named secret for a named developer | |
| F16 | Local Codex review in a sandbox. For a story whose review stage runs Codex with `via = "sbx"`, let the conductor dispatch the review. Do it once while the reviewing identity's login is absent from the repository variable `REVIEW_BOTS`, and once while it is listed. The second observation needs a new head commit, or the first review's verdict: the first dispatch left a marker, and that marker changes what the next pass does | The review reaches the `agent-review` status only when the login of the identity that submitted it is listed in `REVIEW_BOTS`. Absent: the review appears on the PR and no status is written. Listed: the `bridge` job writes the status on the reviewed commit, and this part should SUCCEED. Note the login you actually saw | |
| F17 | Run `agentctl conductor --dry-run` while the conductor is running in another terminal | It does one pass, prints the plan and exits, without waiting for or disturbing the lock. The running conductor is unaffected and nothing is created. This one should SUCCEED | |
| F18 | Three failed passes. With a story due for dispatch, set `CLAUDE_TRIGGER_URL` in `conductor.env` to an `https://` address that refuses connections, and start the conductor. Restore it afterwards | Each pass prints `FAILED: ...` for the dispatch (and no marker stays on the issue). After the third in a row it prints "3 passes in a row failed; next pass in 15 minutes". After the URL is restored the next pass that succeeds returns it to the normal interval | |
| F19 | Missing settings. Rename `conductor.env` and run `agentctl conductor` | It stops at once with a message that names the file and the missing keys. It does not start a pass | |
| F20 | The conductor reads the default branch. In your working directory, edit the active sprint file (for example add a story) without committing or pushing, and run `agentctl conductor --dry-run`. Then check out another branch with a different `agentdev.toml` and run it again | The plan reflects `origin/main` both times: the uncommitted story is not planned, and the other branch's settings are not used | |
| F21 | Sleep. With the conductor running and a stage in flight in the cloud, put the Mac to sleep for longer than the stage's timeout, then wake it | Nothing is dispatched while it sleeps. After waking, the next pass treats the stalled stage by the normal rule: dispatched again as attempt 2 if it never reported, not dispatched if it did report. Note what happened | |
| F22 | Spec drafting limit. Put four unchecked lines in the roadmap on `main`, with no spec pull requests open | The conductor dispatches the product-owner stage once at a time, and never leaves more than `max_open_spec_prs` unapproved spec pull requests open | |
| F23 | Parked too long. Park a story (triage adds a dependency on an unfinished story) and let it sit past `max_parked_hours` (set it to 1 for the test) | The story is labelled `needs-human` with a comment saying it has waited for the named story for over that many hours. It is escalated once, not every pass | |
| F24 | Session limit. Set `max_dispatches_per_story` to 3 and let a story use three sessions without finishing | When it would start a fourth, it is escalated with "3 sessions without finishing". Remove `needs-human`: it gets three more sessions before the next escalation | |
| F25 | Waiting for the escalated one. Escalate story A while story B depends on it (by a triage dependency) | The comment on A ends "Waiting for it: B." B is not labelled `needs-human`. After you settle A, B resumes | |
| F26 | Reminder. Leave a story at `needs-human` (or a T2 PR unapproved) past `remind_after_hours` (set it to 1) | One more mention on the sprint issue, once per wait. If every unfinished story is waiting, the "sprint stalled" notice still comes | |
| F27 | Returning stories. Park two stories that touch the same thing while one has a session running, then satisfy the dependency | The one with the running session is admitted first and keeps its claim; the other does not start beside it | |
| F28 | Clearing a parked story. Let F23 escalate a parked story, then remove `needs-human` | It is not escalated again until another `max_parked_hours` have passed | |

## 5. Not yet verified

Nothing in this layer has run against real GitHub, the vendors' cloud services, Docker Sandboxes or a Mac. The points where a surprise is most likely:

- Everything in `collect` and `execute` of `tools/agentctl/github.py` against the real API: the shape of `statusCheckRollup`, `reviewDecision`, `autoMergeRequest`, issue dependencies (`blocked_by`), and a check name as GitHub reports it. The conductor strips the caller part of `<caller job> / <job>`.
- Whether GitHub keeps an auto-merge request across a push, and `--disable-auto` and `--match-head-commit` as the Conductor App (D22, section 3.10).
- Whether the Conductor App's token can read repository variables and dispatch workflows (F14), and whether `CONDUCTOR_PAUSED` can be created once and read reliably.
- Which cloud route works for each vendor: Claude Code on the web's scheduled task API trigger (`via = "http"`), and a mention that starts a Codex cloud task (`via = "comment"`), including that the comment must come from the account connected to the cloud task. The spike decides this; for a path that does not work, use `via = "sbx"`.
- The `agent-review` workflow route, and the login and format of a review bot's review ([layer-3-ci.md](layer-3-ci.md)).
- The local sandbox route (`agentctl sandbox job`): Docker Sandboxes behaviour, one fresh sandbox per stage, and its removal afterwards ([layer-1-isolation.md](layer-1-isolation.md)).
- The agents' own behaviour: that they add the `done:*` labels, push once at the end of a stage, and stay within their prompt. The prompts have not been tried.
- The timings: stage timeouts, and the 180-second pass against GitHub's rate limits.
- The numbers in the minutes table of the guideline.

## 6. Known limitations

- **One conductor, on one Mac.** The lock file stops a second conductor on the same Mac. A second conductor on another Mac is not supported and nothing prevents it. Two of them could dispatch the same stage twice (never lose one: the marker is written first).
- **When the Mac sleeps or the terminal closes, nothing advances.** There is no conductor in the cloud, no hand-over and no notice that it stopped. Work already dispatched to the cloud carries on, and the next pass notices stalls by the stage timeouts.
- **With several developers, one conductor does not dispatch other people's stories.** A story given to another login waits until a conductor runs on that person's Mac. A stage with `via = "sbx"` only starts on the Mac of the developer whose story it is.
- **The conductor's key is on the host.** The Conductor App's private key sits on your Mac, outside the project directory, where no sandbox can see it, but on the host. Anyone with access to your account can use it.
- **A pull request that edits a caller workflow chooses the workflow that judges it.** For `pull_request` events GitHub runs the PR's own workflow files, so a changed `uses:` or `kit_version:` decides which kit produces that PR's check results. The defence is CODEOWNERS on `.github/**` and your reading of the diff; green checks on such a PR say little ([layer-3-ci.md](layer-3-ci.md)). A mitigation to evaluate is GitHub's ruleset rule "require workflows to pass", which runs a workflow from a fixed repository and ref instead of the PR's copy. Its availability on the Team plan is not verified.
- **The sandbox start code is still being reworked.** See [layer-1-isolation.md](layer-1-isolation.md) for the state of `sbx.sh job` when `sbx create` or `sbx secret set` fails.
- **A malformed `CONDUCTOR_QUOTA` is ignored entry by entry.** A bad entry means that harness is treated as having quota; you will not be told. Keep the variable valid JSON.
- **The network probe cannot tell an origin's own 403 or 5xx from a policy denial**, so a sandbox start check can report a block that is not one, or the other way round. See [layer-1-isolation.md](layer-1-isolation.md).
- **`touches` is a prediction and will miss things.** The cost is merge conflicts and rework, corrected afterwards by triage and the conflict-resolution stage. It does not lead to wrong code being merged.
- **Capacity is limited by subscription quota.** When quota runs out, work slows down; it does not fail. The conductor does not read quota from the vendors: you set `CONDUCTOR_QUOTA` by hand.
- **Cloud triggering depends on features both vendors are still changing.** The fallback is a local sandbox, which needs the Mac on and the conductor running.
- **The conductor's login is accepted as a marker author with and without its `[bot]` suffix.** A person whose login equals the Conductor App's slug would be believed as a marker author. They would also have to be a collaborator on the repository to comment at all.
- **While you are away, decisions accumulate.** What waits for you (T2 pull requests, escalations, specs, sprints) is the one pace in the system that you set.
- **Actions usage is an estimate**, and the allowance is not extended automatically ([layer-3-ci.md](layer-3-ci.md)).
