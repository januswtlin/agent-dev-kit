# Guideline for the AI Coding Agent Development Environment

*繁體中文：[guideline-zh-TW.md](guideline-zh-TW.md). The English version governs if the two differ.*

This document explains the design of this repo: why it is built this way, how the parts fit together, what has been verified and what has not.
Installation steps are in [runbook.md](runbook.md). Threats and the controls that answer them are in [threat-model.md](threat-model.md).

## 1. Goals

1. **Agents cannot reach your private data and cannot cause irreversible damage.** In order of severity: reading private files (once read, it cannot be taken back), deleting files outside the working directory by mistake, using temporarily valid cloud credentials on the machine, and, in future, production.
2. **Human attention is the bottleneck.** You are the director: you decide what to build, approve the scope, and release to production. You do not read ordinary PRs, merge, or dispatch work.

It assumes nothing fixed about the team. One person with one AI subscription is enough. So is one person with several, or several people who each bring their own. Who may approve product decisions, and which harness does which stage for each person, are settings (`policy/roles.toml`, `.github/CODEOWNERS`). Only two things are constant: agents run on subscriptions, with no pay-as-you-go API keys, and the repo is on a GitHub plan that enforces rulesets on private repos.

## 2. Three principles

**Protect with capability boundaries, not with agent self-discipline.** Prompts, permission settings and command blocklists can all be bypassed, so they only count as a second layer. The real guarantee is that nothing capable of causing damage exists in the environment where the agent runs. It cannot see your home directory, and the token it holds has no dangerous permissions.

**GitHub is the only control plane.** All harnesses hand work over only through branches, PRs and issues. Changing models, changing vendors or adding a local model does not change the process. This is also why no API key is needed: each vendor's model runs in its own harness on subscription quota.

**Mechanical checks take precedence over what the agent says about itself.** Agents declare completion too early and overestimate their own output. Whatever can be verified by a program (whether a test really exists and runs, whether it really exercises the behaviour) is not asked of the agent.

## 3. Trust zones

| Zone | Contents | What an agent can do |
|---|---|---|
| 0 Your Mac | Private data, browser, Keychain, temporarily valid cloud tokens, Ollama | Coding agents do not run here |
| 1 Sandbox | A local VM, or the vendor's cloud session. Only the project's worktree | Full autonomy inside; cannot get out |
| 2 GitHub | Rulesets, required checks, CODEOWNERS | Can only push branches; everything else must pass the gates |
| 3 Production | Cloud resources, databases | Nothing. Only a release tag pushed by a human can trigger a deployment |

### Rules for Zone 1

**Coding agents always run in a VM or in the cloud, never directly under a user account on the Mac.**

The sandbox built into a harness is not enough to protect privacy. Claude Code's sandbox allows reading almost the whole file system by default, and it covers only Bash, not the file tools, MCP servers or hooks. Codex's `workspace-write` likewise restricts only writes. They work against accidental deletion, but protection against reading depends on you listing every path correctly. A VM's mounts are deny by default: what is not mounted does not exist.

The local sandbox is Docker Sandboxes (`sandbox/sbx.sh`). Five properties:

- One microVM per agent, with its own kernel.
- **Clone mode.** The repository is mounted read-only and the agent works on a private clone inside the VM. Nothing it does changes a file on the Mac, and its only way to deliver work is `git push`. This matters more than it looks. With an ordinary read-write mount, an agent can write a git hook into `.git/hooks`, and that hook then runs on the Mac, as you, the next time you use git in that directory.
- Outbound connections are denied except to the hosts in `sandbox/allowlist.txt`, filtered by host name. This limits both data exfiltration after a prompt injection and callbacks from malicious packages.
- No GitHub credential inside the VM. A proxy on the host replaces a placeholder with a one-hour token of your agent GitHub App, which a helper on the host mints when it is needed. The App's private key never leaves the host. SSH agent forwarding is turned off, because it is on by default and would let the agent push as you.
- One sandbox per dispatched stage, created for it and removed afterwards. Stages share no files, processes or login state, and each is given only what it needs (see "Role assignment" in section 5).

