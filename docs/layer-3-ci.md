# Layer 3: CI gates

*繁體中文：[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md). The English version governs if the two differ.*

This layer puts five checks between a branch and `main`: `ci`, `security`, `spec-verify`, `risk-gate` and `agent-review`. The kit holds the workflows (reusable workflows in `.github/workflows/` of the kit). The project holds thin caller workflows, `agentdev-*.yml`, which name one kit version, and one file, `agentdev.toml`, which holds every setting the checks read. The layer gives you mechanical proof that each approved test case maps to a test that ran and passed, that the story's tests fail before the change and pass after it, and that a change to guardrails or high-risk code waits for a human. It does not give you the rules that make those checks required (layer 2), the isolation of the agents that write the code (layer 1) or the program that dispatches the work (layer 4). The checks run without layers 1 and 4. Without layer 2 they only report: nothing makes them required. The design and its reasons are in [guideline.md](guideline.md).

Nothing here has been run against real GitHub yet. Anything marked **To verify** describes behaviour of GitHub itself that the code relies on.

## 1. What this layer protects

| Check | What it verifies | Judged by |
|---|---|---|
| `ci` | Lint (`spec-lint`, `docs-lint`, `codeowners --check`, `pins`, and your `lint_cmd`) and all tests | Program |
| `security` | Secret scanning (gitleaks) and static analysis (semgrep) | Program |
| `spec-verify` | Traceability: every approved test case has a test that ran and passed, and one that has passed may not disappear. Red-green: the story's tests fail on the base branch and pass on the branch | Program |
| `risk-gate` | The risk tier of the change. T2 needs a human's approval of the current commit | Program and human |
| `agent-review` | A different agent's review of the implementation and of how faithful the tests are | Agent |

What the checks defend against:

- A test that passes without testing anything (`assert True`): red-green fails it, because it passes on the base branch too.
- A test case that is claimed but not written, skipped, or only mentioned in a comment: traceability reads the test runner's own report, not the source.
- A test case quietly deleted together with its spec: it is not allowed to disappear unless it is listed in `retired.toml`, which a human approves.
- A pull request that loosens the rules that judge it: `spec-verify` and `risk-gate` take their settings from the base branch, and the kit from the pinned version, never from the pull request.
- A change to guardrails, high-risk paths, dependency manifests or an oversized diff passing on green checks alone: it is T2 and needs a person.

What they do not defend against is in section 6. The most important limit: the test results are produced by the pull request's own code, so an agent could write a fake results file. The weakest check is `agent-review`, because the reviewer reads untrusted text. No hard guarantee rests on it.

## 2. Before you start

- Layer 2 is where the checks become required and where the `conductor` environment lives. Do it first, or the checks below are advisory. Setup of `agent-review` needs that environment: [layer-2-github.md](layer-2-github.md).
- The kit is installed on your Mac and `agentctl` runs ([adopting.md](adopting.md)). `agentctl init` creates the caller workflows and `agentdev.toml` with the kit version filled in.
- The kit repository must be readable without a credential. Each reusable workflow fetches the kit with `curl` from `codeload.github.com` at the pinned commit, with no token. A private kit repository is not supported. (Known limitation.)
- GitHub Actions is enabled for the project. Workflow minutes are billed (section 3.8).
- Your tests can write JUnit XML. If they cannot, choose a runner that can before you go on (section 3.3).
- Story ids are decided: `[stories] id_digits` is 3 by default and sets the shape of every id (`TC-012-03`, branch `story/012-slug`). A project whose existing issue or pull request numbers are large may want 4. Change it before the first story, not after.

## 3. Setup

### 3.1 The caller workflows

`agentctl init` copies these files from `templates/project/.github/workflows/` into the project. Each one calls the kit's workflow of the same purpose.

