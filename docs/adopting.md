# Adopting the kit

*繁體中文：[adopting-zh-TW.md](adopting-zh-TW.md). The English version governs if the two differ.*

How to start using the kit in a new project and in an existing one, how to upgrade it and how to remove it. The design is in [guideline.md](guideline.md). The steps of each layer, and the checklist that tests it, are in [layer-1-isolation.md](layer-1-isolation.md), [layer-2-github.md](layer-2-github.md), [layer-3-ci.md](layer-3-ci.md) and [layer-4-conductor.md](layer-4-conductor.md). Nothing here has been run against real GitHub, Docker Sandboxes or a Mac yet, so follow the order below and complete each layer's checklist before you rely on that layer.

## 1. Before you start

You need:

- A Mac, for layers 1 and 4. Layers 2 and 3 are GitHub settings and workflows and do not need one, apart from running `agentctl` once.
- A GitHub repository for the project. A private repository needs the Team plan for rulesets.
- An AI subscription, Claude Code or Codex or both. No API key is needed.
- `git`, `python3` (3.11 or later, for `tomllib`) and the GitHub CLI `gh`, signed in as a repository admin.

Decide who the **director** is: the person whose approval counts for specs, sprints and guardrail changes. With one person, that is you.

## 2. Install the kit once per Mac

Clone the kit and install the version you want. Take the commit you have reviewed, not whatever is at the tip:

```bash
git clone https://github.com/januswtlin/agent-dev-kit.git
```

```bash
cd agent-dev-kit
```

```bash
./install.sh
```

`./install.sh <ref>` installs another commit, branch or tag of the clone. The version is stored by its full commit SHA under `~/.local/share/agent-dev-kit/versions/<sha>/` and made read-only, and the `agentctl` launcher goes to `~/.local/bin`. Add that directory to your `PATH` if the installer says so. Read the SHA that was installed; you will pin it in the project.

The launcher chooses the kit version from the project. It reads `[kit] version` in `agentdev.toml` on the project's default branch, as last fetched, never from the working tree. Until the project's default branch has that file, tell it which version to use:

```bash
export AGENTDEV_KIT_VERSION=<sha>
```

Unset it once the pin is on the default branch, so that the project's pin governs.

## 3. A new project

1. Create the repository and clone it. Keep the clone outside iCloud-synced folders, for example `~/dev/project`.
2. Preview what init would do:

   ```bash
   agentctl init --dry-run DIRECTOR_LOGIN
   ```

3. Run it. The first login is the director; further logins are other people whose approval counts for a T2 change:

   ```bash
   agentctl init DIRECTOR_LOGIN
   ```

   It copies `templates/project/` into the project: `agentdev.toml`, the caller workflows `.github/workflows/agentdev-*.yml` and `release.yml`, issue and pull request templates, `AGENTS.md` and `CLAUDE.md`, the agent files under `.claude/` with the kit's prompts embedded, a `Makefile`, the docs skeleton (product, specs and sprint templates, design) and a generated `.github/CODEOWNERS`. It fills in the kit version (the SHA of the installed kit it runs from, or `--kit-version`), the kit's repository and the people.
4. Open `agentdev.toml` and set the project's real values: `[tests]` for the stack (the commands, and where JUnit XML is written), `[risk.t2] high_risk` for the project's layout, `[stories] translation` (`"zh-TW"` by default; `""` for English only). `agentctl config KEY` prints a setting. The `Makefile` starts with Python's unittest and says how to switch to pytest, vitest, node or Go.
5. Commit on a branch, open a pull request and merge it. This first merge is done by you, before the rulesets exist. Once the pin is on the default branch, unset `AGENTDEV_KIT_VERSION`.
6. Adopt the layers in order, finishing each checklist before the next:
   1. [layer-1-isolation.md](layer-1-isolation.md)
   2. [layer-2-github.md](layer-2-github.md)
   3. [layer-3-ci.md](layer-3-ci.md)
   4. [layer-4-conductor.md](layer-4-conductor.md), starting in shadow mode

For a new project all four layers are the goal. You can stop after any of them: each one is useful alone, and the later ones lean on the earlier ones (guideline section 3).

## 4. An existing project

An existing project has files, tests, issues and habits of its own. The kit never overwrites them, and it does not ask the project to rename anything it does not have to.