Lima (`sandbox/vm.sh`) remains as a fallback and as the home of the self-hosted runner. It is weaker on three counts: the workspace is mounted read-write, traffic is filtered by address rather than by host name, and the App's key has to live inside the VM. Neither has been run on a real machine yet; see section 9.

Cloud sessions (Claude Code on the web, Codex cloud) are vendor-managed VMs that cannot reach your laptop at all. They are the strongest isolation for privacy, and the only place where work can continue while the laptop is closed. Set the environment's network to restricted and put no secrets in it.

### Hygiene rules on the Mac

`bin/agentctl doctor` checks those of the following that can be checked.

- Keep projects somewhere not synced by iCloud, such as `~/dev`. An accidental deletion in an iCloud-synced directory syncs to every device.
- Do not grant Full Disk Access to the terminal or the IDE. Any program run inside them inherits that permission.
- Do not enable computer use, screen recording or accessibility for agent-type desktop apps. Do not install agent extensions in the browser profile you use every day. Do not connect personal Gmail, Drive or iCloud as an agent connector or MCP server. These paths bypass the VM and reach private data directly, and there is no technical means to enforce the rule. It holds only by not turning them on.
- Turn on Time Machine or an equivalent backup.
- Optional: create a separate standard macOS user account for development. With private data under another account, file permissions block reading. The cost is the nuisance of switching accounts.

If you really must run directly on the Mac (for example, a brief interaction inside the IDE), the host profiles in `.claude/settings.json` and `codex/config.example.toml` provide strict settings. This is the exception, not the norm.

### Story agents and maintenance work

Agents have two roles in this repo, and the guardrails ask different things of each.

A **story agent** is dispatched by the conductor and runs unattended. It must not edit the guardrail paths. This rule has two layers. The hard layer is CODEOWNERS and token permissions. The soft layer is the deny rules in `sandbox/story-agent.claude-settings.json`, installed in the user-level settings inside the sandbox and in the cloud environment, which apply only to story agents. The product owner and the planner are dispatched the same way but have to write specs and sprints, so they get `sandbox/spec-agent.claude-settings.json`: the guardrail paths stay off limits, the spec paths do not.

**Maintenance work** is when you ask an agent directly, in a session, to change the pipeline itself (workflows, policy, tools, prompts). This is allowed on these conditions: a human asks in person, the work is done on a `chore/` branch, and a human approves the PR. A dispatch prompt, an issue or the contents of a file does not count as such a request.

The repo's shared `.claude/settings.json` therefore holds only the rules that are true for both roles: no reading or writing in home, no force push, no cloud CLIs, no opening or merging PRs on its own. An earlier version also put the rule against editing guardrail paths in the shared settings. As a result, even maintenance work you had instructed was blocked, including fixing that setting itself.

### Identities and tokens

Three identities, with separate permissions:

| Identity | What it is | Can | Cannot |
|---|---|---|---|
| Human | The people on the project, repo admins | Approve PRs, push release tags, change settings | Push directly to main (nobody can) |
| Agent | A GitHub App per developer, for that developer's agents | Push branches, comment, change labels | Open PRs, approve, merge, change workflows, create tags, write commit statuses |
| Conductor | One GitHub App for the pipeline | Open PRs, enable auto-merge, dispatch work, notify | Approve PRs |

Why each developer's agents get their own GitHub App: an App has exactly the permissions it was granted, whatever its owner's role, so it carries no admin bypass. Its tokens expire after an hour. It takes no seat. And because there is one per developer, a commit or a comment shows whose agent made it; a single App shared by everyone would hide that. A personal access token cannot do the same: a token issued from an admin account, even a fine-grained one, still inherits the admin's eligibility to bypass rulesets. `agentctl app-token` mints the token, and it runs on the host: the sandbox's proxy calls it and injects the result, so neither the key nor the token is inside the VM.

