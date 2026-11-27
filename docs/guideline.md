# Guideline for the AI Coding Agent Development Kit

*繁體中文：[guideline-zh-TW.md](guideline-zh-TW.md). The English version governs if the two differ.*

This document explains the design of the kit: why it is built this way, how the parts fit together, what has been verified and what has not. It has no setup steps. Each layer has its own setup document and checklist: [layer 1, isolation](layer-1-isolation.md), [layer 2, GitHub protection](layer-2-github.md), [layer 3, CI gates](layer-3-ci.md) and [layer 4, the conductor](layer-4-conductor.md). Adopting the kit in a project is in [adopting.md](adopting.md). Threats and the controls that answer them are in [threat-model.md](threat-model.md).

## 1. Goals

1. **Agents cannot reach your private data and cannot cause irreversible damage.** In order of severity: reading private files (once read, it cannot be taken back), deleting files outside the working directory by mistake, using temporarily valid cloud credentials on the machine, and, in future, production.
2. **Human attention is the bottleneck.** You are the director: you decide what to build, approve the scope, and release to production. You do not read ordinary pull requests, merge, or dispatch work.

The kit assumes nothing fixed about the team. One person with one AI subscription is enough. So is one person with several, or several people who each bring their own. Who may approve product decisions, and which harness does which stage for each person, are settings in `agentdev.toml` (`[roles]`), and CODEOWNERS is generated from the same file. Only two things are constant: agents run on subscriptions, with no pay-as-you-go API keys, and the repository is on a GitHub plan that enforces rulesets on private repositories.

## 2. Three principles

**Protect with capability boundaries, not with agent self-discipline.** Prompts, permission settings and command blocklists can all be bypassed, so they only count as a second layer. The real guarantee is that nothing capable of causing damage exists in the environment where the agent runs. It cannot see your home directory, and the token it holds has no dangerous permissions.

**GitHub is the only control plane.** All harnesses hand work over only through branches, pull requests and issues. Changing models, changing vendors or adding a local model does not change the process. This is also why no API key is needed: each vendor's model runs in its own harness on subscription quota.

**Mechanical checks take precedence over what the agent says about itself.** Agents declare completion too early and overestimate their own output. Whatever can be verified by a program (whether a test really exists and runs, whether it really exercises the behaviour) is not asked of the agent.

## 3. The kit, its layers and its settings

### Four layers

| Layer | Concern | Main parts |
|---|---|---|
| 1. Isolation | Agents cannot reach the Mac or hold powerful credentials | Docker Sandboxes (sbx) in clone mode, a GitHub App per developer for agents, Mac hygiene, cloud sessions |
| 2. GitHub protection | Agents cannot change what judges them, merge, or release | Rulesets (`templates/rulesets/`, applied by `agentctl rulesets 2`), CODEOWNERS generated from `agentdev.toml`, the `conductor` environment, the Conductor GitHub App |
| 3. CI gates | Nothing merges without evidence | The reusable workflows `ci`, `security`, `spec-verify`, `risk-gate`, `agent-review` |
| 4. Conductor | Work moves forward without you | `agentctl conductor`, which dispatches stages to agents, opens pull requests and, once you allow it, merges |

Each layer can be adopted on its own, but they lean on one another. Layer 2 can be adopted alone. Layer 3 is only as strong as layer 2: a check an agent can edit or skip proves nothing. Layer 4 needs the identities of layer 1 and the rulesets of layer 2, and its merges are only as good as the gates of layer 3. For an existing project the order is 1 and 2, then 3, then 4 in shadow mode (section 9).

### Installed once per Mac, pinned per project

The kit's host-side code runs on the Mac with your permissions, and an agent can change anything in a project's tree. So that code is never in the project tree.

- `install.sh [REF]`, run from a clone of the kit, unpacks a version by its full commit SHA into `~/.local/share/agent-dev-kit/versions/<sha>/`, makes it read-only, and puts the `agentctl` launcher in `~/.local/bin`.
- The launcher runs the version the project pins in `agentdev.toml` (`[kit] version`), read from the project's **default branch** (`origin/HEAD`, as last fetched), never from the working tree. A branch, an agent's included, cannot choose which code runs on the Mac. `AGENTDEV_KIT_VERSION` overrides the pin, for use outside a project or while adopting the kit before the pin is on the default branch.
- The launcher starts the tools as `python3 -I`, which keeps the current directory and `PYTHONPATH` off the import path, so a file named `json.py` in a checkout cannot shadow the real module.

Consequence: there is no "is this checkout trusted" check, no per-project copy of the tools, and no rule against running host scripts from an agent's branch. Code an agent cannot change needs none.

The same holds in CI. Each reusable workflow takes `kit_version`, fetches the kit at that SHA from codeload into the runner's temporary directory, and runs it from there. A project's caller workflows (`agentdev-*.yml`) name the SHA twice, in `uses: ...@<sha>` and in `kit_version: <sha>`. `agentctl pins`, run in the `ci` lint step, fails unless both equal `[kit] version`. To upgrade, change the SHA in `agentdev.toml` and in every caller in one pull request, which is a T2 change, and run `./install.sh <sha>` on each Mac.

### One configuration file

`agentdev.toml` at the project root holds every project setting, over the kit's defaults (`tools/agentctl/defaults.toml`, which is the reference for every key). Tables merge key by key; any other value, a list included, replaces the default as a whole. `agentctl config KEY` prints a setting.

| Section | Holds |
|---|---|
| `[kit]` | The pinned version and the kit's repository |
| `[paths]` | Where specs, sprints, the roadmap, product documents and design notes live |
| `[stories]` | `id_digits` (default 3), `translation` (default `zh-TW`, `""` for none), `max_lines` |
| `[docs]` | Translation pairing of documents and which must exist |
| `[tests]` | `setup_cmd`, `lint_cmd`, `test_cmd`, `junit_glob`, `test_paths`: the contract with the project's stack |
| `[risk.thresholds]`, `[risk.t0]`, `[risk.t2]` | Risk tiers (section 6) |
| `[conductor]` | Limits, fuses, `auto_merge_tiers`, stage timeouts, the Actions budget |
| `[roles]` | Directors, humans, the planner, how each harness is started, which harness does which stage for whom |

`.github/**` and `agentdev.toml` are always guardrails, whatever a project writes. T2 can never be listed in `auto_merge_tiers`. A change to the file is T2, so an agent cannot loosen its own limits. The stage prompts belong to the kit (`prompts/`); they are templates filled in from this file (`agentctl prompt STAGE`), and the conductor sends the whole rendered prompt in each dispatch, so a project needs no prompt files.

## 4. Trust zones

