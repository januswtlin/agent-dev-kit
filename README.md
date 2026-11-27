# agent-dev-template

*繁體中文：[README-zh-TW.md](README-zh-TW.md). The English version governs if the two differ.*

A project template in which AI coding agents develop continuously inside isolated environments, with a human acting as director.
It works for one person or a team, with any mix of Claude Code and Codex (Ollama to be added later), on subscriptions only. No API key is needed.

Two goals:

1. Agents cannot reach your private data and cannot cause irreversible damage.
2. You do not read ordinary PRs, merge, or dispatch work. You do only four things: state a requirement, approve stories, approve sprints, and release to production.

## How it works

```
You say one sentence ─► PO agent writes a story ─► you approve
                                       │
              ┌────────────────────────┘
              ▼
        Conductor (a stateless scheduling program, running in your terminal or on GitHub Actions)
              │  dispatches work by the approved dependencies and priority
              ▼
   design ─► tests ─► impl ─► review        each stage is a brand-new agent session,
              │                              run in a VM or in the vendor's cloud
              ▼
   all five required checks green ─► merge ─► evidence table posted to the issue
              │
              ▼
        you push a release tag ─► deploy
```

Agents can only push branches. Every other step is guarded by GitHub rulesets and checks. Four of the checks are mechanical and do not take the agent's word for anything, including "every test case you approved has a test that really runs and that changes with the behaviour".

## Where to start reading

| Document | Contents |
|---|---|
| [docs/guideline.md](docs/guideline.md) | Design and rationale. Read this first |
| [docs/new-project.md](docs/new-project.md) | Once per project: repo, conductor, rulesets, the spike. The first person does its sections 1 to 5, then all of new-machine.md, then returns for the spike |
| [docs/new-machine.md](docs/new-machine.md) | Once per person and computer: agent identity, sandbox, cloud accounts. Needs sections 1 to 5 of new-project.md to be done |
| [docs/operations.md](docs/operations.md) | Day to day: where the conductor runs, auto-merge, adding a person |
| [docs/threat-model.md](docs/threat-model.md) | Threats and the controls that answer them |
| [docs/redteam-project.md](docs/redteam-project.md), [docs/redteam-machine.md](docs/redteam-machine.md) | Checklists that verify the defences really work, for the project and for each computer |
| [docs/specs/000-example/](docs/specs/000-example/) | An example of one sentence of requirement becoming a story |
| [AGENTS.md](AGENTS.md) | The rules every agent follows |

## Directory layout

| Path | Purpose |
|---|---|
| `tools/agentctl/` | Risk tiering, spec and document checks, traceability, red-green, conductor, Actions budget estimate. Python standard library, no dependencies |
| `policy/` | Risk rules, conductor limits, role assignment, the contract with the technology stack |
| `prompts/` | Instructions for each stage, vendor-neutral |
| `.github/` | Workflows, rulesets, CODEOWNERS |
| `sandbox/` | Docker Sandboxes setup (clone mode), egress allowlist, the Lima fallback. Its self-hosted runner is not part of the supported setup |
| `.claude/`, `codex/` | Settings for each harness |
| `docs/specs/`, `docs/sprints/`, `docs/product/` | The things you approve |

## Status

The tooling layer has unit tests and they pass. Red-green has been verified end to end on a real git repo.
Integration with the real GitHub API, the two cloud services and the macOS sandbox has not yet been run on real machines.
The list is in [section 9 of the guideline](docs/guideline.md#9-verified-and-not-yet-verified), and the verification steps are in the spike section of [docs/new-project.md](docs/new-project.md).
Until the spike and both red-team checklists are complete, do not let it run unattended.

## Languages

For documents, English is the primary file. Traditional Chinese sits next to it in the same directory under a file name ending in `-zh-TW`. Stories work the same way: `story.md` is what agents implement from, and `story-zh-TW.md` is the version the director reads and approves.

## Commands

```bash
make lint
```

```bash
make test
```

```bash
bin/agentctl --help
```

```bash
bin/agentctl conductor here
```