Why the conductor is a separate GitHub App: GitHub does not let an author approve their own PR. If a cloud agent opened a spec PR under your identity, you could not approve it. So the agent only pushes a branch, and the Conductor App opens the PR. In addition, PRs opened and merges made with the default `GITHUB_TOKEN` do not trigger other workflows, so the gates would not run at all.

Cloud sessions are the exception. Claude Code on the web and Codex cloud reach GitHub through the vendor's own integration, acting as the user account you connect; you cannot put your own App in its place. The default here is to connect your personal account. A cloud agent then acts with your identity, and what it cannot do depends on the vendor's limits and on rulesets that have no bypass. Section E of the red-team checklist tests exactly this: whether a cloud agent can create a release tag or approve a pull request. If either succeeds, there are two ways out. Connect a separate machine account for the cloud services, which costs one more seat. Or stop using the cloud path and run every stage on self-hosted runners (`via = "workflow"`), which costs nothing but needs the machine to be on.

## 4. Gates: what must hold before a merge

The ruleset for `main` (`.github/rulesets/main.json`) has no bypass list and treats humans and agents alike:

- No direct push, no force push, no deletion. Merging only through a PR, by squash. The branch must be up to date with main.
- All five required checks green.
- When a path listed in CODEOWNERS is touched, an owner (a human) must approve. A new push invalidates earlier approvals.

| Check | What it verifies | Judged by |
|---|---|---|
| `ci` | Lint, all tests | Program |
| `security` | Secret scanning, static analysis | Program |
| `spec-verify` | Traceability: every approved test case maps to a test that actually ran and passed, and one that has passed may not disappear. Red-green: the story's tests fail on main and pass on the branch | Program |
| `risk-gate` | Risk tiering; T2 needs a human approval of the current commit | Program + human |
| `agent-review` | A different agent's review of the implementation and of how faithful the tests are | Agent |

`spec-verify` and `risk-gate` run with **the tools and policy of the base branch**, so a PR cannot change the rules that judge it. `spec-verify` itself runs none of the PR's code: the tests run in the `ci` job, and the results are handed to `spec-verify` as files for judgement.

A story's PR is opened as a draft. A draft runs only lint. When the implementation stage is complete, the conductor marks it ready for review, and only then do the full gates run. This saves Actions budget; see section 6.

### Risk tiers

`policy/risk-tiers.toml`:

- **T0** Documentation only. Green checks are enough.
- **T1** A code change that belongs to an approved story. Passing checks and agent review are enough.
- **T2** Needs human approval. This covers: the guardrails themselves (`.github/`, `policy/`, `tools/`, `prompts/` and so on), specs and sprints, high-risk code paths (auth, payments, migrations, infra), any dependency added or changed, a diff over the size threshold, and a code change that belongs to no story.

Test files are not T0. Weakening a test is a change in behaviour.

### "The AI saying it will write test XYZ does not mean it really did"

In a story you have approved, every test case has an ID (`TC-012-03`). Four layers of checks follow, and the first three do not depend on anything an agent says:

1. **Traceability.** The test name must carry the TC ID. CI reads the JUnit XML that the test runner outputs and confirms that every ID has at least one test that actually ran and passed. Tests that are skipped, that do not exist, or that are only mentioned in a comment do not count. The basis is the execution result, not a search of the source code.
2. **Red-green.** The PR's test files are overlaid on main and run, and they must fail. On the PR they must pass. An empty test such as `assert True` passes on main already, and is therefore blocked.
3. **No disappearing.** A TC that passed on main may not go missing later. The spec itself is protected by CODEOWNERS, so an agent cannot quietly delete a TC.
4. **Fidelity audit.** The review agent (different from the agents that wrote the tests and the implementation) judges each TC one by one: do the test's assertions really verify the behaviour described? This layer covers the case the first three cannot see: the test exists and goes red and green, but verifies the wrong thing.

The first three layers are run by the single check `spec-verify`.