| Zone | Contents | What an agent can do |
|---|---|---|
| 0 Your Mac | Private data, browser, Keychain, temporarily valid cloud tokens, the installed kit, Ollama | Coding agents do not run here |
| 1 Sandbox | A local microVM, or the vendor's cloud session. The project's repository, mounted read-only, with a private clone inside | Full autonomy inside; cannot get out |
| 2 GitHub | Rulesets, required checks, CODEOWNERS | Can only push branches. Cannot open or merge a pull request; everything else must pass the gates |
| 3 Production | Cloud resources, databases | Nothing. Only a release tag pushed by a human can trigger a deployment |

### Rules for zone 1

**Coding agents always run in a microVM or in the cloud, never directly under a user account on the Mac.**

The sandbox built into a harness is not enough to protect privacy. Claude Code's sandbox allows reading almost the whole file system by default, and it covers only Bash, not the file tools, MCP servers or hooks. Codex's `workspace-write` likewise restricts only writes. They work against accidental deletion, but protection against reading depends on you listing every path correctly. A microVM's mounts are deny by default: what is not mounted does not exist.

The local sandbox is Docker Sandboxes (`sandbox/sbx.sh`, run through `agentctl sandbox`). It is the only supported local runtime. Its properties:

- **One microVM per agent**, with its own kernel.
- **Clone mode.** The repository is mounted read-only and the agent works on a private clone inside the VM. Nothing it does changes a file on the Mac, and its only way to deliver work is `git push`. This matters more than it looks. With an ordinary read-write mount, an agent can write a git hook into `.git/hooks`, and that hook then runs on the Mac, as you, the next time you use git in that directory. The mount is the whole repository directory, including untracked and ignored files, so nothing secret may live in the project directory. The script refuses to start a sandbox while it finds an untracked file whose name looks like a secret. That check goes by file name, so it is a reminder, not a guarantee.
- **Outbound connections are denied except to allowlisted hosts**, filtered by host name: sbx's deny-all preset plus `sandbox/allowlist.txt`, and the package registries of `sandbox/allowlist-build.txt` only for stages that build. The allowlist limits both data exfiltration after a prompt injection and callbacks from malicious packages. Because the preset is machine-wide and can be changed outside the script, each sandbox is also probed from inside when it is created: GitHub must be reachable, and two hosts that are not allowlisted must not be. This is a spot check of three hosts at that moment. It cannot tell a policy denial from an origin's own 403 or 5xx answer, and it does not prove that the effective allowlist equals the project's lists.
- **No GitHub credential inside the VM.** A proxy on the host replaces a placeholder with a one-hour token of the developer's agent GitHub App, which a helper on the host mints when it is needed. The App's private key never leaves the host. SSH agent forwarding is turned off, because it is on by default and would let the agent push as you. The shared skills store is turned off too, because by default it is mounted read-only into every sandbox.
- **One sandbox per dispatched stage, never reused**, and removed however the job ends. Stages share no files, processes or login state, and each is given only what it needs (section 7, "Role assignment").
- **Nothing from the project directory is executed on the host.** The sandbox scripts are the installed kit's own, and what they read from the project (`agentdev.toml`) comes from the default branch. Story id, stage and harness are validated before they reach a path, a sandbox name or a command.

There is no interactive mode. To work with an agent yourself, use sbx directly (`sbx create --clone`, `sbx run`). Such a sandbox gets the machine-wide deny-all preset and allowlist from `agentctl sandbox setup`, but no GitHub token and no harness deny rules.

**Cloud sessions** (Claude Code on the web, Codex cloud) are vendor-managed VMs that cannot reach your laptop at all. They are the strongest isolation for privacy, and the only place where work can continue while the laptop is closed. Set the environment's network to restricted and put no secrets in it.

### Hygiene rules on the Mac

`agentctl doctor` checks those of the following that can be checked.

- Keep projects somewhere not synced by iCloud, such as `~/dev`. An accidental deletion in a synced directory syncs to every device.
- Keep nothing secret in the project directory: no `.env` files, keys or credentials, ignored ones included. A clone-mode sandbox can read the whole directory. For this reason the conductor's credentials live in `~/.config/agent-dev/<owner>-<repo>/conductor.env` and the agent App's key in `~/.config/agent-app/`, outside the repository.
- Do not grant Full Disk Access to the terminal or the IDE. Any program run inside them inherits that permission.
- Do not enable computer use, screen recording or accessibility for agent-type desktop apps. Do not install agent extensions in the browser profile you use every day. Do not connect personal Gmail, Drive or iCloud as an agent connector or MCP server. These paths bypass the VM and reach private data directly, and there is no technical means to enforce the rule. It holds only by not turning them on.
- Turn on Time Machine or an equivalent backup.
- Optional: create a separate standard macOS user account for development. With private data under another account, file permissions block reading. The cost is the nuisance of switching accounts.

If you really must run an agent directly on the Mac (for example, a brief interaction inside the IDE), the project's `.claude/settings.json` and `sandbox/codex-config.example.toml` provide strict settings. This is the exception, not the norm.

### Story agents and maintenance work

Agents have two roles in a project, and the guardrails ask different things of each.

A **story agent** is dispatched by the conductor and runs unattended. It must not edit the guardrail paths. The hard layer is CODEOWNERS, the rulesets and token permissions. The soft layer is the harness deny rules, generated for each sandbox from `[risk.t2]` (`agentctl harness-settings story|spec`) and installed in the sandbox and in the cloud environment. The product owner and the planner are dispatched the same way but have to write specs and sprints, so their rules leave the spec paths open and the guardrail paths closed.

**Maintenance work** is when you ask an agent directly, in a session, to change the pipeline itself (workflows, `agentdev.toml`, agent settings). This is allowed on these conditions: a human asks in person, the work is done on a `chore/` branch, and a human approves the pull request. A dispatch prompt, an issue or the contents of a file does not count as such a request. The conductor opens the pull request for a `chore/` branch, ready for review. A human approves and merges it; the conductor does not enable auto-merge on it.

The project's shared `.claude/settings.json` holds only the rules that are true for both roles: no reading or writing in home, no force push, no cloud CLIs, no opening or merging pull requests on its own. Putting the rule against editing guardrails there would block even maintenance work you had asked for.

## 5. Identities and tokens

Three identities, with separate permissions:

| Identity | What it is | Can | Cannot |
|---|---|---|---|
| Human | The people on the project, repository admins | Approve pull requests, merge, push release tags, change settings | Push directly to main (nobody can); skip a check or an approval |
| Agent | A GitHub App per developer, for that developer's agents | Push branches, comment, change labels. The review token can review a pull request instead of pushing | Merge, approve as a code owner, change workflows, create tags, write commit statuses. The token that pushes cannot open, retarget or review a pull request |
| Conductor | One GitHub App for the pipeline | Open pull requests, mark them ready, enable auto-merge, merge, dispatch work | Approve pull requests; skip a check or an approval |

