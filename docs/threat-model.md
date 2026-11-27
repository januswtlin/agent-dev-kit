# Threat model

*繁體中文：[threat-model-zh-TW.md](threat-model-zh-TW.md). The English version governs if the two differ.*

Each row is a class of incident that has really happened or can be expected, mapped to the controls that stop it. Controls are of two kinds. **Hard** controls are enforced by the environment or by GitHub, and the agent cannot get round them. **Soft** controls can be bypassed and serve only as a second layer.

## Assets

| Asset | Worst case | Recoverable? |
|---|---|---|
| Private data on the Mac | Read and taken into a vendor's context, or sent outside | No |
| Files on the Mac outside the working directory | Deleted or overwritten | From backup |
| Temporarily valid cloud CLI tokens | Used to operate on cloud resources while they are valid | Depends on the operation |
| The repo's history and main | Rewritten, or faulty code merged in | Yes (git), but at a high cost |
| The guardrails themselves (workflows, policy, specs) | Once weakened, the other lines of defence fail | Yes, provided someone notices |
| The subscription accounts' login state | Stolen | Can be revoked |
| Future production and databases | Deleted or leaked | No |

## Threats and controls

| # | Threat | Hard controls | Soft controls |
|---|---|---|---|
| 1 | The agent reads private files under home | The VM mounts only the project directory, read-only; cloud sessions are not on your machine | `denyRead` in `.claude/settings.json`; guard hook |
| 2 | The agent deletes files outside the working directory by mistake (`rm -rf ~/`) | As above: those files are not in the VM | Guard hook; the project is not kept in a directory synced by iCloud; backups |
| 3 | The agent uses cloud credentials on the machine | Directories such as `~/.aws` do not exist in the VM | Deny rules block the cloud CLIs |
| 4 | Prompt injection (repo content, issues, web pages, package descriptions) induces the agent to send data out | Egress allowlist on top of a deny-all network preset; the VM holds no secrets worth sending out, apart from the subscription login state and, in the Lima fallback, the agent token. This assumes the project directory holds none (#32) | AGENTS.md rule 7 |
| 5 | The agent installs a malicious or non-existent package (slopsquatting, compromised packages) | Dependency changes, lock files included, are always T2 and need human approval to merge; installation happens inside the VM; the egress allowlist limits calls back out | AGENTS.md rule 5 |
| 6 | The agent pushes straight to main, force-pushes or deletes branches | Ruleset `main`: main can only be changed through a PR. Ruleset `main-merge`: only admins and the Conductor App may update main (**To verify**). The agent acts as a GitHub App with only the permissions it was granted and no bypass | Guard hook; deny rules |
| 7 | The agent modifies CI to make the checks pass | The agent token has no Workflows permission; `.github/` and the scanner configuration (`.gitleaks.toml`, `.semgrepignore` and the like) are in CODEOWNERS; the judging checks are run by the base branch's copy of the tools, with its policy, started as `python3 -I`; only PRs into main are judged | AGENTS.md rule 3 |
| 8 | The agent weakens the risk rules, prompts or tools | `policy/`, `prompts/` and `tools/` are in CODEOWNERS and are T2 | As above |
| 9 | The agent claims to have written tests but has not, or has written empty tests | `spec-verify`: traceability (based on execution results) and red-green | The review agent's faithfulness audit |
| 10 | The agent modifies or deletes tests to suit the implementation | Specs are protected by CODEOWNERS; a TC that has passed may not disappear, even when its spec is deleted in the same change, unless a human lists it in `docs/specs/retired.toml`; red-green, in which a test skipped on base or a base run with no report does not count as red | The review agent checks, one by one, every test change made after the tests stage |
| 11 | The agent quietly changes the requirements | `docs/specs/` is in CODEOWNERS; a new push invalidates earlier approvals | |
| 12 | The agent approves or merges its own PR | The agent's GitHub App cannot be a code owner; PRs are opened by the Conductor App; the App cannot approve; the token that pushes cannot merge (#34) | Deny rules block `gh pr merge` |
| 13 | The agent forges the `agent-review` result | The agent token has no commit status permission; the status is written by a `publish` job that never sees the PR's files; the verdict is written outside both checkouts and counts only if the review step succeeded, otherwise the status is failure; the reviewer runs in a checkout of the default branch with a read-only token, so its settings and hooks do not come from the PR; required checks must be reported by GitHub Actions (**To verify**) | None against the reviewer being talked into a wrong verdict by the text it reviews. See the explanation in guideline 4: this is the weakest link, and the hard guarantees do not depend on it |
| 14 | The agent deploys or creates a release on its own | Tag ruleset: only an admin can create `v*`; the release job requires `ci`, `security` and `spec-verify` to be present and green on the tagged commit; the cloud trusts only OIDC that comes from a tag; there are no long-lived keys | |
| 15 | The agent deletes the production database or its backups | The agent and CI have no production credentials; the deploy role has no permission to delete backups; migrations are T2 | |
| 16 | A secret is committed | gitleaks in the `security` check | AGENTS.md rule 6 |
| 17 | The conductor runs away: endless retries, opening PRs in bulk | Daily PR limit, limits on retries and fix rounds, WIP limit; the kill switch, read live on every pass by the Actions job and by the local conductor; a dispatch is recorded before it is sent, so an interrupted run does not send it twice | Daily brief |
| 18 | The agent drifts from its instructions after running for a long time | There are no long sessions: each stage is a fresh context, and the state lives on GitHub | |
| 19 | Behaviour changes after a model upgrade | Scheduling is deterministic code; the gates are mechanical checks | Weekly audit sampling |
| 20 | Computer use, browser extensions or personal-data connectors touch private data | None. These paths do not go through the VM | Rule: do not turn them on. See guideline 3 |
| 21 | The agent writes a fake test results file directly and fools `spec-verify` | None. The test results are produced by the PR's code in the first place | `Makefile` is protected by CODEOWNERS; the review agent; weekly spot checks |
| 22 | The two versions of a bilingual story differ in meaning: the Chinese you approved and the English the agent implements do not match | Matching structure and changing both together are enforced by `spec-lint` | The PO's own comparison; a review agent from the other vendor compares them item by item |
| 23 | A PR's code leaves something behind on the self-hosted runner that affects later jobs | Overflow is off by default (`overflow_runner = []`), so `ci` and `security` run on GitHub-hosted runners; the jobs that pass judgement never move, whatever is configured | None once you configure an overflow runner: nothing checks that it is rebuilt for every job. See #37 |
| 24 | A maintenance session is induced to weaken the guardrails | Changes to guardrail paths always need human approval to merge | AGENTS.md rule 3: only something a human asks for directly in the session counts as a maintenance request |
| 25 | The Actions allowance is exhausted and the gates cannot run | When the allowance runs out, PRs cannot be merged; nothing is merged without the gates | Usage estimate in the daily brief. Overflow is off by default, so nothing relieves it automatically: merging stops until the next month or until you pay for more |
| 26 | The agent plants a git hook or edits `.git/config` in a mounted repository, and it runs on the Mac the next time you use git there | Clone mode: the repository is mounted read-only and the agent works on a private clone | `agentctl doctor --inside` warns when the workspace is writable |
| 27 | The agent uses your forwarded SSH agent to push as you, bypassing its own identity | `sandbox/sbx.sh setup` turns SSH agent forwarding off; outbound SSH is not on the allowlist | `agentctl doctor --inside` fails when an SSH agent with keys is reachable |
| 28 | The agent's GitHub credential is stolen from inside the sandbox | With sbx neither the key nor the token is in the VM; the proxy on the host injects a one-hour token | In the Lima fallback the key is in the VM; revoke it in the App's settings |
| 29 | An agent acts outside its role: a reviewer or triage agent changes code, or pulls in packages | Its token is minted without push permission and its sandbox cannot reach the package registries (`tools/agentctl/profiles.py`); a sandbox is never reused, so it cannot inherit another stage's network rules. Docker Sandboxes path only | The stage prompt; the harness deny rules |
| 30 | An agent widens its own privileges by editing the profiles or the sandbox scripts on its branch | Sandboxes are set up by a copy of the tooling pinned outside the repo and by the scripts on the default branch | Those paths are guardrails: CODEOWNERS and T2. `sandbox/sbx.sh` refuses to run from a checkout whose host scripts differ from the default branch (#31) |
| 31 | Code from a PR or from an agent's branch runs on the Mac or in a judging job: a file named like a module (`agentctl.py`, `json.py`) in the current directory, or the branch's version of a host script | `bin/agentctl`, the CI judges and the token helpers start the tooling as `python3 -I tools/run.py`, which keeps the current directory and `PYTHONPATH` off the import path; the judges run the base branch's copy; sandboxes are set up by a copy pinned outside the repo; the local conductor starts sandboxes with the scripts of a fresh checkout of `origin/main`; story id, stage and harness are validated before they reach a path, a sandbox name or a command | `sandbox/sbx.sh` and `agentctl conductor here` refuse to run when `sandbox/`, `tools/`, `bin/` or `policy/` differ from the default branch. This guards against the accident of running them from an agent's branch. The check is part of those scripts, so it does not stop a checkout that is already hostile. Rule: run host scripts from a clean checkout of the default branch |
| 32 | A secret in the project directory is read by an agent: clone mode mounts the whole directory read-only, ignored files included | None for a file you put there yourself. The pipeline's own credentials are read from outside the repo: `~/.config/agent-dev/<owner>-<repo>/conductor.env` and `~/.config/agent-app/`. The shared skills store is turned off (**To verify**) | `sandbox/sbx.sh` refuses to start while ignored files look like secrets (`.env*`, `*.pem`, `*.key` and similar). It goes by file name and can be overridden. Rule: keep nothing secret in the project directory |
| 33 | A workflow that holds credentials runs in the version of itself found on a branch | Credentials are secrets of the `conductor` environment, which only the default branch may use, so a run from any other ref gets none (**To verify**); no workflow that holds them is triggered by `pull_request` or by a push to a branch: `notify.yml` has no permissions and no secrets, and the conductor reacts to it through `workflow_run`; the Claude reviewer runs only when dispatched from the default branch; the agent token has no Workflows permission | The environment and its branch rule are created by hand during setup. A secret created as a repository secret instead is not protected this way |
| 34 | An agent opens, retargets or merges a PR with its own token | The token that pushes has pull requests: read (`tools/agentctl/profiles.py`); the `main-merge` ruleset lets only admins and the Conductor App update main; the `main` ruleset has no bypass (**To verify**: narrowing the token, and the layering of the two rulesets). Docker Sandboxes path only | Deny rules block `gh pr create`, `gh pr review` and `gh pr merge`. Not covered: the review token can write to PRs, although it cannot push or merge; a cloud session acts as the account you connected |
| 35 | An agent forges a conductor marker comment to fake a dispatch, cancel one or silence a notification | Markers are believed only when written by the conductor's own login or by a human listed in `policy/roles.toml`; `roles.toml` is read from the default branch | None. Not covered: a cloud session acts as your account, which is a listed human, so a marker it writes is believed |
| 36 | A stale or wrong PR is taken for the story's PR: a closed one, one into another base, one from a fork | The conductor picks only the open PR, else the merged one, from this repository into the default branch; a fix, a conflict resolution and a review are tied to the commit they were dispatched for, and every new commit needs its own verdict; the review workflow refuses a PR that is not open, same-repository and into the default branch; `ci`, `security` and `risk-gate` run only for PRs into main | |
| 37 | PR code runs on a shared, long-lived runner that holds logins: it changes the firewall, reads the logins or persists into later jobs | Overflow is off by default, so `ci` and `security` do not run on the Lima VM's runner; that runner is not part of the supported setup path | None once you set `overflow_runner`: the policy file says the runner must be dedicated, credential-free and recreated for every job, and nothing enforces it |

## Reference incidents

The types of public incident consulted during design, used to check the table above for gaps:

- An agent deleted a production database after being explicitly asked to stop making changes (July 2025, Replit and SaaStr). Corresponds to #14, #15.
- An agent deleted a database and its backups through a cloud platform's API (reports from April 2026). Corresponds to #3, #15.
- A compromised npm package instructed the local AI CLIs to search for secrets and send them out, in the mode that skips permission prompts (August 2025, the Nx incident). Corresponds to #1, #4, #5.
- A model produced the name of a package that did not exist, and the name was then registered as a malicious package. Corresponds to #5.

The details of the last three items come from secondary reports and were not checked one by one against the primary sources.

## Out of scope

- Malicious insiders. The two developers are trusted.
- Data handling on the vendors' side. What is sent to the models is governed by each vendor's terms.
- A compromise of GitHub itself.