After the merge, the `evidence` workflow posts the "AC → TC → test → result" table to the story's issue. You read that table, not the code.

This guarantee has two limits. First, it ensures that every TC you approved has a running test that changes with the behaviour, but it does not guarantee that the list of TCs is itself complete. The completeness of the list depends on the PO's questions and on your reading when you approve the story. Second, the test results are produced by the PR's code, and an agent is able to write a fake results file directly. There is no hard defence against this. It relies on the `Makefile` being protected, the review agent and the weekly spot check.

### The strength of `agent-review`

This is the only one of the five checks judged by an agent, and also the weakest. That should be stated honestly.

Claude's review runs as a workflow job, and the job itself writes the status. The implementation agent's token does not have that permission, so it cannot forge it. Codex's review comes from its GitHub integration and is turned into a status by the `bridge` job. If the review is instead done in an ordinary cloud session, the reviewer and the implementer may be the same GitHub identity, and in that case the two cannot be told apart by identity.

The design therefore lets no hard guarantee depend on `agent-review`. High-risk changes have human approval, and the existence and validity of tests have mechanical checks. Agent review provides a check at the semantic level, and the cost of a wrong pass is bounded by the other gates.

## 5. From one line to production

```
Stage 0  You say one sentence (PO chat, or write it into the roadmap)
Stage 1  PO agent produces the story            → you approve the spec PR 【Gate 1】
Stage 2  design   the design agent writes the design document
Stage 3  tests    the test agent writes tests from the story alone (they must be red at this point)
Stage 4  impl     the implementation agent turns the tests green
Stage 5  review   the review agent reviews the implementation and audits the tests
Stage 6  all five checks green → auto-merge → evidence table posted to the issue
Stage 7  you push a v* tag → deploy to production                         【Gate 2】
```

Each stage is a brand-new agent session with no memory of the previous session. Everything it needs is in the spec, the story issue, the branch and the commit history. The instructions are in `prompts/` and are vendor-neutral.

### AI Product Owner

Your requirement is usually one sentence. The PO (`prompts/product-owner.md`) turns it into a story you can approve within two minutes.

- It first reads the domain documents in `docs/product/` and the related existing stories, and checks whether the new requirement conflicts with existing behaviour.
- It asks at most five questions, and only those that "would change what is to be built and are hard to undo afterwards": payment flow and order states, what happens after a failure or a rejection, who has permission, data retention and outbound notifications. It decides the rest itself and lists those decisions as assumptions.
- It produces three files: `story.md` (English, what agents implement and review against), `story-zh-TW.md` (Traditional Chinese, the version you read and approve) and `spec.toml` (machine-readable). Each of the two stories is limited to 80 lines. For an example see `docs/specs/000-example/`, which is the result of the sentence about paying by bank transfer with proof of payment.

You approve the Chinese and the agents read the English. The gap in meaning between the two is the main risk of bilingual stories. It is handled in three layers. `spec-lint` checks that the AC and TC IDs of the two files are the same and in the same order, and that the sections are the same. CI checks that the two files must change together in the same PR. The PO compares them item by item after writing, and the review agent from the other vendor compares them item by item once more, treating a difference in meaning as blocking. The first two layers are mechanical checks. The third is an agent's judgement, not a hard guarantee. If the two differ, the English version governs, because that is the version actually implemented.

Two modes. **chat**: you talk with it on your phone or desktop, which suits requirements you want to discuss in depth. **async**: you only add a line to `docs/product/roadmap.md`, the conductor dispatches the PO to draft a spec PR, the questions are written in the PR description, and you answer with review comments. When you come back, what you face is a spec you can approve directly or answer briefly. Unapproved spec PRs are capped at three, to avoid a pile-up.

You approve by approving that PR on GitHub. The mobile app is enough. Labels are not used as the approval signal, because agents can change labels.

### Role assignment

`policy/roles.toml` sets, per developer, which harness each stage uses, with a fallback order. The principle is for the reviewer and the implementer to be from different vendors.