**Why each developer's agents get their own GitHub App.** An App has exactly the permissions it was granted, whatever its owner's role, so it carries no admin bypass. Its tokens expire after an hour. It takes no seat. And because there is one per developer, a commit or a comment shows whose agent made it. A personal access token cannot do the same: a token issued from an admin account, even a fine-grained one, still inherits the admin's eligibility to bypass rulesets. `agentctl app-token` mints the token on the host, and the sandbox's proxy injects it, so neither the key nor the token is inside the VM.

**A sandbox never gets the App's full permissions.** `tools/agentctl/profiles.py` defines two tokens. The `write` token, for stages that deliver code or specs, has contents: write, issues: write and pull requests: read. It can push a branch, but it cannot open, retarget or review a pull request. The `read` token, for review and triage, has contents: read, pull requests: write and issues: write. It can review and comment, but it cannot push. No agent token holds both powers; only the conductor does.

**Who may update `main`** is a second, separate limit. The ruleset `main-merge` lets only repository admins and the Conductor App update the default branch. This ruleset, not the narrowed token, is what keeps an agent from merging: GitHub's merge endpoint needs only contents: write, which the `write` token has. The `main` and `main-checks` rulesets have no bypass, so admins and the Conductor App must satisfy every check and approval too.

**Why the conductor is a separate GitHub App.** GitHub does not let an author approve their own pull request. If a cloud agent opened a spec pull request under your identity, you could not approve it. So the agent only pushes a branch, and the Conductor App opens the pull request. In addition, pull requests opened and merges made with the default `GITHUB_TOKEN` do not trigger other workflows, so the gates would not run at all. The local conductor acts as the same App for the same reason: it mints the App's token itself from the key on the Mac. If it acted as you, you would be the author of the pull requests it opens and could not approve them.

**Cloud sessions are the exception.** Claude Code on the web and Codex cloud reach GitHub through the vendor's own integration, acting as the user account you connect; you cannot put your own App in its place. A cloud agent then acts with that account's identity. The token limits above do not apply to it, and what it cannot do depends on the vendor's limits and on rulesets that have no bypass. The checklist of layer 1 tests exactly this: whether a cloud agent can create a release tag or approve a pull request. If either succeeds, there are two ways out. Connect a separate machine account for the cloud services, which costs one more seat. Or stop using the cloud path and run every stage in a local sandbox (`via = "sbx"`), which costs nothing but needs the Mac to be on with the conductor running.

## 6. Gates: what must hold before a merge

The rulesets are split by layer, so that layer 2 can be adopted alone. `agentctl rulesets 2` applies three of them; `agentctl rulesets 3` applies a fourth.

Layer 2. The first, `main`, has no bypass list and treats humans and agents alike:

- No direct push, no force push, no deletion. Merging only through a pull request, by squash.
- When a path listed in CODEOWNERS is touched, an owner (a human) must approve. A new push invalidates earlier approvals.

The second, `main-merge`, restricts who may update `main` at all: repository admins and the Conductor App. Its bypass list exempts those two from this ruleset only, not from the others. The third, `tags`, lets only admins create, move or delete any tag. A `v*` tag is a release approval; a tag of any other name could pass for a branch wherever a short ref name is resolved (git looks `origin/main` up among tags first), so the kit's own tools also use full ref names (`refs/remotes/origin/main`) or commit ids.

Layer 3. The fourth, `main-checks`, requires all five checks green, with the branch up to date with main, each reported by the GitHub Actions app (`integration_id: 15368`), so a status of the same name from another source does not count. It is applied only after the caller workflows are on the default branch and have run, because it requires checks they produce; applied earlier, it would block every pull request.

| Check as GitHub reports it | What it verifies | Judged by |
|---|---|---|
| `ci / ci` | Lint, all tests | Program |
| `security / security` | Secret scanning, static analysis | Program |
| `ci / spec-verify` | Traceability: every approved test case maps to a test that actually ran and passed, and one that has passed may not disappear. Red-green: the story's tests fail on main, as reported by the test runner, and pass on the branch | Program |
| `risk-gate / risk-gate` | Risk tiering; T2 needs a human approval of the current commit | Program and human |
| `agent-review` (a commit status) | A different agent's review of the implementation and of how faithful the tests are | Agent |

The names are "caller job / job", because the project's caller workflows call the kit's reusable ones. `layer-3-ci.md` explains them.

**The judges are not under the pull request's control.** `spec-verify` and `risk-gate` read the project's settings from the **base branch**, and run the kit at the pinned SHA, so a pull request cannot change the rules that judge it. `ci` reads them from the pull request, because it runs the pull request's code anyway. `spec-verify` itself runs none of the pull request's code: the tests run in the `ci` job, and the results are handed to `spec-verify` as files for judgement. Those files were produced by a job that ran the pull request's code, so `spec-verify` treats them as untrusted input. The artifact is unpacked in the runner's temporary directory, outside both checkouts, only plain `*.xml` files and `collected.json` are passed on, and a symbolic link anywhere in the artifact fails the job. This protects the judge, not the content of the results, which is still whatever that job wrote; see the limits below.

**Only pull requests into `main` are judged.** `risk-gate` also runs on a review, and a review event cannot be filtered by base branch, so its first step fails, rather than skips, when the pull request's base is not the default branch. GitHub counts a skipped job as a passed required check, and that result would stay on the commit after the pull request is retargeted. A pull request retargeted to `main` without a push has no `ci`, `security` or `spec-verify` result, so it stays blocked until the next push.

**Drafts.** The conductor opens a story's pull request as a draft. On a draft, `ci` runs lint only, and `security` and `spec-verify` are skipped. GitHub counts a skipped check as passed. That is acceptable only because a draft cannot be merged, and because marking it ready (`ready_for_review`) triggers a full run on the same commit. When the implementation stage is complete, the conductor marks it ready, and only then do the full gates run. This saves Actions budget.

### Risk tiers

Set by `[risk.*]` in `agentdev.toml`:

- **T0** Documentation only (`[risk.t0] paths`). Green checks are enough.
- **T1** A code change that belongs to an approved story. Passing checks and agent review are enough.
- **T2** Needs human approval. This covers: the guardrails themselves (`.github/**`, `agentdev.toml`, agent settings, `AGENTS.md`, `CLAUDE.md`, the scanner configuration, and so on), specs, sprints and product documents (`human_gated`), the project's high-risk code paths (`high_risk`: auth, payments, migrations, infrastructure by default; a list the project must set for its own layout), a change to a dependency manifest or lock file (`dependency_manifests`, a list the project must extend for its own stack), a diff over the size thresholds, and a code change that belongs to no story.

Test files are not T0. Weakening a test is a change in behaviour.

The changed paths are read from `git diff -z`. Without `-z`, git quotes a path that contains unusual characters, and a quoted path would match no pattern.