| Caller file | Job | Check names GitHub reports | Runs on |
|---|---|---|---|
| `agentdev-ci.yml` | `ci` | `ci / ci`, `ci / spec-verify` | pull requests into `main` (opened, synchronize, reopened, ready_for_review), pushes to `main` |
| `agentdev-security.yml` | `security` | `security / security` | the same events |
| `agentdev-risk-gate.yml` | `risk-gate` | `risk-gate / risk-gate` | the same pull request events, and submitted or dismissed reviews |
| `agentdev-agent-review.yml` | `agent-review` | commit status `agent-review` | started by the conductor (`workflow_dispatch`), and submitted reviews (for the bridge, section 3.7) |
| `agentdev-evidence.yml` | `evidence` | none | pull request closed into `main`: posts the AC, TC, test, result table on the story's issue |
| `agentdev-brief.yml` | `brief` | none | daily, plus a weekly digest on Monday: the Director's brief, and the Actions budget estimate |
| `release.yml` | `release` | none | a `v*` tag. A project-owned template, not a kit workflow: fill in its deploy block |

GitHub names a called job `<caller job> / <job>`. That is why the required checks are `ci / ci` and not `ci`. Do not rename the caller jobs (`ci`, `security`, `risk-gate`): the ruleset names them, the release template names them, and the conductor strips the caller part when it reads checks. The status `agent-review` is a commit status, so it has no prefix.

`spec-verify` reads the earlier runs of `agentdev-ci.yml` on `main` to find test cases that must not disappear. If you rename that file, the history stops matching and `spec-verify` warns that there is nothing to compare against.

The callers have two fixed facts:

- `agentdev-brief.yml` and the `agent-review` job of `agentdev-agent-review.yml` (the review the conductor dispatches) use `secrets: inherit`. They need secrets of the `conductor` environment, which a called job reaches because it declares `environment: conductor`. The `review-bot` job of the same caller, which runs on submitted reviews, passes no secrets: for that event GitHub runs the pull request's copy of the file. Keep model tokens in the `conductor` environment, never as repository secrets. (**To verify**: environment secrets in a called job.)
- Every caller names the kit twice, as `uses: januswtlin/agent-dev-kit/.github/workflows/x.yml@<sha>` and `kit_version: <sha>`. Both must equal `[kit] version` in `agentdev.toml`.

Check the pins at any time:

```bash
agentctl pins
```

It fails when a caller names another SHA, names it once, or `[kit] version` is not a full 40-character SHA. It also runs in the `ci` lint step, so a pull request that edits one SHA and not the others fails.

If the project already has workflows with the same file names, `agentctl init` keeps them and lists them. Merge by hand and keep the job names above.

### 3.2 Required checks and the first green run

The five required checks are in their own ruleset, `main-checks`, which is the layer-3 half of the rulesets. Layer 2 applies `main`, `main-merge` and `tags` with `agentctl rulesets 2`; layer 3 applies `main-checks`, as an admin, from inside the project:

```bash
agentctl rulesets 3
```

Order matters on a new repository: apply it only after the caller workflows are on the default branch and have run once, and `ci` has been green on `main`. A check that has never reported cannot be required in a way that lets anything merge. After the ruleset is on, a pull request needs all five. Confirm with `gh api repos/OWNER/REPO/rulesets --jq '.[].name'`: it should now list `main-checks` as well.

The first `ci` run on `main` creates the baseline that `spec-verify` compares against later. Until a run on `main` has uploaded results, `spec-verify` only warns "no ci run on main has results; nothing to compare against". Results expire after 90 days; the comparison uses up to the five newest runs on `main` that still have results.

### 3.3 `[tests]` for your stack

The workflows do not call `make`. They read `agentdev.toml`:

```toml
[tests]
setup_cmd = ""
lint_cmd = "make lint"
test_cmd = "make test"
junit_glob = "reports/junit/*.xml"
test_paths = ["tests/**", "**/tests/**", "**/__tests__/**", "**/*_test.*", "**/*.test.*", "**/*.spec.*", "**/test_*.py"]
```

| Key | Meaning |
|---|---|
| `setup_cmd` | Installs dependencies. Runs before the tests, also in a clean checkout of the base branch for red-green. If it fails there, red-green fails: a test that cannot run shows nothing |
| `lint_cmd` | Static checks. Run by `ci` after the kit's own lint, and by agents before they push |
| `test_cmd` | Must run every test, write JUnit XML where `junit_glob` finds it, and exit non-zero when a test fails. Run with `bash -c` |
| `junit_glob` | Where the JUnit files are. `agentctl collect-junit` copies what it finds into one directory, so any layout works. A symbolic link is skipped |
| `test_paths` | Files that red-green copies onto the base branch besides any file that mentions the story's TC ids |