The practical constraint is quota. Implementation is the most token-hungry stage and review the lightest, so put implementation on a person's larger subscription and review on the smaller one. Three common setups:

| Setup | Who reviews | What you give up |
|---|---|---|
| One person, one vendor | A fresh session of the same harness | Cross-vendor review. The mechanical checks carry the main guarantee |
| One person, several vendors | A different vendor from the implementer | Nothing, as long as quota lasts on both |
| Several people, each with their own AI | Whatever each person's own set allows | People with one vendor get same-vendor review on their stories |

In every setup a T2 change still goes to a human. With one person, that human is also the director. After a plan upgrade, changing the settings is all that is needed.

Separating the roles into different sessions is not enough if every session holds the same powers. So each stage's sandbox is given only what that stage needs:

| Stage | Its GitHub token can | Network | May edit |
|---|---|---|---|
| design, tests, impl (and its fix and conflict runs) | Push branches; comment, label | Source control, model providers, package registries | Code and tests; not guardrails, not approved specs |
| review, triage | Read the repo; comment, label, review. **Cannot push** | Source control and model providers only | Nothing it could deliver anyway |
| product-owner, planner | Push branches; comment, label | Source control and model providers only | Specs, sprints, product documents; not guardrails |

The first two columns are hard controls. GitHub mints an App token with a subset of the App's permissions, and the sandbox's network policy is set per sandbox, so a reviewing agent that tries to push is refused by GitHub, whatever its prompt or its own reasoning says. The third column is the harness's deny rules, a soft layer. The table lives in `tools/agentctl/profiles.py` as constants, and a sandbox is set up from a copy of that file pinned outside the repo, so a branch cannot give itself more.

Two limits. GitHub permissions are per repository, not per path: "the test writer must not touch the implementation" and "the implementer must not weaken a test" cannot be expressed in a token, and stay with `spec-verify`, CODEOWNERS and review. And this separation exists only on the Docker Sandboxes path. The Lima fallback is one long-lived VM that every stage shares, and a cloud session acts with the account you connected, whatever the stage.

## 6. Continuous operation: the conductor

When you are away, it is the conductor that moves work forward.

### What it is

A program with no state and no LLM (`agentctl reconcile`). It can run in a terminal on your Mac, and it can run on GitHub Actions. On every run it reads the complete current situation: sprint, specs, issues, PRs, check results. It works out the next thing that should happen now, then does it. It remembers nothing itself. All memory is on GitHub (labels, issue links, hidden marker comments). So interruptions, reruns and missed events do no harm: the next run reaches the same conclusion.

### Where the conductor runs

The conductor is a deterministic program, not an agent, so running it directly on your Mac is safe, and it uses no Actions budget.

- **You are at the computer**: `bin/agentctl conductor here`. It polls every three minutes, and each time it reads the approved sprint, specs and policy from `origin/main`, not from the contents of your working directory.
- **You are going out**: `bin/agentctl conductor away`, or just press Ctrl-C. This hands over to GitHub Actions.
- **You close the laptop without handing over**: the local conductor renews a lease on every run. The scheduled Actions run, every four hours, checks it and takes over automatically if it has not been renewed for more than 20 minutes.

Two repo variables ensure that only one side acts at a time: `CONDUCTOR_HOME` (`local` or `actions`) and `CONDUCTOR_LEASE`. While the local side holds the lease, event-triggered runs on Actions are skipped and use no minutes.

On Actions, events are the main driver (`ci` completing, a PR closing, a review being submitted, a label changing on an issue). The schedule only catches stalls and missed events. A local run uses your own `gh` login. The trigger URL and token needed for dispatching are kept in `.env.conductor` (listed in `.gitignore`).

### Where the judgement about order comes from

A program cannot judge which story should be done first. It does not need to, because the judgement happens elsewhere:

**At planning time, an agent judges and you approve.** The planner (`prompts/planner.md`) reads all candidate stories and the code, and settles for each story its `depends_on` (stories that must be merged first), `touches` (the modules and shared resources it will change) and `priority`. These are written in `spec.toml` and come to you for approval with the sprint PR. What you approve is the scope and the priority order.

