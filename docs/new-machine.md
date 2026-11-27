# Setting up a person and their computer

*繁體中文：[new-machine-zh-TW.md](new-machine-zh-TW.md). The English version governs if the two differ.*

Done by each person who will have agents work on their stories. Sections 2, 3 and 5 are once per person and project. Section 4 is once per computer; repeat it when you get a new one.

It assumes the project already exists: sections 1 to 5 of [new-project.md](new-project.md) are done. That means the repo is there with the template on `main`, the Conductor App is installed, the `conductor` environment exists with its branch rule, and the rulesets are applied. If you are the person setting up the project, do those five sections first and come back.

Every command in this document is run from your clone of the project, on the default branch. If you do not have a clone yet, make one in a location that iCloud does not sync:

```bash
mkdir -p ~/dev && cd ~/dev && gh repo clone OWNER/REPO && cd REPO
```

Anything marked **To verify** has not yet been run on a real account or machine. When you do it, check it against the official documentation of the day and write the result back into this document.

## 1. What you need

- At least one AI coding subscription for each person whose stories agents will work on, for example Claude Max or ChatGPT. No API key is needed.
- On the Mac: Python 3.11 or newer. The tooling uses `tomllib` and starts as `python3 -I`. Check with:

```bash
python3 --version
```

- On the Mac: Docker Sandboxes (`sbx`). Homebrew and Lima only if you use the fallback VM.
- A recent `gh`, only if you will run the local conductor on this Mac (`agentctl conductor here`). The conductor uses `gh variable get` and `gh variable set`, which older releases lack. No exact minimum version is known. Check with:

```bash
gh variable get --help
```

## 2. Agent GitHub App

Each developer creates a GitHub App for their own agents, so that a commit or a comment shows whose agent made it. Under your account's Settings > Developer settings > GitHub Apps:

- Name it after yourself, for example `yourname-agent`.
- Repository permissions: Contents: Read and write; Pull requests: Read and write; Issues: Read and write; Metadata: Read. Nothing else. In particular, **not** Workflows, Administration, Commit statuses, Secrets or Variables.
- Subscribe to no webhooks, and untick Active.
- After creating it, generate a private key and install the App on this repo only.

That list is the most the App can do. No sandbox gets all of it. For each sandbox, a helper on the Mac mints a one-hour token with a subset of the App's permissions. The subset is fixed per stage in `tools/agentctl/profiles.py`:

| Token | Stages | Contents | Pull requests | Issues |
|---|---|---|---|---|
| `write` | design, tests, impl, fix, resolve-conflict, fix-main, product-owner, planner | write | read | write |
| `read` | review, triage, and any stage that file does not list | read | write | write |

So a token that can push cannot open or review a pull request, and a token that can review cannot push. Merging is a separate matter. GitHub's merge endpoint asks only for Contents: write, which the `write` token has, so the token is not what stops an agent from merging. The `main-merge` ruleset is: only repo admins and the Conductor App may update the default branch. The App itself needs Pull requests: Read and write because the review stage's token writes to pull requests, and Contents: Read and write because the build stages' token pushes. Opening and merging pull requests is the conductor's job. **To verify**: that GitHub issues an installation token narrowed this way, that the `write` token is refused when it tries to open a pull request, and that the `main-merge` ruleset refuses its merge of a pull request that is otherwise ready (C17 in [redteam-machine.md](redteam-machine.md)).

Keep the App's ID and the private key file. Section 4 puts them on your Mac, outside the sandbox. **To verify**: `agentctl app-token` has not been run against the real API yet.

To start cloud tasks by commenting, each developer also needs one personal token, `DISPATCH_TOKEN`: a fine-grained personal access token limited to this repo, with Issues: Read and write; Pull requests: Read and write; Metadata: Read. It comes from the developer's own account because the comment may have to be made by the user whose ChatGPT account is linked (**To verify**).

## 3. Your secrets

These belong to your own subscriptions. Create them as **environment secrets** of the `conductor` environment, which was created in [new-project.md](new-project.md): the repo's Settings > Environments > `conductor` > Environment secrets. Do not create them as repository secrets under Secrets and variables > Actions. The environment's deployment branch rule allows the default branch only, so a workflow run from any other ref is refused these secrets. A repository secret has no such rule (**To verify**: environments with deployment branch rules on a private repository on the Team plan).