`risk-gate` publishes the tier twice. The label `tier:T0`, `tier:T1` or `tier:T2` on the pull request is for people. The commit status `risk-tier/T0`, `risk-tier/T1` or `risk-tier/T2` on the head commit is what the conductor reads when it decides whether it may enable auto-merge. An agent's token has issues: write and can edit labels, but it cannot write a commit status. When a commit carries more than one such status, the strictest wins; a commit with none is treated as T2.

### "The AI saying it will write test XYZ does not mean it really did"

In a story you have approved, every test case has an ID (`TC-012-03`, with the number of digits set by `[stories] id_digits`). Four layers of checks follow, and the first three do not depend on anything an agent says:

1. **Traceability.** The test name must carry the TC ID. CI reads the JUnit XML that the test runner outputs and confirms that every ID has at least one test that actually ran and passed. Tests that are skipped, that do not exist, or that are only mentioned in a comment do not count. The basis is the execution result, not a search of the source code. The project's `[tests] test_cmd` must run every test and write JUnit XML where `junit_glob` finds it; the kit ships a unittest wrapper (`agentctl junit-unittest`) for Python projects. In that wrapper, a test marked `expectedFailure` whose assertion fails is reported as skipped, so it never counts as a passing test case.
2. **Red-green.** The pull request's test files, and any file that mentions the story's TC ids, are overlaid on a clean checkout of main and run there, and they must fail. On the pull request they must pass. An empty test such as `assert True` passes on main already, and is therefore blocked. The run on main first executes `setup_cmd`, so that a test does not fail there merely for lack of dependencies. "Red" has to be something the test runner reported. A test that was skipped on main is not accepted as red. If the run on main produced no report at all, or `setup_cmd` itself failed there, the check fails, because nothing was shown. A test that is missing from a report that does exist is accepted as red only when a failure or an error in that report belongs to one of the story's overlaid test files, matched by the file's name without its extension. The usual cause is that the file could not be imported before the implementation exists. An unrelated failure elsewhere on main does not count.
3. **No disappearing.** A TC that passed on main must still pass, even if its spec was deleted in the same change. The only way to drop one is to list it in `retired.toml` in the specs directory (`retired = ["TC-012-03"]`). That file and the specs are protected by CODEOWNERS, so an agent cannot quietly delete a TC. The comparison uses up to five of the newest completed `ci` runs on main that have results, whatever those runs concluded, and a TC that passed in any of them must still pass. A run whose artifact is absent or expired is skipped. A listing or a download that fails makes the job fail; it is not mistaken for "no history". If no run has results (a new project, or the artifacts have expired after 90 days), `spec-verify` only warns.
4. **Fidelity audit.** The review agent (a different session from those that wrote the tests and the implementation) judges each TC one by one: do the test's assertions really verify the behaviour described? This layer covers the case the first three cannot see: the test exists and goes red and green, but verifies the wrong thing.

The first three layers are run by the single check `spec-verify`. After the merge, the `evidence` workflow posts the "AC → TC → test → result" table to the story's issue. You read that table, not the code.

This guarantee has three limits. First, it ensures that every TC you approved has a running test that changes with the behaviour, but it does not guarantee that the list of TCs is itself complete. That depends on the PO's questions and on your reading when you approve the story. Second, the test results are produced by the pull request's code, and an agent is able to write a fake results file directly. There is no hard defence against this. It relies on `test_cmd` and the files it runs being guarded, the review agent and the weekly spot check. Third, red-green shows that the story's tests do not pass on main. It does not show why. A test written to behave differently on main than on the branch, for example by checking whether a file exists, can still satisfy it. Catching that is the job of the fidelity audit.

### The strength of `agent-review`

This is the only one of the five checks judged by an agent, and also the weakest. That should be stated honestly.

Claude's review runs as a workflow, `agent-review`, started by the conductor from the default branch. The reviewer runs in a checkout of the default branch, and the pull request is checked out beside it, as data, so Claude Code's settings and hooks never come from the pull request. The workflow first checks that the pull request is open, comes from this repository and targets the default branch. A review is for one commit: the conductor passes the commit it recorded in the dispatch marker. If the head is a different commit when the job starts, the job fails before reviewing and the conductor asks again for the new head. The reviewing job has a read-only token and a restricted tool list, and writes its verdict outside both checkouts. A separate `publish` job, which never sees the pull request's files, posts the findings and sets the status. The verdict counts only if the review step itself succeeded; otherwise the status is failure, never pass. The implementation agent's token cannot write a commit status, so it cannot forge one.

For a reviewer that is not Claude (Codex, for example), a bridge job turns a review posted by a bot listed in the repository variable `REVIEW_BOTS` into the status. If a review is instead done in an ordinary cloud session, the reviewer and the implementer may act as the same GitHub identity, and the two cannot be told apart by identity. For a review started by a comment or run in a local sandbox, the prompt names the commit to review and tells the reviewer to stop if the head is a different commit. That is an instruction to an agent, not an enforcement like the workflow's check.

What remains is the reason this check is the weakest. The reviewer reads untrusted text: the diff, the commit messages and the files of the pull request. That text can talk it into a wrong verdict. The isolation limits what a misled reviewer can do. It does not limit what it concludes.

The design therefore lets no hard guarantee depend on `agent-review`. High-risk changes have human approval, and the existence and validity of tests have mechanical checks. Agent review provides a check at the semantic level, and the cost of a wrong pass is bounded by the other gates.

## 7. From one line to production

```
Stage 0  You say one sentence (PO chat, or write it into the roadmap)
Stage 1  PO agent produces the story            → you approve the spec pull request 【Gate 1】
Stage 2  design   the design agent writes the design document
Stage 3  tests    the test agent writes tests from the story alone (they must be red at this point)
Stage 4  impl     the implementation agent turns the tests green
Stage 5  review   the review agent reviews the implementation and audits the tests
Stage 6  all five checks green → merge → evidence table posted to the issue
Stage 7  you push a v* tag → deploy to production                         【Gate 2】
```

Each stage is a brand-new agent session with no memory of the previous one. Everything it needs is in the spec, the story issue, the branch and the commit history, and its instructions are the kit's prompt for that stage.

### AI Product Owner

Your requirement is usually one sentence. The PO (`prompts/product-owner.md`) turns it into a story you can approve within two minutes.

- It first reads the domain documents under `[paths] product` and the related existing stories, and checks whether the new requirement conflicts with existing behaviour.
- It asks at most five questions, and only those that "would change what is to be built and are hard to undo afterwards": payment flow and order states, what happens after a failure or a rejection, who has permission, data retention and outbound notifications. It decides the rest itself and lists those decisions as assumptions.
- It produces `story.md` (English, what agents implement and review against), `story-<lang>.md` (the language you approve in, `zh-TW` by default, omitted when `[stories] translation` is empty) and `spec.toml` (machine-readable). Each story file is limited to `max_lines` (80 by default). For an example see `examples/specs/000-example/`.

