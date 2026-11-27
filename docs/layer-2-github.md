# Layer 2: GitHub protection

*繁體中文：[layer-2-github-zh-TW.md](layer-2-github-zh-TW.md). The English version governs if the two differ.*

This layer makes GitHub itself refuse what an agent, or a mistake, should not be able to do: change `main` without a pull request, merge its own work, approve its own work, move a release tag, or read the pipeline's secrets from a branch. It gives you three rulesets (`agentctl rulesets 2`) and, once layer 3 exists, a fourth that requires its checks (`agentctl rulesets 3`), CODEOWNERS generated from `agentdev.toml` (`agentctl codeowners`), the `conductor` environment, the Conductor GitHub App, and a few repository settings. It does not run any check: the checks the `main-checks` ruleset requires come from layer 3. It does not start agents: that is layer 4. It pairs with [layer-1-isolation.md](layer-1-isolation.md), whose agent tokens are what these rules are written against. The design is in [guideline.md](guideline.md); the threats are in [threat-model.md](threat-model.md); adopting the kit is in [adopting.md](adopting.md).

Done once per project, by someone who administers the repository.

## 1. What this layer protects

| Threat | Control |
|---|---|
| A push to `main`, a force-push, a deleted `main` | `main` ruleset: no deletion, no non-fast-forward, changes only through a pull request. No bypass for anyone. |
| A pull request merged without a human where one is needed | `main` ruleset: code owner review required. CODEOWNERS (generated from `[risk.t2]`) names a director for the guardrails, specs, sprints, dependency manifests and high-risk code. A new push dismisses stale approvals. |
| An agent merges its own green pull request | `main-merge` ruleset: only repository admins and the Conductor App may update the default branch. The agent token can push branches and, by GitHub's rules, call the merge endpoint, so this ruleset is what refuses it. |
| Merging before the gates pass | `main-checks` ruleset (applied with layer 3): the five required checks, strict (the branch must be up to date). The checks come from layer 3. |
| A tag created, moved or deleted by an agent: a `v*` release, or a tag named like a branch (`origin/main`) that a short ref name would resolve to | `tags` ruleset: only repository admins touch any tag. |
| A branch or a cloud session reads the pipeline's secrets | The `conductor` environment holds them and allows the default branch only. |
| An agent approves its own pull request | The Conductor App opens pull requests, so no human is the author; agents' tokens cannot review as a code owner. A person cannot approve a pull request they opened (D10). |
| Squash-merge history, stale branches | Repository settings: squash only, auto-delete head branches. |

## 2. Before you start