**At run time, a program computes.** A story may start when: the stories it depends on are all merged, it is not marked blocked, its `touches` do not intersect those of stories in progress, and the limit on stories in progress at once is not exceeded. Those that qualify are ordered by priority, by the number of downstream stories they unblock, and by number. The same input always gives the same result, uses no quota, and can be unit tested in full.

**When something goes wrong, a short-lived triage session judges.** Planned dependencies will contain mistakes. A common one is discovering halfway through that another, unfinished story is needed. When the conductor detects a stage failing repeatedly or stalling, it starts a triage agent (`prompts/triage.md`). It can do only three things: add a "blocked by" link, ask for a retry and explain what to do differently, or escalate to you with options. It cannot change the spec, cannot change the sprint scope, and cannot touch code or tests.

### Why not keep a long-running LLM session as supervisor

A long session's state is in its context. Context gets compacted and instructions are lost, a session cannot be fully restored after an interruption, its behaviour is hard to audit, and it consumes quota continuously. With the state on GitHub and a brand-new context for every judgement, these problems do not exist.

Experience with existing tools points the same way. For Gas Town, which uses an LLM as coordinator, the author says it stopped working after a model upgrade, with agents turning to modifying the harness itself over and over (this item comes from secondary reports). The Claude Code agent teams documentation records that the lead finishes early and that task status lags behind and blocks downstream work. Anthropic's engineering article on long-running agents argues for starting every session from a brand-new context and keeping continuity in files and git. The closest to this design is OpenAI Symphony: a deterministic reconcile loop with the issue tracker as the source of truth. It supports only Codex and Linear, so this repo adopts its approach rather than its implementation.

### What it does and does not do

- When a story is waiting on you, it goes around it and works on something else. A story waiting on you does not take one of the slots for stories in progress.
- When every unfinished story in the sprint is stuck on you, it stops everything and notifies you once.
- When the sprint is complete and the next one is not yet approved, development stops. Only the drafting of specs continues. It does not expand the scope on its own.
- When a PR falls behind main, it updates the branch. When there is a conflict, it dispatches a conflict-resolution task.
- When main turns red, it stops dispatching and dispatches only one repair task.
- When a harness runs out of quota, it switches to the fallback. When all are exhausted, it waits.
- When all gates pass, it enables auto-merge, but only for the tiers listed in `auto_merge_tiers` in `policy/conductor.toml`.

### Fuses

- **Kill switch**: set the repo variable `CONDUCTOR_PAUSED` to `true`, and from the next run on all dispatching stops.
- Limits: the number of stories in progress at once, the number of PRs opened per day, the number of retries of the same stage, the number of fix and review rounds, the number of triage sessions. Beyond a limit it escalates to you. It does not retry without end.

### Actions budget

GitHub measures the allowance in money: $18 a month on the Team plan. A standard Linux runner costs $0.006 per minute (about 3,000 minutes), a 1-core Linux runner costs $0.002 per minute, and self-hosted runners are not billed. **Each job's time is always rounded up to a whole minute**, so a job that runs for 5 seconds also counts as one minute. This rule shapes the design below.

- The test suite runs only as many times as necessary: once on head, plus, for a story branch, once on base with the test files overlaid. Both happen in the same job.
- A draft PR runs only lint. The full gates are left until the implementation is complete: about three times per story rather than once per push.
- An agent pushes only once, at the end of each stage.
- Light jobs that do not run the PR's code (`spec-verify`, `risk-gate`, conductor, evidence, brief) can use a 1-core runner instead, set with the repo variable `LIGHT_RUNNER`.
- The conductor's heartbeat on Actions is once every four hours. When you are at the computer, it does not run on Actions at all.