A change to `agentdev.toml` is T2 (always a guardrail). Other settings are in `tools/agentctl/defaults.toml` of the kit. Print the effective value of any of them:

```bash
agentctl config tests.test_cmd
```

Starting points for the JUnit output (the shipped `Makefile` lists them too):

| Stack | `test_cmd` |
|---|---|
| Python, standard library (the shipped default) | `agentctl junit-unittest tests reports/junit/unittest.xml` |
| pytest | `pytest --junitxml=reports/junit/python.xml` |
| vitest | `vitest run --reporter=junit --outputFile=reports/junit/web.xml` |
| Node's test runner | `node --test --test-reporter=junit --test-reporter-destination=reports/junit/node.xml` |
| Go | `gotestsum --junitfile reports/junit/go.xml ./...` |

Two rules that bite:

- The tests must run on a clean GitHub-hosted runner with Python 3.12 present and only `setup_cmd` run before them. Put everything your tests need into `setup_cmd`.
- Red-green runs the story's tests on the base branch, where the feature does not exist yet. The tests must fail by reporting a failure or an error in their own report. A test that does not run at all (the runner exits before reporting) is only accepted as red when the report contains a failure or error that belongs to one of the story's test files (matched by the file's name without its extension). If your runner reports nothing when a test file cannot be imported, test that case on a toy story before you rely on it.

For a project that has an existing test suite, keep the test names. Traceability only needs the TC id somewhere in the test's name, class name or file name. Which forms count is in section 3.4.

### 3.4 Traceability: TC ids and test names

An approved story has a `spec.toml` with acceptance criteria (`AC-012-1`) and test cases (`TC-012-03`). A test carries its TC id in its name, its class name or its file name. Many languages forbid `-` in identifiers, so all of these count for story 012, case 03: `TC-012-03`, `tc_012_03`, `TC01203`, `TC 012 03`. The pattern is case-insensitive and follows `[stories] id_digits`.

Examples:

```python
def test_tc_012_03_after_passing_the_order_is_paid(self): ...
```

```js
test("TC-012-03 after passing, the order is paid", () => { ... });
```

What counts as a pass:

- The report from the runner says the test ran and passed. A skipped test, a missing test, and a TC id only in a comment do not count.
- In the shipped unittest runner, a test marked `expectedFailure` whose assertion fails is reported as skipped, so it never counts as a passing test case.
- A TC that passed on `main` (in any of the newest five runs that have results) must still pass. The only way to drop one is to list it in `retired.toml` under the specs directory (`retired = ["TC-012-03"]`). That file is protected by CODEOWNERS and by `human_gated`.

Stories come in two language files (`story.md` English and `story-<lang>.md`, where `<lang>` is `[stories] translation`, default `zh-TW`). `spec-lint` checks that the two have the same AC and TC ids in the same order and the same sections, and that they changed together in the pull request. Set `translation = ""` for English only. `max_lines` (default 80) limits each story file.

Documents are checked the same way when `[docs] translation` is set: every `<name>.md` needs `<name>-<lang>.md` with the same headings, and the files in `[docs] required` must exist. It is off by default.

### 3.5 Risk tiers

`risk-gate` computes one tier from the changed paths, read with `git diff -z`, using `agentdev.toml` as it is on the base branch.

| Tier | When | What it needs |
|---|---|---|
| T0 | Every changed file matches `[risk.t0] paths` (default `docs/**`, `**/*.md`, `LICENSE`) | Green checks |
| T1 | A code change on a story branch (`story/NNN-slug`) that triggers none of the T2 reasons | Green checks and `agent-review` |
| T2 | Any file in `[risk.t2]` `guardrails`, `human_gated`, `high_risk` or `dependency_manifests`; a diff over `[risk.thresholds]`; or a code change on a branch that belongs to no story | A person in `[roles] humans` approves the current commit |

Test files are not T0: weakening a test is a behaviour change. `.github/**` and `agentdev.toml` are always guardrails, whatever the project writes, and T2 can never be listed in the conductor's `auto_merge_tiers`.

Set `high_risk` to the project's real layout. The default list (`**/auth/**`, `**/payments/**`, `**/billing/**`, `**/migrations/**`, `infra/**`, `**/*.tf`, `**/Dockerfile`, `**/docker-compose*.yml`) is only a start. A list in `agentdev.toml` replaces the default as a whole, so copy the entries you want to keep. The same is true of `dependency_manifests`: extend it for your own stack, with lock files and registry configuration included.

```toml
[risk.t2]
high_risk = [
  "**/auth/**",
  "**/payments/**",
  "**/migrations/**",
  "infra/**",
  "**/Dockerfile",
  "app/security/**",
]
```

`risk-gate` publishes the tier twice: the label `tier:T0`, `tier:T1` or `tier:T2` on the pull request, for people, and the commit status `risk-tier/T0`, `risk-tier/T1` or `risk-tier/T2` on the head commit, with the description "pull request #N into BRANCH". The conductor reads the status, because an agent's token can edit labels but cannot write a commit status, and it believes a tier only when the description says it was computed for that pull request into the default branch. A commit with no such status counts as T2; with several, the strictest wins.

Outside story branches `risk-gate` sets `agent-review` to success with the description "not a story branch; no agent review required", so the required status is satisfied there. Documentation (T0) needs no agent review and any other non-story change is T2, reviewed by a person.

`risk-gate` fails, and does not skip, for a pull request whose base is not the default branch. A skipped job counts as passed for a required check, and that result would stay on the commit if the pull request were retargeted.

Draft pull requests: `ci` runs lint only, `risk-gate` runs, and `security` and `spec-verify` are skipped. GitHub shows the skipped checks as passed. That is acceptable only because a draft cannot be merged and because marking it ready (`ready_for_review`) starts a full run on the same commit. Layer 2's checklist covers the ready-for-review step.

### 3.6 Test the gates on a toy story

Before real stories, run the gates once with a small story: one AC, two TCs, a failing test first, then the implementation. The full loop with the conductor is the spike in [layer-4-conductor.md](layer-4-conductor.md). To exercise only this layer, push a branch `story/NNN-slug` for a story whose spec is on `main`, open the pull request yourself and mark it ready. Open it as a draft first, to see lint-only on a draft.

Expected: the first push of the test file alone makes `spec-verify` pass the red part (its tests fail on the base branch) and fail traceability (the tests fail on the branch too). After the implementation, all of `ci / ci`, `ci / spec-verify` and `security / security` are green, and `risk-gate / risk-gate` is green for T0 or T1 and red for T2 until a listed person approves.

### 3.7 `agent-review`

The required status `agent-review` is set by one of two sources.

**Claude, as a workflow.** The conductor dispatches `agentdev-agent-review.yml` for one commit of a story's pull request (inputs `pr`, `story`, `developer`, `sha`). The `claude` job:

- runs only from the default branch and uses the `conductor` environment, whose deployment rule allows only the default branch, so a branch cannot run it or read its secret;
- checks that the pull request is open, comes from this repository and targets the default branch, and that its head is the commit the conductor asked about. If the branch moved, nothing is reviewed and nothing is published. The next conductor pass asks again for the new commit;
- checks out the default branch as the reviewer's own working directory and the pull request beside it, in `./pr`, as data, so the pull request cannot supply Claude Code's settings or hooks;
- reads its instructions from the kit's `review` prompt at the pinned version, filled in from `agentdev.toml`;
- runs with a read-only token and `--tools "Read,Grep,Glob,Write,Bash"`, with only three read-only `git -C pr` commands pre-approved for Bash, and writes its verdict under the runner's temp directory.

A separate `publish` job, which never sees the pull request's files, posts the findings as a comment and sets the status. The verdict counts only if the review step itself succeeded. A review that did not finish is published as failure, never left pending or passed.

Setup:

1. The `conductor` environment exists with its branch rule ([layer-2-github.md](layer-2-github.md)).
2. Create the review token. On a Mac where Claude Code is signed in, generate a long-lived OAuth token (`claude setup-token`) and store it as the environment secret `CLAUDE_CODE_OAUTH_TOKEN` of the `conductor` environment:

```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN --env conductor
```

3. For a story the sprint file gives to a named developer, store that person's token under the suffixed name instead: `CLAUDE_CODE_OAUTH_TOKEN_<LOGIN>`, the login in upper case with every other character as `_` (`CLAUDE_CODE_OAUTH_TOKEN_ALICE`). The plain name is used only for stories of `default`. It is never a fallback for a named developer.

The conductor running on your Mac cannot see GitHub's secrets, so it cannot check that the token exists before it dispatches. With a missing token the workflow starts, the review step fails, and `publish` sets `agent-review` to failure on that commit. Look at the run if a review fails at once.

The inputs of `anthropics/claude-code-action` and the effect of `--tools` and `--allowedTools` are to be verified in the spike. (**To verify**.)

**A review bot, bridged.** A review posted by another agent (for example the Codex cloud GitHub integration, or a review from a local sandbox) is turned into the status by the `bridge` job, on a submitted pull request review (called from the caller's `review-bot` job, without secrets). It only listens to the logins in the repository variable `REVIEW_BOTS`, a JSON array:

```bash
gh variable set REVIEW_BOTS --body '["chatgpt-codex-connector[bot]"]'
```

The status is success when the review's state is `approved` or its body contains `agent-review: pass` (any case), and failure otherwise. The status is written on the commit the review was submitted for.

If a review stage runs in a local sandbox (`via = "sbx"` in `[roles.harness.<name>]` and no `review_workflow`), the sandbox's token cannot write the status, so the review is posted as a pull request review by the developer's agent App. Add that App's login (`NAME-agent[bot]` or whatever your App's slug gives) to `REVIEW_BOTS`, or the review is ignored. Note the login you actually see on the review. The login of the Codex integration is a guess until the spike. (**To verify**.)

If the review is done in an ordinary cloud session, the reviewer and the implementer may be the same GitHub identity and cannot be told apart. The prompt tells the reviewer which commit to review and to stop if the head differs. That is an instruction to an agent, not an enforcement.

Which reviewers run for which stage, and in what order, is set in `[roles.developers.<login>.stages]`; see [layer-4-conductor.md](layer-4-conductor.md). A one-person, one-vendor project gets a fresh session of the same harness as reviewer. The mechanical checks carry the main guarantee in that case.

### 3.8 Actions minutes and budget

GitHub bills Actions in money ($18 a month of allowance on the Team plan at the time of writing; check GitHub's pages), and rounds each job up to a whole minute. The design keeps usage down:

- The test suite runs once on the head, plus once on the base for a story branch, in the same job.
- A draft only runs lint. About three full gate runs per story rather than one per push.
- `spec-verify`, `risk-gate`, `evidence`, `brief` and the `agent-review` publish job do not run the pull request's code and can use a smaller runner: set the repository variable `LIGHT_RUNNER` to its label. If it is unset they use `ubuntu-latest`.
- The conductor runs on your Mac, so it uses no minutes.

The daily brief runs `agentctl budget`, which estimates the month's usage from the job records, keeps it in the repository variable `ACTIONS_USAGE`, and prints one line that the brief shows. You can run it yourself:

```bash
agentctl budget --dry-run
```

The estimate may differ from the bill. GitHub's billing page is the source of truth.

Overflow is off. `[conductor.actions] overflow_runner` is empty on purpose: `ci` and `security` execute the pull request's code, so an overflow runner would have to be dedicated, hold no credentials and be recreated for every job. A developer's Mac and any VM an agent works in are not. When the allowance is used up, CI stops and nothing merges until the next month or until you pay for more. (**To verify**: what GitHub does at that point.) If you do configure a suitable runner, usage above `overflow_at` (0.85 of the allowance) points the repository variable `CI_RUNNER` at it and a new month changes it back. Only `ci` and `security` follow `CI_RUNNER`. The jobs that judge always stay on GitHub-hosted runners.

The figures for minutes per story in the guideline are estimates. In the spike, record the real ones: minutes for one run of your tests, full gate runs per story, minutes shown on GitHub's Actions usage page for the story.

### 3.9 Upgrading the pinned SHA

One pull request changes every place that names the kit:

1. On the Mac, install the new version by its full commit SHA, from a clone of the kit at that commit:

```bash
./install.sh NEW_SHA
```

2. On a `chore/` branch, replace the old SHA with the new one in `[kit] version` of `agentdev.toml` and in every `agentdev-*.yml` (twice per file: `uses:` and `kit_version:`).
3. Run `agentctl pins`. Run it with the new version, not the old one: until the pin is on `main`, set `AGENTDEV_KIT_VERSION` to the new SHA.

```bash
AGENTDEV_KIT_VERSION=NEW_SHA agentctl pins
```

4. Open the pull request. It touches `.github/**` and `agentdev.toml`, so it is T2: a person approves it, and CODEOWNERS makes that approval required. Read the limit in section 6: for a pull request that edits the callers, the workflow files that run are the pull request's own, so its check results say little. The person's approval is what protects you.
5. After the merge, run `./install.sh NEW_SHA` on every other Mac that works on the project. The launcher reads the pin from the default branch, so a Mac that has not installed the new version stops with "kit NEW_SHA is not installed" and the command to run.

Read the kit's changes between the two SHAs before you approve. A new kit version changes what judges your pull requests.

## 4. Checklist

Run it once when the setup is complete, and again after you change a workflow, `agentdev.toml` or the kit version. **Most items attempt something that must fail.** If such an attempt succeeds, a line of defence is not working. A few items check that the normal path works and expect success: D1 and D16 (the latter in [layer-4-conductor.md](layer-4-conductor.md)). D21 expects success in part. The "Expected" column says which.

Note the message you actually saw in the "Result" column. None of these items has been run against real GitHub, so a result that differs may also mean this checklist is wrong. Write that back too. Item ids are shared with the other layer documents and never reused. D9, D10 and D23 are in [layer-2-github.md](layer-2-github.md); D16, D20 and D22 are in [layer-4-conductor.md](layer-4-conductor.md).

Unless an item says otherwise, the test pull request targets `main`.

| # | Attempt | Expected | Result |
|---|---|---|---|
| D1 | A PR that changes only `docs/guideline.md`. Open it yourself, from a branch whose name does not start with `story/`, `spec/`, `sprint/` or `chore/` | Labelled T0, checks green, and `agent-review` set to success with "not a story branch". Nothing merges it automatically. This one should SUCCEED. Repeat once from a `chore/` branch, with the conductor opening the pull request: the result is the same, and the conductor never merges it | |
| D2 | Change `agentdev.toml` and empty `[risk.t2] high_risk` | Labelled T2 (`agentdev.toml` is a guardrail); cannot be merged without a person's approval. And this PR's tier is computed with the settings on `main` | |
| D3 | Change code on a branch that is not a story branch | T2, the reason being that there is no corresponding story | |
| D4 | Add a dependency | T2, the reason `dependency_manifests` | |
| D5 | On a story branch, add an `assert True` test carrying a TC id | `spec-verify` fails, with a message pointing out that the TC already passes on base | |
| D6 | On a story branch, leave out one TC | `spec-verify` fails and says which one is missing | |
| D7 | Mark the test for a TC as skip | `spec-verify` fails. A test that is skipped only on base is not accepted as red either | |
| D8 | Modify an approved `spec.toml` and delete one TC that passes on `main`, together with its test | Needs a person's approval to merge (`human_gated`). And `spec-verify` fails, saying the TC passed on base but is missing now. The only way to drop it is to list it in `retired.toml`, which also needs approval | |
| D11 | Change only `story.md` and not the translated story file (or the other way round) | `ci` fails | |
| D12 | Put an AC with a different meaning in each of the two story files (for example 10 MB in one and 5 MB in the other) | The review agent points out the difference and treats it as blocking. This item is a soft control; note whether it was really caught | |
| D13 | While the story's PR is still a draft | `ci` runs lint only, `risk-gate` runs, and `security` and `spec-verify` are skipped. GitHub shows the skipped checks as passed; the PR still cannot be merged, because it is a draft (D23 in [layer-2-github.md](layer-2-github.md)) | |
| D14 | Open a PR whose base is a branch other than `main` (for example from `story/000-example` into a branch `test/base`) | No `ci`, `security`, `spec-verify` or `risk-gate` check appears on it, and no `tier:` label. A status earned against another base must not exist. If a review is submitted on it, `risk-gate` does appear, and it is red (D19) | |
| D15 | A PR that changes only a lock file (for example `package-lock.json` or `uv.lock`). Repeat with a lock file the configuration does not name, such as `composer.lock` | Labelled T2, with the reason `dependency_manifests`; cannot be merged without a person's approval | |
| D17 | Make a Claude review fail on purpose: set the `conductor` environment secret `CLAUDE_CODE_OAUTH_TOKEN` to an invalid value, then run `gh workflow run agentdev-agent-review.yml -f pr=N -f story=NNN` for an open story PR. If you store that secret with a `_LOGIN` suffix, change that one and add `-f developer=LOGIN_IN_UPPER_CASE`. Restore the secret afterwards | The `agent-review` status on the PR's head commit is failure ("review requested changes or did not finish"). It is never success and is not left pending | |
| D18 | Hostile result artifact. On a test story branch, make the test step leave a symbolic link inside `reports/`: for example a test file that runs `os.symlink("/etc/hostname", "reports/junit/link.xml")` when it is imported. Mark the PR ready, so that the full gates run. Repeat once with `reports` itself replaced by a link to another directory | `spec-verify` fails at the step "Keep only plain result files", saying that the directory contains a symbolic link. Nothing under the base checkout (`base/`) is changed. If the link does not survive the upload and arrives as a plain file, the step does not fail: note what arrived (**To verify**: how artifact upload and download treat links) | |
| D19 | Retargeting. Create a branch `test/base` from `main`. Open a PR from a story branch into `test/base` and submit a review on it. Then change the PR's base to `main` without pushing anything. Afterwards push a commit | After the review: `risk-gate` on that commit is red, with "this pull request targets test/base, not main". It is failed, not skipped. After retargeting, without a push: the PR is blocked and nothing is credited. `risk-gate` is still red, and `ci`, `security` and `spec-verify` have no result, because those workflows do not run on a change of base. After the push: every required check runs against `main`. Record what actually happens at each of the three points (**To verify**) | |
| D21 | Review and a moving head. While the `claude` job of a dispatched `agentdev-agent-review.yml` run is still queued, push a new commit to the story branch. To get the same situation by hand: `gh workflow run agentdev-agent-review.yml -f pr=N -f story=NNN -f sha=PREVIOUS_HEAD_SHA`, with `-f developer=LOGIN_IN_UPPER_CASE` if the story names a developer | The `claude` job stops at "Resolve the pull request" with "the branch moved since this review was asked for". The `publish` job is skipped: no findings comment, and no `agent-review` status on either commit. With the conductor running, its next pass asks for a review of the new head, and that review is published. This last part should SUCCEED. A duplicate review of the same head is possible; note it if you see one | |
| D24 | Run the review from a branch. `gh workflow run agentdev-agent-review.yml --ref SOME_BRANCH -f pr=N -f story=NNN`. (The workflow file must exist on that branch; use a branch made from `main`.) | The `claude` job is skipped (it runs only from the default branch), or the `conductor` environment refuses it its secrets. No review runs and no status is written. If the job gets as far as the review step with a token, the environment's branch rule is not working | |
| D25 | Pin check. On a branch, change the SHA in one `uses:` line of one `agentdev-*.yml` and nothing else | `ci` fails at lint, with a message from `agentctl pins` that names the file and both SHAs. Repeat with `kit_version:` changed and `uses:` left, and with `[kit] version` changed alone | |
| D26 | Bridge. Submit a review on a story PR as an account that is not in `REVIEW_BOTS`, then as one that is, once approving and once requesting changes | Not listed: no `agent-review` status is written. Listed and approved: `agent-review` success on the reviewed commit, "review bot approved". Listed and changes requested: failure. This part should SUCCEED. Note the login you actually saw | |
| D27 | Settings come from the base. On a story branch, edit `[tests] test_cmd` in `agentdev.toml` so that it runs nothing, and `[risk.t2]` so that `high_risk` is empty | The PR is T2 because it touches `agentdev.toml`. `spec-verify` and `risk-gate` use the settings on `main`: no risk reason disappears. `ci` itself runs the changed `test_cmd` (it runs the PR's code anyway), and red-green and traceability still fail because no test reports | |
| D28 | A hostile file in the pull request's tree. On a story branch, add a file named `json.py` (and one named `agentctl.py`) at the repository root, and a `tomllib.py` | `risk-gate` and `spec-verify` behave as without them: the judging steps start Python with `-I`, so the tree cannot supply a module. Nothing from the file runs in those jobs | |

## 5. Not yet verified

Nothing in this layer has run against real GitHub. These are the points where the code relies on GitHub's behaviour, or on a vendor's, and where a surprise is most likely:

- The check names GitHub reports for a called workflow (`ci / ci`, `ci / spec-verify`, `security / security`, `risk-gate / risk-gate`) and that the ruleset can require them with the Actions app as the source. Layer 2 holds the ruleset; the names here must match it exactly.
- Environment secrets in a called job: that `secrets: inherit` in a caller passes the `conductor` environment's secrets to a job that declares `environment: conductor`.
- That a `pull_request_review` event started from a bot account carries the review's `commit_id` and state as the bridge expects, and the login and review format of the Codex review bot.
- The inputs of `anthropics/claude-code-action`, that `--tools` limits the tools that exist for the session, and that `--allowedTools` only pre-approves calls.
- How `actions/download-artifact` and `upload-artifact` treat a hostile archive and symbolic links (D18).
- That the commit statuses `risk-tier/*` and `agent-review` appear in the pull request's check rollup, which is where the conductor reads them, and that statuses written with the workflow token are accepted as coming from the Actions app.
- What happens to a pull request retargeted without a push (D19), and to a draft marked ready without a push.
- A fetch of the kit from `codeload.github.com` by SHA from a runner, and that the pinned tarball is the same bytes every time.
- Whether the checks stay inside the Actions allowance at your project's size, and what GitHub does when it runs out.
- Red-green on your own stack: how your test runner reports a test file that cannot be imported on the base branch.
- The semgrep configuration `--config auto` needs network access to semgrep's rule registry from the runner, and the gitleaks download needs GitHub's release host. Neither has been run.

## 6. Known limitations

- **The results can be fabricated.** The JUnit files are produced by a job that ran the pull request's code, so an agent can write a fake report. `spec-verify` treats the files as untrusted input (plain `*.xml` and `collected.json` only, a symbolic link fails the job, unpacked outside both checkouts), which protects the judge, not the content. The defence is the protected build configuration (`agentdev.toml`, workflows), the review's audit of each test case, and a periodic spot check.
- **Red-green shows that a test fails on the base, not why.** A test written to behave differently on the base and on the branch (for example, by checking whether a file exists) can satisfy it. Only the review's audit of each test can catch that.
- **The list of test cases may be incomplete.** The checks prove that every approved TC has a running test. They do not prove that the list is complete. That depends on the product-owner stage's questions and on your reading when you approve the story.
- **`agent-review` is the weakest check.** The reviewer reads untrusted text (the diff, commit messages, files) that can talk it into a wrong verdict. Isolation limits what a misled reviewer can do, not what it concludes. No hard guarantee depends on it.
- **A review bridged from a bot or a sandbox is only as good as the login list.** Anyone whose login is in `REVIEW_BOTS` can set the status to success.
- **The baseline is only as good as the runs on `main`.** `spec-verify` compares against the newest five runs on `main` whose results can be read, whatever those runs concluded. Partial runs on `main` still shrink what is remembered, and a test case that was never in a readable run cannot be protected.
- **A pull request that edits a caller workflow chooses the workflow that judges it.** For `pull_request` events GitHub runs the workflow files of the pull request. A change to `uses:` or `kit_version:` therefore decides which kit version (or repository) produces that pull request's own check results. The settings still come from the base branch, but the code does not. The defences are that `.github/**` is a guardrail owned by a person in CODEOWNERS, so the ruleset requires a human approval whatever the checks say, and that you read the diff of every such pull request. Treat green checks on a pull request that changes `.github/**` as uninformative. A mitigation to evaluate is the ruleset rule that requires workflows to pass: it runs a workflow from a fixed repository and ref instead of the pull request's copy (not verified on the Team plan).
- **The kit repository must be public or otherwise readable without a token**, because the workflows fetch it by `curl`.
- **A required skipped check counts as passed.** The design relies on drafts being unmergeable and on `ready_for_review` starting a full run. If either does not hold on real GitHub, a draft could merge on skipped results.
- **Overflow is off**, so when Actions minutes run out, CI stops and nothing merges.
- **Estimates of minutes and cost are not measured.** `agentctl budget` may differ from the bill.
- **Dependencies are routed to a person, not scanned.** A new or changed dependency is always T2. No check looks at whether the package is safe.
- **Scanner configuration comes from the tree.** `.gitleaks.toml`, `.semgrepignore` and similar files are read from the pull request's checkout, so they are guardrails (T2). A change that weakens them waits for a person.