| Type | Name | Source | When it is needed |
|---|---|---|---|
| Environment secret | `DISPATCH_TOKEN` | Section 2 | When Codex is started by a comment |
| Environment secret | `CLAUDE_CODE_OAUTH_TOKEN` | Run `claude setup-token` on your machine | Claude review |
| Environment secret | `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN` | The scheduled task created in section 5 | Claude cloud sessions |

`CLAUDE_CODE_OAUTH_TOKEN` is the only credential you create for the Claude review. On GitHub, the review job uses the token that Actions gives the job.

Which name to store them under depends on how the sprint file gives out stories:

- A story the sprint file gives to nobody in particular (`assignee = "default"`, and no entry in `[owners]`) uses the plain names: `DISPATCH_TOKEN`.
- A story the sprint file gives to a named person uses that person's names only: the plain name with the login appended in upper case, any other character as `_`, for example `DISPATCH_TOKEN_ALICE` or `CLAUDE_TRIGGER_URL_ALICE_SMITH`. If that secret is missing, the dispatch fails and says so. It does not fall back to the plain name, because that would run one person's story on another person's subscription without anyone noticing.

With one person, either keep `assignee = "default"` and use the plain names, or name yourself in the sprint file and use the suffix. With several people, give everyone suffixed secrets and name the owner of every story.

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

Two rules apply to every use of `sandbox/sbx.sh`.

**Run it only from a clean checkout of the default branch.** Never run it from an agent's branch that you have checked out. The script runs on the Mac with your permissions. If an agent's branch is checked out, the copy of the script you run is the agent's. As a guard against that accident, `setup`, `up` and `job` refuse to run when `sandbox/`, `tools/`, `bin/` or `policy/` differ from the default branch as your clone last fetched it, or when `sandbox/`, `tools/` or `bin/` contain untracked files. `bin/agentctl conductor here` has the same check. The guard is itself part of those scripts, so it does not protect you from a checkout that is already hostile. The rule is yours to keep: one checkout that stays on the default branch, and host commands run only from there. `AGENT_ALLOW_MODIFIED_SCRIPTS=1` turns the guard off; it is meant for work on the scripts themselves.

**Keep nothing secret in the project directory, ignored files included.** Clone mode mounts the whole directory read-only into every sandbox, under `/run/sandbox/source`. That includes files git ignores, such as a `.env` file, and files git simply does not track. The script refuses to set up a machine, to create a sandbox, or to re-attach to one while it finds an untracked file, ignored or not, whose name looks like a secret: `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `id_ecdsa*`, `credentials*`, `.netrc`, `.npmrc`, `.pypirc`, and any name containing `secret`, in upper or lower case. It lists them and stops. Move them out of the repository. The check goes by file name only, so a secret under another name is not found; do not rely on it. `AGENT_ALLOW_FILES_IN_TREE=1` lets the script proceed anyway. The local conductor's own credentials are kept outside the repository for this reason, in `~/.config/agent-dev/OWNER-REPO/conductor.env` ([operations.md](operations.md), section 1).

Then:

```bash
sandbox/sbx.sh setup
```

Setup does the following, in this order:

1. Turns off SSH agent forwarding (`sbx settings set ssh.agentForwardingEnabled false`) and the shared skills store (`sbx settings set skills.defaultMode off`). Both are machine-wide sbx settings: they apply to all your sandboxes, not only this project's.
2. Requires a deny-all network preset (`sbx policy init deny-all`). The allowlist only means something on top of deny-all.
3. Restarts the sbx daemon.
4. Installs the pinned tooling and the two token helpers outside the repo (see below).
5. Allows the hosts in `sandbox/allowlist.txt` for every sandbox: source control and the model providers. Package registries are not in that list.

If sbx already has a network preset the first time you run setup, step 2 fails and setup stops. Docker's "balanced" preset is one such case; it allows package managers. sbx cannot change a preset in place, so setup asks you to run it again like this:

```bash
AGENT_RESET_POLICY=1 sandbox/sbx.sh setup
```

With `AGENT_RESET_POLICY=1`, setup first runs `sbx policy reset --force`. **That removes all existing sbx network rules on this machine**, including rules you made for sandboxes that have nothing to do with this project. Then it starts again from deny-all. Write down any rules you still need before you run it.

Once setup has set deny-all it leaves a marker (`~/.local/state/agent-dev/sbx-deny-all`), and a later plain `sandbox/sbx.sh setup` skips step 2. So refreshing the pinned tooling does not need a reset. Use `AGENT_RESET_POLICY=1` again only when you want to wipe the rules and start over.

The marker only records what setup once did. It cannot know whether the preset was changed afterwards, by you or by another tool. So the script does not rely on it. **Every time a sandbox is created, and every time you re-attach to one, the script asks from inside the sandbox what it can reach**: `https://example.com/` must be refused for every sandbox, and `https://registry.npmjs.org/` must be refused for every stage that does not build. If either is reachable, the script stops and tells you; the usual cause is a preset that is not deny-all, or a machine-wide rule that is wider than this project's lists, and the fix is the reset above. The probe uses `curl` inside the sandbox. If the sandbox image has no `curl`, the script cannot check and refuses; `AGENT_SKIP_NETWORK_PROBE=1` proceeds without the check. **To verify**: that the sandbox images contain `curl`, and that a request the sbx proxy denies fails the way the probe expects (`curl -f` exiting non-zero).

