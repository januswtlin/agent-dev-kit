# Self-hosted runner inside the sandbox VM

*繁體中文：[README-zh-TW.md](README-zh-TW.md). The English version governs if the two differ.*

Extra capacity and a fallback. While the Mac is on, the runner in the VM picks up
the `agent-job` runs the conductor queues on GitHub. Nobody has to start them.
Ollama stages can only run here.

Cloud sessions remain the main path, because they keep working with the laptop closed.

The runner has a second use. When the month's Actions allowance is nearly spent,
`agentctl budget` moves `ci` and `security`, the two heavy jobs that execute pull
request code, onto it. Jobs that judge a pull request never come here.

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

This setup has not been run on a real machine yet. When it is in place, run
`docs/redteam-checklist.md`.