| | First version | Now |
|---|---|---|
| Each full gate run | about 5T + 7 minutes | about 2T + 4 minutes, plus about 3 light jobs |
| Full gate runs per story | about 8 | about 3 |
| Per story (T=3) | about 215 minutes | about 55 minutes equivalent |
| Fixed overhead per month | about 750 minutes | about 70 minutes equivalent, lower when the conductor runs locally |
| Stories supportable per month (T=3 / T=10) | about 10 / 4 | about 50 / 30 |

T is the number of minutes one run of the test suite takes. "Equivalent" means 1-core runner minutes converted by unit price. **These are all estimates and have not yet been measured.** The spike in the runbook asks you to record the actual numbers.

**Overflow to self-hosted.** `agentctl budget` estimates the month's usage from the Actions job records (it runs in both the daily brief and the conductor's scheduled runs). When usage reaches 85% of the allowance, it points the repo variable `CI_RUNNER` at the runner inside the VM on your Mac, and changes it back when a new month begins. The threshold, the unit prices and the allowance are all in `policy/conductor.toml`.

Only `ci` and `security` move over, because they are the heavy jobs that run the PR's code. The jobs that judge always stay on GitHub-hosted runners: a self-hosted runner is not rebuilt between jobs, and a machine that PR code has touched cannot be used to judge that same code. If the Mac is closed during overflow, these two checks queue, and the conductor treats them as in progress and waits.

### Where agents run

| Location | How it is started | Does the laptop need to be open |
|---|---|---|
| Claude Code cloud session | The conductor calls a scheduled task's API trigger | No |
| Codex cloud | The conductor leaves an `@codex` comment on the PR or issue | No |
| Claude review | The `agent-review` workflow job | No |
| Local Docker Sandbox, clone mode | The conductor running on your Mac starts it directly | Yes |
| Self-hosted runner in the Lima VM | The conductor starts the `agent-job` workflow, and the runner picks it up when it comes online | Yes |

The first three are the main workforce. The last two are extra capacity and a fallback, and need the Mac to be on; Ollama tasks can only use them. A stage assigned to a local sandbox while the conductor is on GitHub Actions simply waits until the conductor runs on the Mac again. Which cloud path actually works has to be confirmed by the spike. For one that does not, change it to `via = "sbx"` in `policy/roles.toml`.

## 7. Your day to day

You do four things:

1. Add a line to the roadmap, or say one sentence to the PO.
2. Approve or answer spec PRs.
3. Approve sprint PRs.
4. Push release tags.

You look at two places:

- **Director's brief**: one fixed issue, updated every day. It contains sprint progress, things waiting for your decision, items that are stuck, newly merged items, and the estimate of the month's Actions usage along with where the conductor is currently running. Every Monday it has an extra audit section: the number of merges per tier, the number of reverts, the number of escalations, and a few randomly drawn PRs that were merged without a human, for you to spot-check. The numbers come from GitHub, not from what agents say about themselves.
- **GitHub notifications**: PRs that need your review and issues assigned to you are your decision queue.

## 8. Turning on auto-merge in stages

A new project's tests are not yet good enough to serve as the basis for merging, so `auto_merge_tiers` is empty by default (shadow mode): every gate is computed and reported as usual, but you press merge, and the conductor only notifies you that "this one can be merged".

Observe for a while. Once you have confirmed that the gates' conclusions agree with your own judgement, turn on `T0` first, then `T1`. T2 always needs human approval.

The credibility of auto-merge is capped by the quality of the tests. That is the reason for doing it in stages.

## 9. Verified and not yet verified

**Verified during development:**

- `agentctl`'s risk tiering, bilingual spec and document checks, traceability, red-green judgement, conductor scheduling logic, budget estimate and lease judgement: 96 unit tests in total.
- Red-green was run end to end on a real git repo, split into two steps, collect and judge: an empty test was blocked, and passed after being changed into a real test. When the collect step was not run, the judgement was fail rather than pass.
- The conductor's GitHub interface layer was run against a simulated `gh`: dispatching, leaving markers, marking a draft ready for review, a single failed action not affecting the others. While the lease is valid the Actions side does not act, and it takes over when the lease expires. When usage reaches the threshold it rewrites `CI_RUNNER`.
- The workflows pass actionlint, the shell scripts pass shellcheck, and the command-blocking hook has tests.