You approve the translation and the agents read the English. The gap in meaning between the two is the main risk of bilingual stories. It is handled in three layers. `spec-lint` checks that the AC and TC IDs of the two files are the same and in the same order, and that the sections are the same. CI checks that the two files change together in the same pull request. The PO compares them item by item after writing, and the review agent compares them again, treating a difference in meaning as blocking. The first two layers are mechanical. The third is an agent's judgement, not a hard guarantee. If the two differ, the English version governs, because that is the version actually implemented.

Two modes. **chat**: you talk with it on your phone or desktop, which suits requirements you want to discuss in depth. **async**: you only add a line to the roadmap, the conductor dispatches the PO to draft a spec pull request, the questions are written in the description, and you answer with review comments. Unapproved spec pull requests are capped at `max_open_spec_prs` (three by default), to avoid a pile-up.

You approve by approving that pull request on GitHub. The mobile app is enough. Labels are not used as the approval signal, because agents can change labels. The conductor opens spec and sprint pull requests ready for review. Once you have approved one, the conductor enables auto-merge on it, and it merges by itself when the checks are green. This is your decision, not the conductor's judgement, so it does not depend on `auto_merge_tiers`.

### Role assignment

`[roles.developers.<login>.stages]` in `agentdev.toml` sets, per developer, which harness each stage uses, with a fallback order; `default` covers a story with no assignee and anyone not listed. Whose story it is comes from the approved sprint file: `assignee` is the default, and an optional `[owners]` table names another developer for single stories. Issue assignees are not used. `[roles.harness.<name>]` says how each harness is started: `via = "http"` (a cloud scheduled task's API trigger), `"comment"` (a mention that starts a cloud task, for example Codex cloud) or `"sbx"` (a fresh local sandbox, only while the conductor runs on that Mac). Nothing here assumes a particular vendor: a project that uses only Codex lists only Codex.

The principle is for the reviewer and the implementer to be different sessions, and from different vendors where there are several. The practical constraint is quota. Implementation is the most token-hungry stage and review the lightest, so put implementation on a person's larger subscription and review on the smaller one.

| Setup | Who reviews | What you give up |
|---|---|---|
| One person, one vendor | A fresh session of the same harness | Cross-vendor review. The mechanical checks carry the main guarantee |
| One person, several vendors | A different vendor from the implementer | Nothing, as long as quota lasts on both |
| Several people, each with their own AI | Whatever each person's own set allows | People with one vendor get same-vendor review on their stories |

In every setup a T2 change still goes to a human. With one person, that human is also the director.

Separating the roles into different sessions is not enough if every session holds the same powers. So each stage's sandbox is given only what that stage needs:

| Stage | Its GitHub token can | Network | May edit |
|---|---|---|---|
| design, tests, impl (and its fix and conflict runs) | Push branches; comment, label. Cannot open, retarget or review a pull request | Source control, model providers, package registries | Code and tests; not guardrails, not approved specs |
| review, triage | Read the repository; comment, label, review. **Cannot push** | Source control and model providers only | Nothing it could deliver anyway |
| product-owner, planner | Push branches; comment, label. Cannot open, retarget or review a pull request | Source control and model providers only | Specs, sprints, product documents; not guardrails |

The first two columns are hard controls. GitHub mints an App token with a subset of the App's permissions, and the sandbox's network policy is set per sandbox, so a reviewing agent that tries to push is refused by GitHub, whatever its prompt says. A sandbox is never reused, so a review sandbox cannot inherit the package registries that an implementation sandbox was allowed. The third column is the harness deny rules, a soft layer. The table lives in `tools/agentctl/profiles.py` as constants in the installed kit, so a branch cannot give itself more.

Two limits. GitHub permissions are per repository, not per path: "the test writer must not touch the implementation" and "the implementer must not weaken a test" cannot be expressed in a token, and stay with `spec-verify`, CODEOWNERS and review. And this separation exists only on the sandbox path: a cloud session acts with the account you connected, whatever the stage.

## 8. Continuous operation: the conductor

When you are away, the conductor moves work forward.

### What it is, and why it is deterministic

A program with no state and no LLM (`agentctl conductor`, which runs the reconcile logic in `tools/agentctl/reconcile.py`). On every pass it reads the complete current situation: sprint, specs, issues, pull requests, check results. It works out the next thing that should happen now, then does it. It remembers nothing itself. All memory is on GitHub (labels, issue links, hidden marker comments). So interruptions, reruns and missed events do no harm: the next pass reaches the same conclusion.

It is not a long-running LLM session, for these reasons. A long session's state is in its context. Context gets compacted and instructions are lost, a session cannot be fully restored after an interruption, its behaviour is hard to audit, and it consumes quota continuously. With the state on GitHub and a brand-new context for every judgement, these problems do not exist. The same input always gives the same result, uses no quota, and can be unit tested in full.

Experience with existing tools points the same way. For Gas Town, which uses an LLM as coordinator, the author says it stopped working after a model upgrade, with agents turning to modifying the harness itself over and over (secondary reports). The Claude Code agent teams documentation records that the lead finishes early and that task status lags behind and blocks downstream work. Anthropic's engineering article on long-running agents argues for starting every session from a brand-new context and keeping continuity in files and git. The closest to this design is OpenAI Symphony: a deterministic reconcile loop with the issue tracker as the source of truth. It supports only Codex and Linear, so the kit adopts its approach rather than its implementation.

What it reads back is not trusted blindly. A marker comment is believed only when it was written by the conductor's own login or by a human listed in `[roles]`. An agent can comment on issues, so a marker from anyone else is ignored. A story's pull request is the open one, or else the merged one, from this repository into the default branch. Closed pull requests, pull requests into another base and pull requests from another repository are never picked. Only the branch name the spec defines, `story/NNN-slug`, is the story's branch.

### Where it runs

The conductor runs on **one Mac only**, in a terminal: `agentctl conductor`. It polls every 180 seconds (`--interval`). Each pass it reads specs, sprint and `agentdev.toml` from a fresh worktree of `origin/main`, not from your working directory, and acts on GitHub as the Conductor App, not as you. `agentctl conductor --dry-run` does one pass, prints the plan and acts on nothing. Ctrl-C stops it.

There is no GitHub Actions conductor, no lease and no hand-over. A lock file stops a second conductor for the same project on the same Mac. A second conductor on another Mac is not supported, and nothing detects it (a known limitation). When the Mac sleeps, or the terminal is closed, nothing advances. Agents already dispatched to the cloud keep working, but their pushes wait for the next pass to get a pull request, a review or a merge. After three failed passes in a row it waits 15 minutes between passes.

The conductor's credentials live outside the repository, in `~/.config/agent-dev/<owner>-<repo>/conductor.env`: the Conductor App's id and the path to its private key (`CONDUCTOR_APP_ID`, `CONDUCTOR_APP_KEY`), `DEVELOPER` (your GitHub login) and the dispatch secrets you use. A conductor on your Mac holds your credentials only. It dispatches the stories assigned to you and the unassigned ones, and defers a story assigned to another developer; a local sandbox (`via = "sbx"`) is only started on the Mac of the developer whose story it is.

The GitHub Actions side has three jobs: the reusable workflows of layer 3, the daily director's brief (which also runs `agentctl budget`), and the secrets of the `conductor` environment that the review workflow needs. The environment's deployment branch rule allows the default branch only, so a run from any other ref is refused the secrets. Secrets must be created as environment secrets of `conductor`, not as repository secrets. A named developer's review uses only that developer's `_<LOGIN>` secret, and a missing one fails the dispatch before anything is written.

The conductor opens the pull requests. A story branch gets a draft. A spec, sprint or chore branch gets a pull request that is ready for review. The author is the Conductor App, so a human can approve.

### Where the judgement about order comes from

A program cannot judge which story should be done first. It does not need to, because the judgement happens elsewhere:

**At planning time, an agent judges and you approve.** The planner (`prompts/planner.md`) reads all candidate stories and the code, and settles for each story its `depends_on` (stories that must be merged first), `touches` (the modules and shared resources it will change) and `priority`. These are written in `spec.toml` and come to you for approval with the sprint pull request. What you approve is the scope and the priority order.

**At run time, a program computes.** A story may start when: the stories it depends on are all merged, it is not marked blocked, its `touches` do not intersect those of stories in progress, and `wip_limit` is not exceeded. Those that qualify are ordered by priority, by the number of downstream stories they unblock, and by number. A story that has started and then has to wait for a dependency added later by triage is parked: it holds no slot and no claim on its `touches`. When several started stories become eligible again at once, the lowest ids are given new work first, within `wip_limit` and never two that touch the same thing.

**When something goes wrong, a short-lived triage session judges.** Planned dependencies will contain mistakes. A common one is discovering halfway through that another, unfinished story is needed. When the conductor detects a stage failing repeatedly or stalling, it starts a triage agent (`prompts/triage.md`). It can do only three things: add a "blocked by" link, ask for a retry and explain what to do differently, or escalate to you with options. It cannot change the spec, cannot change the sprint scope, and cannot touch code or tests.

### What it does and does not do

- When an agent has pushed a branch that has no pull request yet, it opens one.
- When a story is waiting on you, it goes around it and works on something else. A story waiting on you does not take a slot. A red `risk-gate` (a T2 change waiting for approval) is such a wait. It is never reported as "ready to merge".
- When every unfinished story in the sprint is stuck on you, it stops everything and notifies you once.
- When the sprint is complete and the next one is not yet approved, development stops. Only the drafting of specs continues. It does not expand the scope on its own. It asks for the next sprint to be drafted once the share of merged stories reaches `draft_next_sprint_at`.
- When a pull request falls behind main, it updates the branch. When there is a conflict, it dispatches a conflict-resolution task.
- A fix, a conflict resolution and a review are tied to the commit they were dispatched for. A fix counts as in flight until the branch moves. Every new commit needs its own review verdict.
- A stage that cannot be sent from where the conductor runs (a local sandbox for another developer's story) is deferred, and nothing is written.
- A dependency merged in an earlier sprint counts as satisfied. It is recognised by the exact branch name its spec defines.
- When main turns red, it stops dispatching and dispatches only one repair task.
- When a harness runs out of quota, it switches to the fallback in `[roles]`. When all are exhausted, it waits.
- When all gates pass, it enables auto-merge, but only for the tiers listed in `auto_merge_tiers`. The tier comes from the `risk-tier/*` commit status, not from the label; only statuses described as "pull request #N into BRANCH" for this pull request and the default branch count. Auto-merge is enabled only for the commit the decision was made about (`gh pr merge --match-head-commit`): if the branch has moved, GitHub refuses and the next pass decides again. GitHub keeps an auto-merge request on a pull request across later pushes, so on every pass the conductor checks each story pull request that has auto-merge on, and withdraws it when the pull request no longer meets what it was enabled for: not a draft, no human review outstanding, the four mechanical checks and `agent-review` green, and its tier in `auto_merge_tiers`. It also withdraws it when main is red, when the plan is broken, or when the story is not in the sprint, even if the pass returns early. It enables it again when the pull request qualifies. Between a push and the next pass the request is still armed; the limitations say what that window can let through.

### Fuses

- **Kill switch**: set the repository variable `CONDUCTOR_PAUSED` to `true`. It is read live on every pass, through the API, so a conductor that is already running halts within one pass. While paused, the conductor does not dispatch and does not open pull requests. It does one thing: it switches off auto-merge on every open pull request that has it on, because GitHub would otherwise merge such a pull request by itself when its checks turn green. That happens at the next pass, not at the moment you set the variable, and not at all while the Mac is off. For an immediate stop, also run `gh pr merge NUMBER --disable-auto` yourself. A variable that cannot be read is not taken as unset (a malformed `CONDUCTOR_QUOTA` entry is ignored entry by entry): `CONDUCTOR_PAUSED`, `CONDUCTOR_BOT` and `CONDUCTOR_QUOTA` are read first and together, and if any of them cannot be read the pass behaves as paused and still withdraws auto-merge. Dispatching stops as soon as a pass sees the pause or fails to read a variable. Auto-merge that is already switched on has been withdrawn only once a pass could list the pull requests and call GitHub successfully.
- **Limits**, all under `[conductor]`: stories in progress at once (`wip_limit`), pull requests opened per day (`max_prs_per_day`), dispatches of the same stage (`max_attempts`), fix and review rounds (`max_fix_rounds`), triage sessions per story (`max_triage`), the time a stage may take (`stage_timeout_minutes`). Beyond a limit it escalates to you, as a `needs-human` item. It does not retry without end.
- **Parked and waiting stories.** A story parked longer than `max_parked_hours` (72) is escalated, and so is one about to start a session after `max_dispatches_per_story` (15) sessions; both count from the last escalation, so a person who clears a story gives it a fresh allowance. The escalation names the stories waiting for it. A story waiting on a person is mentioned again after `remind_after_hours` (48), once per wait. A story whose session is running is always admitted, so its timeout and retry are looked at and a returning story never runs beside it. Detail: [layer-4-conductor.md](layer-4-conductor.md).
- **A dispatch is recorded before it is sent**, and the record is withdrawn if sending fails. So a dispatch can be duplicated, never lost.

### Actions budget

GitHub measures the allowance in money: the Team plan includes a monthly amount (`monthly_allowance_usd`, an estimate; check GitHub's billing pages). **Each job's time is rounded up to a whole minute**, so a job that runs for 5 seconds also counts as one minute. This rule shapes the design:

- The test suite runs only as many times as necessary: once on head, plus, for a story branch, once on base with the test files overlaid. Both happen in the same job.
- A draft pull request runs only lint. The full gates are left until the implementation is complete.
- An agent pushes only once, at the end of each stage.
- Light jobs that do not run the pull request's code can use a cheaper runner, set with the repository variable `LIGHT_RUNNER`.

`agentctl budget` estimates the month's usage from the Actions job records and reports it in the daily brief. These are estimates and have not been measured against a bill. **Overflow to a self-hosted runner is off** (`overflow_runner = []`): `ci` and `security` execute the pull request's code, so such a runner would have to be dedicated, hold no credentials and be recreated for every job, and the kit does not provide one. When the allowance runs out, CI stops, and nothing merges until the next month begins or until you pay for more. The jobs that judge always stay on GitHub-hosted runners: a machine that pull request code has touched cannot be used to judge that same code.

### Where agents run

| Location | How it is started | Does the Mac need to be on |
|---|---|---|
| Claude Code cloud session | The conductor calls a scheduled task's API trigger (`via = "http"`) | The conductor does, to dispatch and to handle the result |
| Codex cloud | The conductor leaves an `@codex` comment on the pull request or issue (`via = "comment"`) | As above |
| Claude review | The `agent-review` workflow, started by the conductor | As above |
| Local Docker Sandbox, clone mode | The conductor starts it directly (`via = "sbx"`) | Yes, with the conductor running there |

Which cloud path actually works has to be confirmed on your accounts. For one that does not, change it to `via = "sbx"` in `[roles.harness.*]`.

## 9. Turning on auto-merge in stages

A new project's tests are not yet good enough to serve as the basis for merging, so `auto_merge_tiers` is empty by default (**shadow mode**): every gate is computed and reported as usual, but you press merge, and the conductor only notifies you that "this one can be merged". An existing project adopts the conductor this way too.

Observe for a while. Once you have confirmed that the gates' conclusions agree with your own judgement, set `auto_merge_tiers = ["T0"]`, then `["T0", "T1"]`. Each is a pull request that changes `agentdev.toml`, so a human approves it. T2 always needs human approval and can never be listed.

The credibility of auto-merge is capped by the quality of the tests. That is the reason for doing it in stages. [layer-4-conductor.md](layer-4-conductor.md) says what to watch before each step.

## 10. Your day to day

You do four things:

1. Add a line to the roadmap, or say one sentence to the PO.
2. Approve or answer spec pull requests.
3. Approve sprint pull requests.
4. Push release tags.

You look at two places:

- **Director's brief**: one fixed issue, updated every day. It contains sprint progress, things waiting for your decision, items that are stuck, newly merged items and the estimate of the month's Actions usage. Every Monday it has an extra audit section: the number of merges per tier, the number of reverts, the number of escalations, and a few randomly drawn pull requests that were merged without a human, for you to spot-check. The numbers come from GitHub, not from what agents say about themselves.
- **GitHub notifications**: pull requests that need your review and issues that mention you are your decision queue. An escalation mentions the humans; it does not assign the issue.

## 11. Verified and not yet verified

**Nothing has run against real GitHub, Docker Sandboxes, the vendors' cloud services or a Mac.** This section is the single list for the whole kit; each layer's document says which of these its checklist settles.

**Verified during development:**

- The tools' logic has 174 unit tests, which pass: risk tiering, configuration, init, bilingual spec and document checks, traceability, red-green judgement, the conductor's scheduling logic (reconcile), the budget estimate, identity and token profiles, the command-blocking hook, and the installer.
- Red-green was run end to end on a real git repository, split into collect and judge: an empty test was blocked, and passed after being changed into a real test. When the collect step was not run, the judgement was fail rather than pass.
- The step of `spec-verify` that keeps only plain result files was run as written in the workflow, against an artifact that contained symbolic links and stray files.
- The baseline step of `ci` was run against a fake `gh`: seven runs with missing and expired artifacts, a refused listing and a refused download.
- The test flow was run in a scratch repository with the shipped runner: an honest story passes both judges, and vacuous tests, tests without ids and expected failures are rejected.
- The conductor's GitHub interface layer was run against a simulated `gh`: dispatching, leaving a marker before the work is sent and withdrawing it when sending fails, marking a draft ready, a single failed action not affecting the others, and ignoring forged markers and decoy pull requests.
- A hostile module in the working directory (`agentctl.py`, `json.py`, `tomllib.py`) cannot shadow the tools when they are started through the launcher or `python3 -I tools/run.py`.
- `sandbox/sbx.sh` was run against a fake `sbx` for its refusals (secret-looking files in the tree, an existing sandbox name, a bad story id, stage or harness), the network probe's outcomes, the limit on name length and the collision of two repository names. The `sbx` commands behind them were not run.
- The workflows pass actionlint and the shell scripts pass shellcheck.

**Not yet verified:**

*Layer 1, isolation (settled by the checklist in [layer-1-isolation.md](layer-1-isolation.md)).*

- Docker Sandboxes on a real Mac: the `sbx` commands the scripts use, clone mode, that the whole project directory, ignored files included, is what clone mode mounts, whether the proxy injects the App token into `git push` over HTTPS, the home directory path inside the sandbox, and headless runs of each harness.
- Three `sbx` commands the setup depends on: `sbx settings set skills.defaultMode off`, `sbx policy init deny-all` and `sbx policy reset --force`; and network rules for one sandbox (`sbx policy allow network --sandbox NAME HOST`).
- The network probe inside a real sandbox: that `curl` is present there, what a request denied by the sbx proxy looks like from inside, and that `github.com` is reachable. That sbx accepts the longest sandbox name the script produces.
- Minting an agent App token against the real API (`agentctl app-token`), and narrowing it to fewer permissions: a push token with pull requests: read, refused when it tries to open or review a pull request.
- What a cloud session connected to a personal admin account can do on GitHub.
- Whether the sandbox and permission syntax in `.claude/settings.json` matches the current Claude Code version, and that harness deny rules generated by `agentctl harness-settings` take effect.

*Layer 2, GitHub protection (settled by [layer-2-github.md](layer-2-github.md)).*

- The `main-merge` ruleset layering on the `main` ruleset as described in section 6, and `agentctl rulesets 2` and `3` creating the four rulesets on a real repository, and that `integration_id: 15368` names GitHub Actions and accepts the `agent-review` status written by a workflow job.
- Required checks from reusable workflows being reported as "caller job / job" (`ci / ci` and the others), as the rulesets expect.
- Environments with deployment branch rules on a private repository on the Team plan: that a run from any ref other than the default branch is refused the secrets of the `conductor` environment, and that a called reusable workflow can use them.
- The feature boundaries of the Team plan on private repositories: rulesets and auto-merge are available; merge queue and required reviewers for environments are not. The latter is why releases use tag protection.

*Layer 3, CI gates (settled by [layer-3-ci.md](layer-3-ci.md)).*

- The reusable workflows on real GitHub: fetching the kit by SHA from codeload, `secrets: inherit` into a called job, the reviewer reading its prompt from the runner's temporary directory, and `agentctl pins` against real callers.
- The current input parameters of `anthropics/claude-code-action` (`github_token`, the `--allowedTools` argument, that `--tools` restricts the reviewer's tools); the account name of a review bot and its review format for the `REVIEW_BOTS` bridge.
- How `actions/download-artifact` behaves with a hostile archive.
- The commit statuses `risk-tier/*` showing up in `statusCheckRollup`, where the conductor reads the tier.
- How required checks that were skipped on a draft pull request behave after it is marked ready: that fresh full runs appear for the same commit before it becomes mergeable.
- The actual gap between the budget estimate and the GitHub bill, and the actual label of a cheaper runner.

*Layer 4, conductor (settled by [layer-4-conductor.md](layer-4-conductor.md)).*

- The conductor against the real GitHub API, in particular issue dependency links and the reading of check status, and reading repository variables with the Conductor App's token (a refused read would make every pass behave as paused).
- Minting the Conductor App's token from the key on the Mac.
- The interface for triggering a Claude cloud scheduled task by API, and whether starting a task with an `@codex` comment is feasible and what it requires of the commenter's identity.
- The review decision GitHub reports for an approved spec or sprint pull request, the Conductor App enabling auto-merge on it, and the merge that follows. `gh pr merge --match-head-commit` and `--disable-auto` run as the Conductor App. That GitHub keeps an auto-merge request across a push, and the conductor withdrawing it.
- A full loop from one sentence to a merged story, which the spike in layer 4 is meant to prove.

## 12. Known limitations

**Trust and scope**

- The people on the project are trusted. The design defends against agents going out of control and against prompt injection, not against insiders.
- What you paste into the PO chat or an issue enters the vendor's context and is outside the isolation.
- Docker Sandboxes is at version 0.x. Its commands may change.
- The capacity for continuous operation is limited by subscription quota. When quota runs out, work slows down. It does not fail.
- Cloud triggering depends on features that both vendors are still evolving. The fallback is a local sandbox, but it needs the Mac to be on with the conductor running.
- While you are away, things waiting for your decision accumulate. This is the only pace in director mode that is set by you.

**Layer 1, isolation**

- In clone mode the agent's work exists only inside the VM until it pushes. A stage that ends without pushing leaves nothing behind except its log.
- Clone mode shows the agent the whole project directory, ignored files included. The check for secrets goes by file name. A secret under another name is not found, and every sandbox could read it.
- The subscription login state inside the VM could in theory be stolen by malicious repository content. The egress allowlist reduces this risk but does not remove it.
- The network probe is a spot check of three hosts, made when a sandbox is created. It does not prove that the effective allowlist equals the project's lists, and it cannot tell an origin's own 403 or 5xx answer from a policy denial.
- Per-stage privileges exist only on the sandbox path. In a cloud session every stage acts as the account you connected.
- Cloud sessions act as the personal account you connect. Until the layer 1 checklist has been run, assume a cloud agent can do on GitHub whatever that account can, limited only by rulesets that have no bypass. The release tag ruleset lets admins bypass, so it is one of the things to test. The account is also a listed human, so the conductor would believe a marker comment written from a cloud session.
- The Conductor App's private key is on the Mac that runs the conductor. It is kept outside the repository, where no sandbox can see it, but it is on the host.

**Layer 2, GitHub protection**

- The review token can write to pull requests. It cannot push or merge, but nothing in the token stops it from opening or editing one.
- The conductor's login is accepted as a marker author with and without its `[bot]` suffix. A person whose login equals the Conductor App's slug would therefore be believed as a marker author. That person would also have to be a collaborator to comment at all.
- A named developer's secret is used for that developer's stories, but nothing checks that the value stored under `NAME_<LOGIN>` really is that person's credential.

**Layer 3, CI gates**

- A pull request that edits a caller workflow chooses which kit version judges it, because GitHub runs a pull request's own workflow files. Only the code-owner approval required by layer 2 stops it. A mitigation to evaluate is the ruleset rule "require workflows to pass", which runs a workflow from a fixed repository and ref (not verified on the Team plan).
- The reviewer can be talked into a wrong verdict by the text it reviews. See "The strength of `agent-review`" in section 6.
- Test results are produced by the pull request's code and can be forged. See section 6.
- Red-green shows that the story's tests do not pass on main. A test written to behave differently on main than on the branch can still satisfy it. Only the fidelity audit can catch that.
- There is no hard guarantee that the two language versions of a story mean the same thing. If the translation you approved and the English the agents implement differ, only the review agent and you yourself can catch it.
- Which files count as a dependency change is a list in `[risk.t2] dependency_manifests`. A manifest or lock file of a stack that the list does not name is not T2 until the project adds it. The same goes for `high_risk` and the project's own layout.
- For a review started by a comment or run in a local sandbox, staying on the named commit is an instruction in the prompt, not a check.
- Actions usage is an estimate. It may differ from the bill, so the warning in the brief may come too early or too late.
- Overflow is off. When the Actions allowance is exhausted, CI stops and nothing merges until the next month begins or until you pay for more.

**Layer 4, conductor**

- It runs on one Mac. A second conductor for the same project on another Mac is not supported, and nothing detects it. When the Mac sleeps, nothing advances.
- Pausing withdraws auto-merge only when a conductor next runs. Until then GitHub still merges a pull request that has auto-merge on as soon as its checks turn green. For an immediate stop, also disable it by hand: `gh pr merge NUMBER --disable-auto`.
- Withdrawing auto-merge needs a pass that can list the pull requests and call GitHub. If GitHub's API is failing altogether, nothing is withdrawn, and the manual command is the only way.
- GitHub keeps an auto-merge request across later pushes. The conductor withdraws it at its next pass when the pull request no longer qualifies, but between the push and that pass the request is still armed. GitHub still requires all five required checks on the new commit, and `risk-gate` fails a T2 commit until a human approves. So what the window can let through is a commit of a tier above the enabled ones but below T2 (T1 while only T0 is enabled) that also passes `ci`, `spec-verify` and `agent-review` before the conductor runs.
- `touches` is a prediction and will miss things. The cost is merge conflicts and rework, corrected afterwards by triage. It does not lead to wrong code being merged.
- A dispatch can be duplicated, never lost.
