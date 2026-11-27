# Setting up a person and their computer

*繁體中文：[new-machine-zh-TW.md](new-machine-zh-TW.md). The English version governs if the two differ.*

Done by each person who will have agents work on their stories. Sections 2, 3 and 5 are once per person and project. Section 4 is once per computer; repeat it when you get a new one. It assumes the project already exists ([new-project.md](new-project.md)).

Anything marked **To verify** has not yet been run on a real account or machine. When you do it, check it against the official documentation of the day and write the result back into this document.

## 1. What you need

- At least one AI coding subscription for each person whose stories agents will work on, for example Claude Max or ChatGPT. No API key is needed.
- On the Mac: `gh` and Docker Sandboxes (`sbx`). Homebrew and Lima only if you use the fallback VM.

## 2. Agent GitHub App

Each developer creates a GitHub App for their own agents, so that a commit or a comment shows whose agent made it. Under your account's Settings > Developer settings > GitHub Apps:

- Name it after yourself, for example `yourname-agent`.
- Repository permissions: Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Metadata: Read. Nothing else. In particular, **not** Workflows, Administration, Commit statuses, Secrets or Variables.
- Subscribe to no webhooks, and untick Active.
- After creating it, generate a private key and install the App on this repo only.

Keep the App's ID and the private key file. Section 4 puts them on your Mac, outside the sandbox. **To verify**: `agentctl app-token` has not been run against the real API yet.

To start cloud tasks by commenting, each developer also needs one personal token, `DISPATCH_TOKEN`: a fine-grained personal access token limited to this repo, with Issues: Read and write; Pull requests: Read and write; Metadata: Read. It comes from the developer's own account because the comment may have to be made by the user whose ChatGPT account is linked (**To verify**).

## 3. Your secrets

In the repo's Settings > Secrets and variables > Actions. These belong to your own subscriptions.

| Type | Name | Source | When it is needed |
|---|---|---|---|
| Secret | `DISPATCH_TOKEN` | Section 2 | When Codex is started by a comment |
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` | Run `claude setup-token` on your machine | Claude review |
| Secret | `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN` | The scheduled task created in section 5 | Claude cloud sessions |

Secrets that belong to one person's subscription (`DISPATCH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN`) can be stored per developer by appending the login in upper case, with any other character as `_`: `DISPATCH_TOKEN_ALICE`. The conductor uses the developer's own secret for that developer's stories and falls back to the plain name. With one person, the plain names are enough.

## 4. Mac and sandbox

```bash
bin/agentctl doctor
```

Fix every FAIL. The local sandbox is Docker Sandboxes in clone mode. Install `sbx` as its documentation describes (docs.docker.com/ai/sandboxes), then sign in:

```bash
sbx login
```

Put your agent App's ID and private key (section 2) on the Mac. They stay on the host, where nothing in a sandbox can read them. Use your App's ID in place of `APP_ID` and the name of the key file you downloaded:

```bash
mkdir -p ~/.config/agent-app && echo APP_ID > ~/.config/agent-app/app-id
```

```bash
mv ~/Downloads/YOUR_APP.private-key.pem ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

Then:

```bash
sandbox/sbx.sh setup
```

This turns off SSH agent forwarding for sbx (a setting that applies to all your sandboxes), allows the hosts in `sandbox/allowlist.txt`, and installs the token helper outside the repo, from the tooling on the default branch. To let sandboxes reach Ollama on the Mac, run it as `AGENT_OLLAMA=1 sandbox/sbx.sh setup`.

Log in to your harnesses the way the sbx documentation describes for each. At the time of writing that is `sbx secret set openai --oauth` on the host for Codex, and `/login` inside the sandbox for Claude Code (**To verify**).

Start an interactive agent, then check the boundary from a second terminal. An optional second argument names the stage whose privileges the sandbox gets, for example `sandbox/sbx.sh up claude review` for a token that cannot push; the default is `impl`. After pulling changes to the tooling, run `sandbox/sbx.sh setup` again to refresh the pinned copy:

```bash
sandbox/sbx.sh up claude
```

```bash
sandbox/sbx.sh check
```

The agent works on a private clone and delivers by pushing. To look at its work before it pushes, fetch from the remote that sbx adds to your repo (`REPO` is the directory name):