**Not yet verified, to be done on your accounts and machines (the spike in the runbook and the red-team checklist):**

- The conductor's behaviour against the real GitHub API, in particular the API for issue dependency links and the reading of check status.
- The actual interface for triggering a Claude cloud scheduled task by API, and whether starting an arbitrary task with an `@codex` comment is feasible and what it requires of the commenter's identity.
- What a cloud session connected to a personal admin account can do on GitHub (section E of the red-team checklist).
- Minting an agent App token against the real API (`agentctl app-token`).
- The current input parameters of `anthropics/claude-code-action`; the account name of the Codex review bot and its review format.
- Docker Sandboxes on a real Mac: the `sbx` commands used by `sandbox/sbx.sh`, clone mode, whether the proxy injects the App token into `git push` over HTTPS (the documentation does not spell this out), the home directory path inside the sandbox, and headless runs of each harness.
- Narrowing an App token to fewer permissions through the real API, and per-sandbox network rules: both follow the documentation and neither has been exercised.
- The Lima configuration and egress rules under `sandbox/`.
- Whether the sandbox and permission syntax in `.claude/settings.json` matches the current version.
- The actual label of the 1-core runner; the permissions needed for `workflow_run` to trigger the conductor and for downloading artifacts across workflows; the Conductor App's permission to write repo variables.
- How required checks that were skipped on a draft PR behave after it is marked ready for review.
- The actual gap between the budget estimate and the GitHub bill; whether the runner labels returned by the Actions jobs API are enough to tell the three classes of runner apart.
- The behaviour of the local conductor (`conductor here`) on a real repo.
- The feature boundaries of the GitHub Team plan on private repos: rulesets and auto-merge are available, merge queue and required reviewers for environments are not. The latter is why releases use tag protection instead.

## 10. Known limitations

- The two developers themselves are trusted. The design defends against agents going out of control and against prompt injection, not against insiders.
- In clone mode the agent's work exists only inside the VM until it pushes. A stage that ends without pushing leaves nothing behind except its log.
- In the Lima fallback, and in sbx's direct mode, the workspace is mounted read-write. The agent can then destroy the working tree and can plant a git hook that later runs on the Mac. That is why clone mode is the default.
- Docker Sandboxes is at version 0.x. Its commands may change.
- Per-stage privileges exist only on the Docker Sandboxes path. In the Lima fallback every stage shares one VM and one write token. In a cloud session every stage acts as the account you connected.
- The subscription login state inside the VM could in theory be stolen by malicious repo content. The egress allowlist reduces this risk but does not remove it.
- In the Lima fallback, egress rules filter by address, so other hosts that share an address with an allowed host are also reachable.
- Cloud sessions act as the personal account you connect. Until section E of the red-team checklist has been run, assume a cloud agent can do on GitHub whatever that account can, limited only by rulesets that have no bypass. The release tag ruleset lets admins bypass, so it is one of the things to test.
- What you paste into the PO chat or an issue enters the vendor's context and is outside the isolation.
- There is no hard guarantee that the two language versions of a story mean the same thing. If the Chinese you approved and the English the agents implement differ, only the review agent and you yourself can catch it.
- Test results are produced by the PR's code and can be forged. See section 4.
- Actions usage is an estimate. It may differ from the bill, so the overflow may come too early or too late.
- `touches` is a prediction and will miss things. The cost is merge conflicts and rework, corrected afterwards by triage. It does not lead to wrong code being merged.
- The capacity for continuous operation is limited by subscription quota. When quota runs out, work slows down. It does not fail.
- Cloud triggering depends on features that both vendors are still evolving. The fallback is the self-hosted runner, but it needs the Mac to be powered on.
- While you are away, things waiting for your decision accumulate. This is the only pace in director mode that is set by you.
