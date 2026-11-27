# Self-hosted runner inside the sandbox VM

*繁體中文：[README-zh-TW.md](README-zh-TW.md). The English version governs if the two differ.*

**This path is not part of the supported setup.** Do not follow this page as part of setting up a project or a machine. It is kept as reference for anyone who wants to finish the work. The supported local path is a Docker Sandbox started by the local conductor (`sandbox/sbx.sh`); see [docs/new-machine.md](../../docs/new-machine.md).

Why it is not supported:

- The Lima VM is long-lived, has passwordless sudo and holds an agent's logins (Claude Code, Codex, the agent App's key). Code that runs on its runner could change the firewall, read those logins and stay behind for later jobs. The runner is not rebuilt between jobs.
- For that reason budget overflow is **off by default**: `overflow_runner = []` in `policy/conductor.toml`. `agentctl budget` still estimates and reports usage, but it moves nothing unless a runner is configured. `ci` and `security` execute pull request code. They may only move to a runner that is dedicated to them, holds no credentials or logins, and is recreated for every job. This VM does not qualify, and this template does not provide such a runner. With no overflow, when the Actions allowance runs out, CI stops and nothing merges until the next month or until you pay for more.

Known gaps, if you set it up anyway:

- `sandbox/allowlist.txt` and `sandbox/allowlist-build.txt` lack the hosts a GitHub Actions runner needs, so the runner cannot work behind the VM's egress filter as it is (**To verify**: the list of hosts, from GitHub's documentation for self-hosted runners).
- The runner service does not get `AGENT_APP_ID` and `AGENT_APP_KEY`. [docs/new-machine.md](../../docs/new-machine.md) exports them in `~/.profile`, which only a login shell reads. The `agent-job` workflow calls `bin/agentctl app-token`, which needs both.
- Nothing here has been run on a real machine.

What it was designed for: while the Mac is on, the runner in the VM picks up the
`agent-job` runs that the conductor queues on GitHub for a harness with `via = "workflow"` in `policy/roles.toml`. No harness uses that setting by default.

Ollama stages do **not** run here. They run in a local Docker Sandbox started by the local conductor (`via = "sbx"`).

Cloud sessions remain the main path, because they keep working with the laptop closed. On the Mac, the main path is a Docker Sandbox started by the local conductor (`sandbox/sbx.sh`); this runner lives in the Lima fallback VM and is the weaker of the two.

The runner was also meant to take `ci` and `security` when the month's Actions allowance was nearly spent. That is the overflow described above, and it is off. Jobs that judge a pull request never move to a self-hosted runner.

## Security requirements

- The runner is installed in the VM, not on macOS. The VM mounts the project directory only, and its outbound traffic is limited by the allowlist.
- The runner serves this one private repository. Never register it with a public repository: anyone who opens a pull request could run code on it.
- Claude Code and Codex in the VM are logged in with your own subscription. Treat `auth.json` and the login state as passwords; they exist only inside the VM.
- On GitHub the runner acts as your own agent GitHub App, which has no Workflows, Administration or Commit statuses permission. Register the runner with your GitHub login as a label, so that your stories run on your machine and your subscription.

## Installation

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh shell
```

The rest runs inside the VM. Get a registration token from the repository's Settings > Actions > Runners > New self-hosted runner (Linux ARM64), download and unpack the runner into `~/actions-runner` as that page says, then:

```bash
cd ~/actions-runner && ./config.sh --url https://github.com/OWNER/REPO --token REGISTRATION_TOKEN --labels agent-sandbox,YOUR_LOGIN --unattended
```

```bash
sudo ./svc.sh install && sudo ./svc.sh start
```

Install the deny rules for story agents (no editing of guardrail paths or approved specs):

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

Log in to both harnesses inside the VM, once each:

```bash
claude
```

```bash
codex login
```

## Start the VM at login

Copy `com.agent-sandbox.vm.plist` to `~/Library/LaunchAgents/`, replace
`PROJECT_DIR` in it with the absolute path of the project, then:

```bash
launchctl load ~/Library/LaunchAgents/com.agent-sandbox.vm.plist
```

A MacBook Air sleeps when the lid closes. The runner is offline while it sleeps,
and queued work waits until it wakes. That is why the cloud is the main path.

## Not yet verified

This setup has not been run on a real machine yet, and it is not part of the supported setup (see the top of this page). If you put it in place anyway, run
`docs/redteam-machine.md`.