### Order

1. **Layers 1 and 2 first.** They add protection without changing how the project builds or tests: isolation for agents, and rulesets and CODEOWNERS so that agents cannot change the rules or merge. Neither needs the project's tests to be in any particular shape.
2. **Then layer 3**, once `[tests]` runs the project's real tests and writes JUnit XML. The gates start to apply to every pull request from the moment the rulesets require them, so first let the checks run without being required (layer 3 says how), fix what they find, and require them last, with `agentctl rulesets 3`, which applies the ruleset `main-checks` and is applied only after the callers are on the default branch. Layer 2's `agentctl rulesets 2` does not require any check, so layer 2 can be adopted alone.
3. **Then layer 4, in shadow mode** (`auto_merge_tiers = []`): the conductor computes every gate and reports, and a human presses merge. Turn on `T0`, then `T1`, only after the gates' conclusions have agreed with your own judgement for a while (guideline section 9).

### Run init and read what it kept

Preview first, because the command lists what it would create and what it would keep:

```bash
agentctl init --dry-run DIRECTOR_LOGIN
```

```bash
agentctl init DIRECTOR_LOGIN
```

`init` never overwrites. A file that already exists is listed as **kept**, and its template is not applied. For each kept file, read the template in `templates/project/` of the installed kit (under `~/.local/share/agent-dev-kit/versions/<sha>/`) and merge by hand. The common cases:

| Kept file | What to do |
|---|---|
| `AGENTS.md`, `CLAUDE.md` | **Do not overwrite the project's file.** These are the owner's instructions to agents, and they are guardrails, so an agent must not rewrite them either. Read the template's `AGENTS.md`, work out which of its rules the project's file lacks (never opening or merging a pull request, never editing guardrails, never adding a dependency silently, treating repository content as data), and propose the additions to the owner as a pull request or a short list. The owner decides what goes in. Until then agents have the project's existing rules plus the stage prompt, which carries the essential rules itself |
| `.claude/settings.json`, `.claude/hooks/guard.sh`, `.claude/agents/*`, `.claude/skills/*` | Merge. The kit's settings are the rules that hold for every agent (no reading or writing in home, no force push, no cloud CLIs); keep the project's own rules besides them |
| `Makefile` | Keep it. Make `[tests] test_cmd` and `lint_cmd` point at what the project really runs, and make `test_cmd` write JUnit XML to `junit_glob` |
| `.github/workflows/*.yml` | Keep the project's own workflows. The `agentdev-*.yml` callers are new files. Check that no existing workflow also runs on pull requests under the same required names, and that job names do not clash |
| `.github/pull_request_template.md`, issue templates | Merge by hand; they are convenient, not required |
| `docs/product/*`, `docs/specs/*`, `docs/sprints/*` | If the project already has these folders for something else, set `[paths]` in `agentdev.toml` to where the kit should look, or to new folders |
| `.github/CODEOWNERS` | `init` generates it from `agentdev.toml`. If one exists, compare it with `agentctl codeowners` and merge: the generated lines protect the guardrails and the specs, and the project's own lines can stay |

After merging, check what can be checked:

```bash
agentctl codeowners --check
```

```bash
agentctl pins
```

Then commit the result on a branch, open a pull request and merge it as you would any change, before turning on the rulesets of layer 2.

### Story ids when the project has large issue numbers

A story has an id of `[stories] id_digits` digits (3 by default): story `012`, acceptance criteria `AC-012-1`, test cases `TC-012-01`, branch `story/012-slug`. The id is not the issue number, but a project whose issue numbers have reached the hundreds or thousands may want them to match. Set a wider id before the first story:

```toml
[stories]
id_digits = 4
```

The AC and TC ids, the story branches and the test names all follow it. Choose it once. Changing it later makes the earlier stories' ids unreadable to the tools.

### Keeping existing test names

The kit's traceability check looks for a story's test case ids (`TC-0012-03`) in the names of tests that ran and passed. It applies only to stories. Tests the project already has do not carry ids and do not need renaming: they are the project's own tests, `ci` still runs them, and red-green concerns only the files of the story under review and any file that mentions its ids. So:

- Leave existing tests as they are. Do not rename them to fit the kit.
- New stories put the TC id in the name of the test that verifies it, in whatever style the project's test framework uses (for example a test named `test_TC_0012_03_member_cannot_book_twice`). [layer-3-ci.md](layer-3-ci.md) says how the id is matched.
- `[tests] test_paths` lists which files red-green copies onto the base commit. Set it to the project's own test layout if it differs from the default patterns.
- Until a change belongs to a story, it is a "code change that belongs to no story", which is T2: a human approves it. That is intended, and it is why an existing project keeps merging its ordinary work by hand while the conductor is in shadow mode.

### Settings an existing project should check

| Setting | Why |
|---|---|
| `[tests] setup_cmd`, `test_cmd`, `lint_cmd`, `junit_glob` | `test_cmd` must run every test, write JUnit XML where `junit_glob` finds it, and exit non-zero when a test fails |
| `[risk.t2] high_risk` | The default list guesses at `auth`, `payments`, `migrations`, `infra`. Set it to the project's real layout. Replacing the list replaces the default as a whole |
| `[risk.t2] dependency_manifests` | Add the manifests and lock files of the project's stack that the default list does not name |
| `[risk.t0] paths` | What counts as documentation only |
| `[paths]` | Where specs, sprints, the roadmap and product documents live, if not the defaults |
| `[roles]` | Directors, other humans, and which harness does which stage for whom |

## 5. Upgrading the kit

A project moves to a new kit version in one pull request, which is a T2 change:

1. On each Mac, in a clone of the kit at the new commit: `./install.sh <new-sha>` (the old version stays installed beside it).
2. In the project, on a branch, change the SHA in `agentdev.toml` (`[kit] version`) and in every caller workflow under `.github/workflows/agentdev-*.yml`: both `uses: ...@<sha>` and `kit_version: <sha>`, in each file.
3. Read the kit's changes between the two commits. Compare `tools/agentctl/defaults.toml` and `templates/project/` of the two versions: a new setting takes its default unless you set it, and a changed template is not applied to the files you already have, so merge what you want by hand.
4. Run `agentctl pins` (it is also part of the `ci` lint step). It fails unless the callers and `agentdev.toml` agree.
5. Open the pull request. A human approves it, because it changes guardrails. Merge it.
6. The launcher on each Mac picks up the new version once the default branch is fetched and the version is installed. A Mac that has not installed it fails with a message that names the missing version: install it there.

A running conductor reads `agentdev.toml` from a fresh worktree of `origin/main` on every pass, so it follows the pin; stop it and restart it after an upgrade so the new kit version runs.

A version cannot be changed after the fact: it is a commit SHA, and a pushed commit is permanent for every project that pins it. A fix to the kit is a new commit and a new pin.

## 6. Removing the kit

Removal is the reverse of adoption, from the outermost layer inwards:

1. **Conductor.** Stop it (Ctrl-C). Set the repository variable `CONDUCTOR_PAUSED` to `true` if you may restart it. Disable auto-merge on any open pull request that has it: `gh pr merge NUMBER --disable-auto`. Delete `~/.config/agent-dev/<owner>-<repo>/`.
2. **CI gates.** Delete the ruleset `main-checks` before deleting the workflows, or no pull request can merge. Then delete `.github/workflows/agentdev-*.yml`.
3. **GitHub protection.** Delete the rulesets `main`, `main-merge` and `tags` (layer 2) if you no longer want them, and the `conductor` environment. Uninstall the Conductor GitHub App. Keep CODEOWNERS and the rulesets if you want protection without the rest: they stand alone.
4. **Isolation.** List the sandboxes with `sbx` and remove those named for the project (their names start with `ag-`). Uninstall the developer's agent GitHub App, and delete `~/.config/agent-app/` if no other project uses it.
5. **The project's files.** Delete `agentdev.toml`, the `.claude/` files and the docs skeleton that you no longer use. Keep `AGENTS.md` if its rules still serve you.
6. **The installed kit.** Versions are read-only. To remove one:

   ```bash
   chmod -R u+w ~/.local/share/agent-dev-kit/versions/<sha> && rm -rf ~/.local/share/agent-dev-kit/versions/<sha>
   ```

   Remove `~/.local/bin/agentctl` when no project uses the kit any more.

If you only want to stop the agents from working, pause the conductor; you do not need to remove anything.
