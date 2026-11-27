# Hand-off: from template to kit, and adopting it in formosan-serow

Written 2026-11-27 at the end of a long session, for the session that continues the work. Delete this file when the restructure is done. It is a snapshot, not a process document.

The director is Janus (`januswtlin`). Reply in Traditional Chinese (Taiwan usage) when they write in it; code, identifiers and repository files in English. Plain paragraphs, no em dashes, direct disagreement where warranted.

## 1. Where things stand

- Repository: `januswtlin/agent-dev-template`, branch `claude/initial-template`, pull request #1 into `main` (`main` holds only `.gitignore`). Head when this was written: `553cfc2` plus this file.
- What it is today: a project **template**. `tools/`, `sandbox/`, `bin/`, `policy/`, `prompts/`, `.github/` and the documents are meant to be copied into each new project.
- Checks that pass: `make lint`, `make test` (140 unit tests), actionlint, ShellCheck.
- **Nothing has run against real GitHub, Docker Sandboxes, the vendors' cloud services or a Mac.** Everything was exercised against fakes (`sbx`, `gh`) and scratch git repositories. `docs/guideline.md` section 9 lists what was and was not verified; section 10 lists known limitations.
- Four independent reviews were done (by another vendor's model, at `16e6627`, `750986f`, `960e2e0`, `553cfc2`). The first three are fixed. **The fourth is not** (section 5 below).

## 2. Decisions the director made at the end of the session

These override the template framing in the current documents.

1. **This becomes a guideline plus tools ("kit"), not a template.** New and existing projects both adopt it. Tools are not copied into projects.
2. **Four layers, each adoptable on its own**, each with its own setup document and checklist:
   1. isolation: Docker Sandboxes in clone mode, a GitHub App per developer for agents, host hygiene;
   2. GitHub protection: rulesets, CODEOWNERS, the `conductor` environment;
   3. CI gates: `ci`, `security`, `spec-verify`, `risk-gate`, `agent-review`;
   4. the conductor.
3. **All four layers are in scope now**, for the kit and for formosan-serow. Not only layers 1 and 2.
4. **The kit will be open source: one public repository** holding the guideline, the tools and the reusable workflows. A public repository's reusable workflows can be called from private repositories in any organization, so no second copy under `Team-JJR` is needed. Projects pin a **commit SHA**, not a tag. Whether it stays under `januswtlin` or moves is the director's call; not decided.
5. **Before publishing: start from a clean initial commit.** The current history carries session links in every commit message. Check the content for anything specific to the director's own environment.
6. **Stories are files.** In formosan-serow, closed issues stay as they are; open story issues are converted to spec files; the roadmap issue becomes a file. Runtime state (stage labels, dispatch markers, triage notes) stays on one GitHub issue per story that the conductor creates.
7. Pull request #1 is not to be merged as it is. Restructure on the same branch.
8. The director asked for a **migration guide**. Proposed and not objected to: a generic "adopting in an existing project" guide lives in the kit; the plan specific to formosan-serow lives in that repository and is deleted when the migration is done.
9. The director will switch to a lighter model and a fresh session to save tokens. Delegate documents, translation and mechanical conversion to a cheaper model. Keep the strongest available model, or at least a review by it, for `sandbox/sbx.sh`, workflow trust boundaries, and the conductor's scheduling and lease code: most defects found in review were in those, and several were introduced by fixes.

## 3. Proposed shape of the kit (agreed in outline, not yet built)

- **Tools installed once per Mac**, from a pinned version of the kit, outside any project directory. This removes a whole class of findings: today the code that runs on the host sits in the same directory an agent can change, which is why the "trusted checkout" check, the pinned copy and the "never run host scripts from an agent's branch" rule exist. `sandbox/sbx.sh` already takes the project from `AGENT_PROJECT_DIR`, and already pins `tools/agentctl` under `~/.local/share/agent-dev/<owner>-<repo>/`.
- **One configuration file in the project**, working name `agentdev.toml`, instead of assumptions in code:

| Setting | Default for a new project | formosan-serow |
|---|---|---|
| story id and test mapping | `TC-012-03` in the test name | to decide (existing tests use `#163`, `s163-`) |
| test command and report | `make test`, `reports/junit/*.xml` | `node --test` with the JUnit reporter in `app`, `web`, `e2e`, `ops` |
| document languages | English plus `-zh-TW` pair | English only |
| high-risk paths | the list in `policy/risk-tiers.toml` | `infra/`, `**/migrations/**`, ledger and sign-in code |
| layers enabled | 4 | 1 and 2 first, then 3, then 4 in shadow mode |

- **Reusable workflows** in the kit; a project holds thin caller workflows that reference the kit at a commit SHA. The workflow checks out the kit's tools at the same SHA.
- Places where the current code hard-codes what must become configuration: `tools/agentctl/specs.py` (spec layout, bilingual story pair), `docs.py` (`REQUIRED` list), `trace.py` (`TC_IN_TEST_RE`), `github.py` (`STORY_BRANCH_RE`, three-digit ids, `BRANCH_PREFIXES`), `sandbox/sbx.sh` (`valid_story`), the workflows' use of `make`.

## 4. formosan-serow: what was found

Repository `Team-JJR/formosan-serow`, attached to the old session read-only and cloned at `/home/user/formosan-serow`. Nothing was changed there. A new session needs to attach it again, and needs push access to write a migration branch.

- A booking and class-pass platform (TypeScript, Fastify, PostgreSQL, Terraform on AWS). Not live yet; close to UAT. The director wants safer practices in place before launch.
- It has its own working agreement in `AGENTS.md` (149 lines), decided by the director, with rules that differ from the kit:
  - a story is a GitHub issue; acceptance bullets live in the issue body; tests are grouped as `describe("#163 …")` in files named `s163-….test.ts`; `docs/test-map.md` maps bullets to tests;
  - roles: PO session, lead (an Opus session that dispatches and merges), SEIT (writes acceptance tests first, on another model than the SE), SE, reviewer (`.claude/agents/reviewer.md`), and a challenger for high-risk work;
  - labels `risk:high` and `sensitive` set by the director; at most two stories in progress;
  - "No other process document is created. A new rule goes here";
  - English in the repository; the sprint issue in Traditional Chinese;
  - no CI: Actions minutes ran out, and CI was to be added after 2026-12-01.
- `deploy.sh live` deploys from the Mac with an `AWS_PROFILE` that has deploy rights. **So production credentials are on the Mac while that token is valid.** The original threat model assumed there were none.
- No `Makefile`, `tools/`, `policy/`, `sandbox/`, `prompts/`, `bin/` or `scripts/` at the root, so the kit's paths do not collide. `.github/` holds only issue templates.
- Tests need PostgreSQL in Docker. **Unverified: whether that works inside an sbx microVM.** Check this first; layer 1 depends on it.
- Open issues on 2026-11-27 (via the REST API; GraphQL is not available from a cloud session):
  - Sprint 10, label `story`: #441 to #454 and #456, most also `sensitive`. #455 is the sprint issue.
  - **#456 is "CI/CD: GitHub Actions tests every pull request and deploys every merge to main; deploy.sh is the emergency path".** It overlaps layer 3 and the release question. Do not design either without reading it.
  - Sprint 9: #403 (sprint issue), #216 (live in its own AWS account; open pull request #233 on branch `s216-org`).
  - Unlabelled, #457 to #462: feedback from the first tenant, in Chinese. Not stories yet.
  - Others: #1 Roadmap (pinned), #36, #42, #44, #100, #128, #245.
- Not checked: whether `Team-JJR` is on the Team plan (rulesets on private repositories need it).

### Proposed for the migration, not yet decided by the director

- `AGENTS.md` is the director's document. Propose a rewrite as a pull request for approval; do not overwrite it. Map lead to conductor, SEIT to the tests stage, SE to impl, reviewer to review. The challenger has no counterpart in the kit; propose one.
- Keep the names of existing tests. New stories use whatever id format is chosen. Issue numbers are already above 460, and the kit's three-digit story id would not survive reuse of them; choose new ids for file-based stories rather than reusing issue numbers.
- Do not change how releases are made before UAT. List it as a post-launch item and say plainly what having production credentials on the Mac means until then. Reconcile this with #456.
- Order: layers 1 and 2 first; layer 3 when Actions minutes are available; layer 4 last and in shadow mode.

## 5. The fourth review (at `553cfc2`): not yet fixed

Verdict: project bootstrap may begin under supervision; the machine guide and the spike are not ready to follow verbatim.

Blockers:
1. Re-attach can scan one clone and open another: the interactive sandbox name identifies repository, harness and stage, not the checkout it mounts.
2. The network probe cannot tell an origin's 403 or 5xx from a policy denial, and checklist item A14 re-attaches to a sandbox created under the permissive preset.
3. `docs/new-machine.md` section 4 runs `bin/agentctl doctor` before telling the reader to install `sbx`; `doctor` fails without a sandbox runtime. The guide also prescribes Claude-specific steps to a reader who may only use Codex.

Before unattended use:
4. In `sbx.sh job`, `( create … ) || rc=$?` suppresses `errexit` inside `create`: a failed `sbx create` or `sbx secret set` still reaches `sbx run`. Clean-up needs a record of what this invocation created.
5. Auto-merge that is no longer eligible stays armed when the planner returns early (red `main`, broken dependency plan) or the story is not in the active sprint. `tier_of` ignores which base or pull request a `risk-tier/*` status was computed for.
6. A paused pass still fails on a malformed `CONDUCTOR_QUOTA`. On Ctrl-C or after three failed passes, a local conductor writes `CONDUCTOR_HOME=actions` even when it no longer holds the lease.
7. A story that resumes after being parked can be dispatched while another story's session, touching the same thing, is still running. A story waiting on a person can hold its claim forever without a stalled-sprint notice.
8. `count_red` matches by substring, so an unrelated `test_hello_legacy` failure counts for `test_hello`. `tools/junit_unittest.py` drops a failing `unittest.subTest` and exits 0.
9. The five-run baseline fills its quota by download before parsing, so five malformed reports displace older usable ones.

Checklist notes: A18 (a push of the same SHA to the same ref is a no-op), F14 (require positive evidence that the variable was read), F16 (needs a fresh head or a newly submitted review).

**Recommendation given to the director, and the reason the review loop was stopped:** adversarial review of about four thousand lines that have never run against the real services does not converge, the fixes themselves introduced defects, and the most important open questions (for example what a request denied by the sbx proxy looks like from inside) can only be answered on a real machine. Rather than patching, **remove**: interactive re-attach (always a fresh sandbox), the local conductor and lease (Actions only at first), the auto-merge path for stories (the director presses merge; that is already the default shadow mode), and re-admission of parked stories (escalate instead). That would dispose of blocker 1 and items 5, 6 and 7. The director has not decided this. Raise it before fixing those items one by one. Items 4, 8 and 9 and blockers 2 and 3 need fixing either way.

## 6. Suggested order of work

1. Confirm with the director: where the public repository lives and what it is called; whether to cut scope as recommended in section 5; that `Team-JJR` is on the Team plan.
2. Kit: move the tools out of the project (install once per Mac), introduce `agentdev.toml`, turn the workflows into reusable ones, split the documents by layer, write the generic adoption guide. Carry layers 3 and 4 over as they are and mark them unverified.
3. Fix what remains of section 5 after the scope decision.
4. formosan-serow: verify PostgreSQL in Docker inside an sbx sandbox; read #456; write the migration plan in that repository; propose the `AGENTS.md` rewrite; convert the open Sprint 10 stories to files.
5. Run layers 1 and 2 on the director's Mac and on formosan-serow, with the director present. This is the first contact with real services. Expect it to change things.

## 7. Working in this repository from a Claude Code session

- The repository's own `.claude/settings.json` denies the Edit and Write tools on guardrail paths (`.github/`, `policy/`, `tools/`, `bin/`, `scripts/`, `sandbox/`, `prompts/`, `.claude/`, `AGENTS.md`, `CLAUDE.md`, `Makefile`), and `.claude/hooks/guard.sh` blocks Bash commands whose text contains certain strings (the `gh` subcommands that create or merge pull requests, privilege escalation, creating tags). The director authorised maintenance of the pipeline in the old session; a new session should ask again. What worked: write a Python patch script or the new file into the scratchpad, run or copy it from there, and commit with `git commit -F <file>`.
- A Stop hook asks for uncommitted changes to be committed and pushed.
- `gh` GraphQL is unavailable from a cloud session; use `gh api` with REST paths.
- Subagents handled document updates well when given the exact diff to mirror. Tell them not to commit and which files they own; run them on a cheaper model.
- The repository's `AGENTS.md` addresses agents dispatched by the pipeline. A human asking directly for maintenance is the other case it describes (rule 3).
