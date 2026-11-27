# agent-dev-kit

*繁體中文：[README-zh-TW.md](README-zh-TW.md). The English version governs if the two differ.*

A guideline and a set of tools for projects in which AI coding agents develop continuously inside isolated environments, with a human acting as director. It works for one person or a team, with any mix of Claude Code and Codex (Ollama to be added later), on subscriptions only. No API key is needed.

Two goals:

1. Agents cannot reach your private data and cannot cause irreversible damage.
2. You do not read ordinary pull requests, merge, or dispatch work. You do four things: state a requirement, approve stories, approve sprints, and release to production.

The kit is not a template that you copy into a project. You install a version once per Mac, a project pins that version by commit SHA in `agentdev.toml`, and the project's workflows call the kit's reusable workflows at the same SHA. Nothing of the kit's code lives in the project tree.

## The four layers

Each layer can be adopted on its own, and has its own setup document and checklist.

| Layer | What it gives you | Setup and checklist |
|---|---|---|
| 1. Isolation | Agents run in Docker Sandboxes (sbx) in clone mode, or in a vendor's cloud. Each developer has a GitHub App for their agents. Mac hygiene | [docs/layer-1-isolation.md](docs/layer-1-isolation.md) |
| 2. GitHub protection | Rulesets on the default branch and on release tags, CODEOWNERS generated from your settings, the `conductor` environment, the Conductor GitHub App | [docs/layer-2-github.md](docs/layer-2-github.md) |
| 3. CI gates | The checks `ci`, `security`, `spec-verify`, `risk-gate` and `agent-review`, run by reusable workflows that thin caller workflows in your project call | [docs/layer-3-ci.md](docs/layer-3-ci.md) |
| 4. Conductor | A program on one Mac that dispatches design, test, implementation and review stages to agents and, once you allow it, merges | [docs/layer-4-conductor.md](docs/layer-4-conductor.md) |

For an existing project, adopt layers 1 and 2 first, then 3, then 4 in shadow mode (`auto_merge_tiers = []`). [docs/adopting.md](docs/adopting.md) has the order and the details.

## How it works

```
You say one sentence ─► PO agent writes a story ─► you approve
                                       │
              ┌────────────────────────┘
              ▼
        Conductor (a program with no state and no LLM, running on one Mac)
              │  dispatches work by the approved dependencies and priority
              ▼
   design ─► tests ─► impl ─► review        each stage is a brand-new agent session,
              │                              in a local sandbox or the vendor's cloud
              ▼
   all five required checks green ─► merge ─► evidence table posted to the issue
              │
              ▼
        you push a release tag ─► deploy
```

Agents can only push branches. Every other step is guarded by GitHub rulesets and checks. Four of the five checks are mechanical and do not take the agent's word for anything, including "every test case you approved has a test that really runs and that changes with the behaviour".

## Install

Once per Mac, from a clone of this repository:

```bash
./install.sh
```

This unpacks the version you have checked out, by its full commit SHA, into `~/.local/share/agent-dev-kit/versions/<sha>/` (read-only), and puts the `agentctl` launcher in `~/.local/bin`. Add that directory to your `PATH`. Several versions can sit side by side. To install a particular one:

```bash
./install.sh <sha>
```

In a project, the launcher runs the version that `agentdev.toml` pins in `[kit] version`, read from the project's default branch (as last fetched), never from the working tree. Outside a project, or while adopting the kit before the pin is on the default branch, set `AGENTDEV_KIT_VERSION=<sha>`.

Then, in the project:

```bash
agentctl init DIRECTOR_LOGIN
```

It copies the project files without overwriting anything and lists what it kept. Read [docs/adopting.md](docs/adopting.md) before you run it in an existing project.

## Where to start reading

| Document | Contents |
|---|---|
| [docs/guideline.md](docs/guideline.md) | Design and rationale for all layers, what is verified and what is not, known limitations. Read this first |
| [docs/adopting.md](docs/adopting.md) | Using the kit in a new project or an existing one: install, init, order of layers, upgrading, removing |
| [docs/layer-1-isolation.md](docs/layer-1-isolation.md) to [docs/layer-4-conductor.md](docs/layer-4-conductor.md) | One setup guide and checklist per layer |
| [docs/threat-model.md](docs/threat-model.md) | Threats and the controls that answer them |
| [examples/](examples/) | An example of one sentence of requirement becoming a story, and a sprint file |
| [AGENTS.md](AGENTS.md) | Rules for an agent maintaining the kit itself. The rules for agents in a project are in `templates/project/AGENTS.md` |

## Commands

`agentctl --help` lists everything. The commands you will use:

| Command | What it does |
|---|---|
| `agentctl init DIRECTOR [HUMAN ...]` | Copy the project files into a project, never overwriting. `--dry-run` lists what it would do |
| `agentctl doctor` | Check host hygiene on the Mac. `--inside` checks the boundary from inside a sandbox |
| `agentctl sandbox setup` | Once per Mac per project: lock down sbx and install the token helpers |
| `agentctl rulesets 2 [OWNER/REPO]` | Create or update the layer 2 rulesets: `main`, `main-merge`, `release-tags` (run by an admin, with `CONDUCTOR_APP_ID` set) |
| `agentctl rulesets 3 [OWNER/REPO]` | Create or update `main-checks`, the required checks. Apply it only after the layer 3 callers are on the default branch |
| `agentctl codeowners [--check]` | Print `.github/CODEOWNERS` generated from `agentdev.toml`, or check the committed one |
| `agentctl conductor` | Run the conductor in this terminal. `--dry-run` prints one pass and acts on nothing. Ctrl-C stops it |
| `agentctl config KEY` | Print one setting, for example `tests.test_cmd` |
| `agentctl pins` | Check that the caller workflows use the kit version `agentdev.toml` pins |
| `agentctl prompt STAGE` | Print a stage's prompt, filled in for this project |
| `agentctl status` | Sprint summary used by the director's brief |
| `agentctl budget` | Estimate this month's Actions spend |

The remaining commands (`risk`, `spec-lint`, `docs-lint`, `trace`, `redgreen`, `redgreen-collect`, `redgreen-judge`, `evidence`, `collect-junit`, `app-token`, `stage-profile`, `harness-settings`, `story-of`, `repo-name`, `junit-unittest`) are run by the workflows and by the sandbox scripts.

To check the kit itself (from a clone):

```bash
make lint
```

```bash
make test
```

## Status

The tools have unit tests and they pass. Red-green has been run end to end on a real git repository. **Nothing has run against real GitHub, Docker Sandboxes, the vendors' cloud services or a Mac.** The list of what is verified and what is not is in [the guideline](docs/guideline.md#11-verified-and-not-yet-verified), and each layer's document ends with the checks that settle its part. Until a layer's checklist is complete, do not rely on that layer, and do not let the conductor run unattended.

The known limitations of the whole kit are in [the guideline](docs/guideline.md#12-known-limitations).

## Languages

For documents, English is the primary file. Traditional Chinese sits next to it in the same directory under a file name ending in `-zh-TW`. Stories work the same way: `story.md` is what agents implement from, and `story-zh-TW.md` is the version the director reads and approves. A project can choose another language, or none, with `[stories] translation` in `agentdev.toml`.