```bash
git fetch sandbox-agent-REPO-claude
```

**To verify** on a real Mac: everything in this section. In particular, confirm that `git push` from inside the sandbox succeeds and is attributed to your agent App, and record the result under C11 in [redteam-machine.md](redteam-machine.md).

Fallback: Lima. Use it if sbx is not available to you, or for the self-hosted runner (`sandbox/runner/README.md`). It is weaker: the workspace is mounted read-write, traffic is filtered by address, and the App's key has to be inside the VM.

```bash
brew install lima
```

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh check
```

```bash
sandbox/vm.sh shell
```

The following run inside the VM. Sign in to your harnesses (`claude`, `codex login`), then give the VM your agent App's key:

```bash
mkdir -p ~/.config/agent-app && cat > ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

Paste the private key, then press Ctrl-D. Next, with your App's ID in place of `APP_ID` and your App's name in place of `yourname-agent`:

```bash
echo 'export AGENT_APP_ID=APP_ID AGENT_APP_KEY=$HOME/.config/agent-app/key.pem PATH=/workspace/sandbox/bin:$PATH' >> ~/.profile && . ~/.profile
```

```bash
git config --global credential.https://github.com.helper '!/workspace/bin/agentctl app-token --git-credential' && git config --global user.name "yourname-agent[bot]" && git config --global user.email "yourname-agent[bot]@users.noreply.github.com"
```

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

The last command installs the deny rules meant for story agents. Also copy the `vm` profile from `codex/config.example.toml` into `~/.codex/config.toml`. For the cloud environments, apply the same story-agent rules (**To verify**: how each cloud service sets user-level rules).

## 5. Cloud agents

### Claude Code on the web

1. At claude.ai/code, connect GitHub with your own account and authorise this repo only. A cloud agent then acts as you on GitHub. Section E of [redteam-machine.md](redteam-machine.md) checks what it can do with that; run it before letting cloud sessions work unattended.
2. Create an environment: set the network to restricted and add no secrets.
3. Create a scheduled task, choose API as the trigger, and set the prompt to "Carry out the instructions in the message you receive". Store its trigger URL and token as `CLAUDE_TRIGGER_URL` and `CLAUDE_TRIGGER_TOKEN`.

**To verify**: the request format of the API trigger. `_send` in `tools/agentctl/github.py` currently assumes a POST with a Bearer token and the body `{"text": "..."}`. Adjusting that one function to match the actual documentation is enough.

PO chat: in the Claude app, open a Claude Code session with this repo attached, type `/po`, then state the requirement.

### Codex cloud

1. At chatgpt.com/codex, connect GitHub and authorise this repo.
2. Create an environment: for the agent phase, turn the network off or set it to an allowlist, and add no secrets.
3. Turn on automatic reviews. The review rules are read from the Code Review Rules section of `AGENTS.md`.

**To verify**: whether commenting `@codex <instruction>` on a PR or issue starts an arbitrary task; and whether the review result appears as a PR review or as a comment. The `bridge` job of the `agent-review` workflow must be adjusted to match.

## 6. Red-team

Run every item in [redteam-machine.md](redteam-machine.md) on this computer. If any item succeeds, fix it before letting agents work unattended.

## 7. Ollama (do this later)

Ollama is installed on the Mac (it needs the GPU). A sandbox reaches it as `host.docker.internal:11434` once `AGENT_OLLAMA=1 sandbox/sbx.sh setup` has allowed that port. In the Lima fallback, `sandbox/egress.sh` already allows it through the host gateway.

- An M2 with 24GB of memory: choose a model in the 14 to 15GB class (for example devstral 24b, gpt-oss 20b). A 19GB-class model with a large context will be very tight. For model names and sizes, go by the Ollama model library of the day.
- Always raise the context window. The default is very small, and the agent will silently lose the instructions at the start.
- Position it for T0-type work: documentation, lint fixes, test skeletons. Its output must pass every gate all the same.
- In `policy/roles.toml`, add `"ollama"` to the stages you want to hand to it. It runs in a local sandbox, so those stages only start while the conductor is running on your Mac (`agentctl conductor here`).