The pinned tooling lives in `~/.local/share/agent-dev/OWNER-REPO/` (under `$XDG_DATA_HOME` if you set it), where `OWNER-REPO` comes from the origin remote. Two clones of different repositories never share it; the directory records which repository it belongs to, and the script stops if another repository's name maps to the same directory. It holds a copy of `tools/agentctl` and `tools/run.py` taken from the default branch on origin, not from your working tree, and two helpers, `github-token-write` and `github-token-read`. The sbx proxy on the host runs one of them when a sandbox needs a GitHub token. Everything in that directory starts as `python3 -I`, so a file in the current directory cannot take its place. After pulling changes to the tooling, run `sandbox/sbx.sh setup` again to refresh the pinned copy.

To let sandboxes reach Ollama on the Mac, run setup as:

```bash
AGENT_OLLAMA=1 sandbox/sbx.sh setup
```

Log in to your harnesses the way the sbx documentation describes for each. At the time of writing that is `sbx secret set openai --oauth` on the host for Codex, and `/login` inside the sandbox for Claude Code (**To verify**, including whether a login made this way is available to a sandbox created later; unattended jobs depend on that).

Start an interactive agent, then check the boundary from a second terminal:

```bash
sandbox/sbx.sh up claude
```

```bash
sandbox/sbx.sh check claude impl
```

Interactive sandboxes are per stage. The second argument of `up` names the stage; the default is `impl`. The stage decides the token, the network and the deny rules the sandbox gets, from the pinned copy of `profiles.py`. The sandbox is named `ag-TAG-STAGE-HARNESS`, so `up claude` and `up claude review` are two different sandboxes. `TAG` stands for the repository: the first eight characters of `owner-repo` in lower case, a hyphen, and six characters of a hash of `owner/repo`, for example `ag-acme-wid-3f9c1a-impl-claude`. The names are short because sbx limits a sandbox name to 63 characters; the script refuses to create a longer one. `up` prints the name. The review one has a token that cannot push and cannot reach the package registries:

```bash
sandbox/sbx.sh up claude review
```

`check` and `rm` take the same two arguments, harness then stage, with the defaults `claude` and `impl`:

```bash
sandbox/sbx.sh check claude review
```

```bash
sandbox/sbx.sh rm claude review
```

Running `up` again for the same harness and stage re-attaches to that sandbox, after the same two checks a new sandbox gets: no secret-looking file in the project directory, and the network probe. It keeps the token and the rules it was created with, and stays until you remove it with `rm`. A stage that builds (design, tests, impl and the fix stages) also gets the hosts in `sandbox/allowlist-build.txt`, for that sandbox only.

Unattended jobs are different. The local conductor starts each one with `sandbox/sbx.sh job`, from its own checkout of the default branch. Every job gets a fresh sandbox with a unique name (`ag-TAG-STORY-STAGE-HARNESS-TIMESTAMP`), and the sandbox is removed when the job ends, whatever happened. If a sandbox of that name already exists, the job refuses. The log stays on the Mac, in `~/.local/state/agent-dev/OWNER-REPO/`. A local sandbox is only started on the Mac of the developer whose story it is: the `DEVELOPER` line in `conductor.env`.