- A GitHub organization on a plan that enforces rulesets on private repositories (Team or above), with one seat per person. Agents and the Conductor App are GitHub Apps and take no seat. On a plan that does not enforce them, the rulesets are created but protect nothing: not verified which plan names apply today, so check GitHub's plan page.
- `gh` logged in as a repository admin (`gh variable get --help` must print usage text; older releases lack it), `git` able to push over HTTPS (`gh auth setup-git`), Python 3.11 or newer, and the kit installed on this Mac ([layer-1-isolation.md](layer-1-isolation.md), section 2).
- The project's repository exists, with `agentdev.toml` (at least `[kit]`, `[roles] directors` and `humans`) on `main`. `agentctl init DIRECTOR_LOGIN [OTHER_LOGIN ...]` creates it and CODEOWNERS ([adopting.md](adopting.md)).
- Layer 2 stands alone. `agentctl rulesets 2` applies `main`, `main-merge` and `tags`, none of which requires a check. The required checks are a separate ruleset, `main-checks`, applied later by `agentctl rulesets 3` (section 3.4) once layer 3's caller workflows are on `main` and have run. Applying it earlier would block every merge, because a check that never reports never passes and the ruleset has no bypass.
- While `main` still holds the placeholder `DIRECTOR_LOGIN`, nobody is a code owner and nobody could approve a pull request that fixes it. Put real logins in `agentdev.toml` and CODEOWNERS before applying the rulesets.
- The project's default branch is known to your clone, because the launcher reads `agentdev.toml` from it. This must print `origin/main`; if not, run `git remote set-head origin -a`:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD
```

## 3. Setup

### 3.1 CODEOWNERS

CODEOWNERS is generated, not written. `agentctl codeowners` prints it from `[risk.t2]` and `[roles] directors` in `agentdev.toml`; the owners are the directors, and only people are owners (an App never is). Write it, commit it, and let layer 3's `ci` fail when it drifts:

```bash
agentctl codeowners > .github/CODEOWNERS
```

```bash
agentctl codeowners --check
```

The file covers four groups: `human_gated` (specs, sprints, product documents), `guardrails` (`.github/**`, `agentdev.toml`, agent settings, `AGENTS.md`, scanner configuration), `dependency_manifests` and `high_risk`. `[roles] directors` must not be empty. Set `high_risk` in `agentdev.toml` to the project's real layout, then regenerate.

### 3.2 Conductor GitHub App

The conductor opens and merges pull requests, comments on and labels issues, dispatches workflows, reads checks and variables, and writes the Actions-budget variables. Create an App under the organization's Settings > Developer settings > GitHub Apps:

- Repository permissions: Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Actions: Read and write; Variables: Read and write; Checks: Read; Commit statuses: Read; Metadata: Read.
- Subscribe to no webhooks, and untick Active.
- Generate a private key and install the App on this repository only. Note the App's numeric ID. Keep the key file outside the project directory (a sandbox reads every file there, ignored ones included).

The key is used in two places. On the Mac that runs the conductor it is a file named in `conductor.env` ([layer-4-conductor.md](layer-4-conductor.md)). In GitHub it is the environment secret below, read only by the daily brief job.

### 3.3 The `conductor` environment

1. In Settings > Environments, create an environment named exactly `conductor`.
2. Under Deployment branches and tags, choose Selected branches and tags and add one rule that allows the default branch (`main`) only.
3. Add the environment secret `CONDUCTOR_APP_PRIVATE_KEY` with the key's full contents. Or:

```bash
gh secret set CONDUCTOR_APP_PRIVATE_KEY --env conductor < PATH_TO_PRIVATE_KEY.pem
```

Why an environment and not a repository secret: the jobs that hold credentials declare `environment: conductor`. A run started from any other ref, a manual dispatch of a branch included, is refused the secrets by GitHub. A repository secret has no such rule.

| Type | Name | Where | Value | Needed by |
|---|---|---|---|---|
| Environment secret | `CONDUCTOR_APP_PRIVATE_KEY` | Environment `conductor` | The Conductor App's private key | The daily brief (layer 3's caller, `agentdev-brief.yml`) |
| Environment secret | `CLAUDE_CODE_OAUTH_TOKEN`, or `CLAUDE_CODE_OAUTH_TOKEN_LOGIN` for a developer's own | Environment `conductor` | From `claude setup-token`; see layer 3 | The Claude review |
| Repository variable | `CONDUCTOR_APP_ID` | Settings > Secrets and variables > Actions > Variables | The App's numeric ID | Skips the brief while empty; set it last (section 3.5) |
| Repository variable | `CONDUCTOR_PAUSED` | Same | `true` to pause, `false` or unset otherwise | The kill switch ([layer-4-conductor.md](layer-4-conductor.md)) |

Other variables (`REVIEW_BOTS`, `CONDUCTOR_QUOTA`, `LIGHT_RUNNER`, `CI_RUNNER`, `ACTIONS_USAGE`, `CONDUCTOR_BOT`) belong to layers 3 and 4 and are described there. Dispatch credentials are not GitHub secrets any more: they sit in `conductor.env` on the Mac.

### 3.4 Rulesets

Run as a repository admin, with the Conductor App's numeric ID (it becomes the bypass actor of `main-merge`):

```bash
CONDUCTOR_APP_ID=APP_ID agentctl rulesets 2
```

The script refuses to run without `CONDUCTOR_APP_ID`, and it needs `gh`. It creates or updates, by name, the three layer 2 files of the kit's `templates/rulesets/`:

- `main`: no deletion, no force-push, changes only through a pull request with code owner review (zero required approving reviews otherwise; approvals dismissed on push; squash only). It has no required checks of its own. No bypass for anyone.
- `main-merge`: only repository admins (role 5) and the Conductor App may update the default branch. They still satisfy everything in `main`.
- `tags`: only repository admins may create, move or delete any tag.

Confirm:

```bash
gh api repos/OWNER/REPO/rulesets --jq '.[].name'
```

It must list `main`, `main-merge` and `tags`. When layer 3's caller workflows are on `main` and have run once, apply the checks ruleset (`main-checks`: the five required checks `ci / ci`, `ci / spec-verify`, `security / security`, `risk-gate / risk-gate` and `agent-review`, strict, no bypass):

```bash
agentctl rulesets 3
```

To change a ruleset, change the kit's template, not the project: the templates are part of the kit version.

### 3.5 Repository settings

In Settings > General > Pull Requests: turn on Allow auto-merge, allow squash merging only, and turn on Automatically delete head branches. In the organization's Settings > Actions > General, confirm **Allow GitHub Actions to create and approve pull requests** is off. Everyone on the project is a repository admin; agents and the conductor are Apps.

Allow auto-merge is not optional: once a code owner has approved a spec or sprint pull request, the conductor enables auto-merge on it at its next pass, whatever `auto_merge_tiers` says, because the decision was a person's. It never does so for a `chore/` pull request.

Last, if you run the conductor and the daily brief, set the variable that switches the brief on. Do this only after sections 3.3 and 3.4:

```bash
gh variable set CONDUCTOR_APP_ID --body APP_ID
```

### 3.6 Release tags

`tags` makes every tag something only an admin can create, so a `v*` tag is a release approval that only an admin can give, and no agent can push a tag named like a branch. The project-owned `release.yml` (copied by `agentctl init`) runs on such a tag and is a starting point: its provider block is yours to fill in, and its check names are the kit's required checks. The cloud side should trust only `repo:OWNER/REPO:ref:refs/tags/v*`, so no branch build and no agent session obtains production access. `release.yml` is not a reusable kit workflow; changing it is a T2 change.

## 4. Checklist

Run it once when setup is complete, and again when you change a ruleset, CODEOWNERS or the kit version. Use test pull requests that target `main`. **Most items attempt something that must fail or be refused.** If one succeeds, a line of defence is not working. Items that expect success, in whole or in part: C17 (its last step), D23 and D25. Note the message you actually saw in the Result column. None of these has been run against real GitHub, so a result that differs may mean this checklist is wrong; write that back too.

Items marked "job" use an agent token as in [layer-1-isolation.md](layer-1-isolation.md), section 4: `agentctl sandbox job claude sprint STAGE "Run these commands ... and print their output: COMMANDS"`, with stage `impl` for the push token and `review` for the review token, then read the log. Judge by what GitHub shows.

### C. Agent tokens against the rulesets

| # | Attempt | Expected | Result |
|---|---|---|---|
| C1 | Job (`impl`): `git push origin HEAD:main` | Rejected by the ruleset | |
| C2 | Job (`impl`): `git push --force origin redteam/c2` to a branch that already exists, then `git push --force origin HEAD:main` | The first depends on the rulesets (they cover the default branch only); `main` is not affected: the second is rejected | |
| C4 | Job (`impl`): `git tag v9.9.9 && git push origin v9.9.9` | Rejected by the `tags` ruleset | |
| C20 | Job (`impl`): `git tag origin/main && git push origin refs/tags/origin/main` (a tag named like the default branch) | Rejected by the `tags` ruleset. If it ever got through: `agentctl` on the Mac and `risk-gate` still read the real default branch, because they use full ref names and the base commit id | |
| C6 | Job (`review`): `gh pr review N --approve` on a spec pull request. Repeat from an `impl` job | From `impl`: 403, the token cannot write to pull requests. From `review`: the approval is not counted as a code owner approval, and the pull request still cannot be merged | |
| C7 | Job (`impl`) and job (`review`): `gh pr merge N --squash` on a pull request whose checks have not passed | Rejected both times. This shows only that a red pull request does not merge. Who may merge a green one is C17(b) | |
| C17 | (b) Take a pull request into `main` that is otherwise mergeable: every required check green, approved if it needs approval. A harmless documentation change will do. Job (`impl`): `gh api --method PUT repos/OWNER/REPO/pulls/N/merge -f merge_method=squash`. Then merge the same pull request as an authorised actor: an admin, or the Conductor App. Part (a) is in layer 1 | The agent's attempt is refused, and what refuses it is the `main-merge` ruleset, not the token: GitHub's merge endpoint needs only contents: write, which the `write` token has. The authorised actor's merge of the same pull request SUCCEEDS, which shows nothing else was blocking it. A pull request with red checks is refused by other rules and proves nothing | |

### D. Approval, CODEOWNERS and merge rules

| # | Attempt | Expected | Result |
|---|---|---|---|
| D9 | After you approve a spec pull request, push another commit | Your approval is dismissed; the pull request does not merge until you approve the new commit | |
| D10 | Open a pull request yourself that changes a spec, then try to approve it | GitHub does not allow it. This is why pull requests must be opened by the Conductor App | |
| D23 | Marking a draft ready. Take a story pull request that is still a draft, with `security` and `spec-verify` shown as skipped on its head commit. Mark it ready without pushing (`gh pr ready N`, or let the conductor do it) | Fresh full runs of `ci`, `security` and `spec-verify` appear for that same commit, and the pull request is not mergeable until they finish green. This one should SUCCEED. If it is mergeable on the skipped results before the fresh runs report, that is a failure | |
| D24 | Edit `.github/CODEOWNERS` by hand (add a line) and push the branch with a pull request. Separately, change `[risk.t2]` in `agentdev.toml` without regenerating | `agentctl codeowners --check` (run by `ci` in layer 3) fails, naming the file. A change to `.github/**` or `agentdev.toml` needs a code owner's approval to merge | |
| D25 | As an admin, try `git push origin HEAD:main` from a clone, then merge a green, approved pull request through the web interface | The direct push is rejected: `main` has no bypass, admins included. The merge through a pull request SUCCEEDS. This one should SUCCEED in part | |
| D26 | As a non-admin collaborator (or with a token that is not an admin's), push `v9.9.9`. As an admin, create and delete a throwaway `v0.0.0-redteam` tag | The non-admin push is rejected. The admin's tag is created and deleted (this shows the ruleset does not lock admins out). Delete the tag afterwards | |
| D27 | Dispatch the daily brief from a branch that is not the default: `gh workflow run agentdev-brief.yml --ref SOME_BRANCH` | The `brief` job is refused the `conductor` environment, or gets an empty `CONDUCTOR_APP_PRIVATE_KEY` and fails at the App token step. No token is minted. If the job reaches the "Actions budget" step, the environment's branch rule is not working | |
| D28 | Read Settings > Environments > conductor | Exactly one deployment rule: the default branch. Do not remove it to test | |
| D29 | A pull request whose base is not `main` (for example `story/000-example` into a branch `test/base`) | None of the required checks apply to it and `main`'s rules do not either; it cannot be merged into `main`. Retarget it to `main` and push: every required check then runs against `main` | |
| D30 | Settings: try to merge a pull request with a merge commit or rebase from the interface | Only squash is offered | |

## 5. Not yet verified

Nothing in this layer has run against real GitHub. Specifically:

- That the current rulesets API accepts the fields in `templates/rulesets/*.json`. If it reports unknown fields, adjust the template according to the error and write the result back.
- That `main` and `main-merge` layer as described (the bypass in `main-merge` does not weaken `main`), and that the Conductor App's ID is the right `actor_id` for an Integration bypass.
- That `integration_id: 15368` in `main.json` is the GitHub Actions app that produces the required checks, and that reusable-workflow checks are reported as `ci / ci`, `ci / spec-verify`, `security / security` and `risk-gate / risk-gate`, with `agent-review` as a plain commit status.
- That environments with deployment branch rules are available for private repositories on the Team plan, the exact names of those settings, and that GitHub does not create the environment without a branch rule if a workflow names it first.
- That the `conductor` environment's secrets are available to a job in a called reusable workflow.
- That the approval of the `review` token is not counted as a code owner approval.
- That auto-merge can be enabled by the Conductor App on a pull request of a repository with these rulesets.

## 6. Known limitations

- Rulesets need Team or above on private repositories. On a lower plan they do not protect anything.
- Until `agentctl rulesets 3` is applied, `main` requires no checks: layer 2 alone gives you pull requests, code owner review and the merge restriction, not the gates.
- `main` requires zero approving reviews beyond the code owner rule. A pull request that touches no owned path needs no human review; it is T0 or T1 and the gates and the conductor's settings decide whether it merges on its own.
- The Conductor App can update `main` through the `main-merge` bypass. Its key sits on the Mac that runs the conductor and in the `conductor` environment; anyone who can read either can merge as the conductor, still subject to `main`.
- Repository admins can change rulesets. Everyone on the project is an admin by design here; the rulesets guard against agents and accidents, not against a malicious admin.
- The auto-merge flag may stay armed on a pull request that is no longer eligible if the conductor's planner returns early; the `main` ruleset is the backstop.
- Cloud sessions are connected with a person's account (layer 1), so their rights are that person's; E1 to E4 in layer 1 check what that allows.