The agent works on a private clone and delivers by pushing. To look at its work before it pushes, fetch from the remote that sbx adds to your repo. List the remotes to find its name; it should be `sandbox-` followed by the sandbox's name as `up` printed it (**To verify**):

```bash
git remote
```

```bash
git fetch REMOTE_NAME
```

Fetching is safe. Do not check that branch out in the checkout you run host scripts from.

**To verify** on a real Mac: everything in this section. The sbx commands follow the Docker Sandboxes documentation as read in November 2026 and have not been run. In particular, confirm that `git push` from inside the sandbox succeeds and is attributed to your agent App, and record the result under C11 in [redteam-machine.md](redteam-machine.md).

Fallback: Lima. Use it only if sbx is not available to you, and only for interactive work. It is weaker, and you should know how:

- The workspace is mounted read-write, so an agent can change files on the Mac, including `.git/hooks` and the tooling under `/workspace` that the VM itself runs. There is no pinned copy.
- Traffic is filtered by address, not by host name.
- The App's key has to be inside the VM.
- One long-lived VM serves every stage. It gets the widest allowlist (both files) and one token with the `write` profile. Nothing is narrowed per stage, and nothing is thrown away between sessions.

The VM's self-hosted runner (`sandbox/runner/`, `agent-job.yml`) and moving CI onto it when the Actions allowance runs low are **not part of the supported setup path**. `ci` and `security` execute pull request code, and this VM is long-lived, has passwordless sudo and holds your agent's logins. Budget overflow is off by default (`overflow_runner = []` in `policy/conductor.toml`). The reasons and the known gaps are in [sandbox/runner/README.md](../sandbox/runner/README.md). Nothing dispatches work to this VM in the supported setup; you start agents in it by hand.

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
3. Create a scheduled task, choose API as the trigger, and set the prompt to "Carry out the instructions in the message you receive". Store its trigger URL and token as the environment secrets `CLAUDE_TRIGGER_URL` and `CLAUDE_TRIGGER_TOKEN` (section 3).

**To verify**: the request format of the API trigger. `_send` in `tools/agentctl/github.py` currently assumes a POST with a Bearer token and the body `{"text": "..."}`. Adjusting that one function to match the actual documentation is enough.

PO chat: in the Claude app, open a Claude Code session with this repo attached, type `/po`, then state the requirement.

### Codex cloud

1. At chatgpt.com/codex, connect GitHub and authorise this repo.
2. Create an environment: for the agent phase, turn the network off or set it to an allowlist, and add no secrets.
3. Turn on automatic reviews. The review rules are read from the Code Review Rules section of `AGENTS.md`.

**To verify**: whether commenting `@codex <instruction>` on a PR or issue starts an arbitrary task; and whether the review result appears as a PR review or as a comment. The `bridge` job of the `agent-review` workflow must be adjusted to match.

## 6. Red-team

Run every item in [redteam-machine.md](redteam-machine.md) on this computer. Most items expect failure or refusal; the checklist's introduction names the few that expect success. If any item gives a result other than the expected one, fix it before letting agents work unattended.

## 7. Ollama (do this later)

Ollama is installed on the Mac (it needs the GPU). A sandbox reaches it as `host.docker.internal:11434` once `AGENT_OLLAMA=1 sandbox/sbx.sh setup` has allowed that port (**To verify**: setup allows `localhost:11434` in the sbx policy; confirm that this is the rule the sandbox's address needs). In the Lima fallback, `sandbox/egress.sh` already allows it through the host gateway.

- An M2 with 24GB of memory: choose a model in the 14 to 15GB class (for example devstral 24b, gpt-oss 20b). A 19GB-class model with a large context will be very tight. For model names and sizes, go by the Ollama model library of the day.
- Always raise the context window. The default is very small, and the agent will silently lose the instructions at the start.
- Position it for T0-type work: documentation, lint fixes, test skeletons. Its output must pass every gate all the same.
- In `policy/roles.toml`, add `"ollama"` to the stages you want to hand to it. Ollama stages run in a local Docker Sandbox (`via = "sbx"`) that the local conductor starts with `sandbox/sbx.sh job`. They do not run on the self-hosted runner. So they only start while the conductor is running on your Mac (`agentctl conductor here`). A story that belongs to another developer waits for that developer's Mac.
- The model is the `OLLAMA_MODEL` environment variable of the local conductor; the default is `devstral`.
