# Operations

*繁體中文：[operations-zh-TW.md](operations-zh-TW.md). The English version governs if the two differ.*

Running a project once it is set up. Setting up is in [new-project.md](new-project.md) and [new-machine.md](new-machine.md).

Nothing here has been run against real GitHub yet. Anything marked **To verify** describes behaviour of GitHub itself that the code relies on.

## 1. Day to day

You decide where the conductor runs: on GitHub Actions, or in a terminal on your Mac. While you are at the computer, let it run in the terminal. That uses no Actions allowance and responds faster (one pass every three minutes).

What `conductor here` needs:

- **A clean checkout of the default branch.** It refuses to start when `tools/`, `bin/`, `sandbox/` or `policy/` in the checkout differ from the default branch. Run it from `main`, not from a branch under review. On every pass it reads the sprint, the specs and the policy from a fresh copy of `origin/main`, not from your working directory. This check guards against the accident of running it from an agent's branch. It is part of the same scripts, so it is no defence against a checkout that is already hostile.
- **A settings file outside the repository**, at `~/.config/agent-dev/<owner>-<repo>/conductor.env` (under `$XDG_CONFIG_HOME` instead of `~/.config` if you set that). It must not be in the project directory: a sandbox can read every file there, including ignored ones. The file holds `KEY=VALUE` lines:

```ini
# The Conductor App (new-project.md, section 3). The key path must be absolute; "~" is not expanded.
CONDUCTOR_APP_ID=123456
CONDUCTOR_APP_KEY=/Users/YOU/.config/agent-dev/OWNER-REPO/conductor-app.pem
# Your GitHub login. A local sandbox is not started for a story that the sprint file gives to someone else.
DEVELOPER=YOUR_LOGIN
# Dispatch credentials, the same values as the secrets in new-machine.md, section 3.
CLAUDE_TRIGGER_URL=https://...
CLAUDE_TRIGGER_TOKEN=...
DISPATCH_TOKEN=...
```

  `CONDUCTOR_APP_ID`, `CONDUCTOR_APP_KEY` and `DEVELOPER` are required; without them `here`, `away` and `status` all stop with a message. The dispatch credentials are needed for the harnesses you use. As on Actions, a name with a `_LOGIN` suffix (`CLAUDE_TRIGGER_URL_ALICE`) is used for that developer's stories, and the plain name is the fallback for everyone. With several people, give each person's credentials their suffix, or another person's story is sent with yours.
- `openssl` on the path. It signs the request for the App's token.

The local conductor acts on GitHub as the Conductor App, exactly like the Actions job: it mints the App's token itself from that key. It does not act as you. If it did, you would be the author of the pull requests it opens, and GitHub does not let an author approve their own pull request.

Start it:

```bash
bin/agentctl conductor here
```

Before you leave, press Ctrl-C, or run this in another terminal:

```bash
bin/agentctl conductor away
```

Both hand over at once: they set `CONDUCTOR_HOME` to `actions` and start a conductor run on Actions.

If you just close the laptop, nothing hands over. While `CONDUCTOR_HOME` is `local`, runs on Actions that an event triggers are skipped. Only the scheduled run and a run started by hand look at the lease, and they take over once it has gone 20 minutes without being renewed (`local_lease_minutes` in `policy/conductor.toml`). The scheduled run happens every four hours, so the gap can be up to about four hours. To close it sooner, start a run by hand from any device once 20 minutes have passed:

```bash
gh workflow run conductor.yml
```

Two more cases end a local conductor. The lease is renewed only after a pass that worked; after three failed passes in a row it sets `CONDUCTOR_HOME` back to `actions` and exits. And if a second `conductor here` starts for the same repo, the lease names the new one, and the first stops on its next pass. Repository variables are not a lock: around a hand-over two conductors can overlap for one pass. Dispatches are recorded before they are sent, so the cost is at worst one duplicated dispatch.

To see where it is running now:

```bash
bin/agentctl conductor status
```

| Situation | What to do |
|---|---|
| You want to pause everything | Set the variable `CONDUCTOR_PAUSED` to `true`. It is read live on every pass, so it stops the local conductor too, within one pass. A paused conductor dispatches nothing and opens no pull requests |
| You want to know the current state | Look at the Director's brief issue, or run `bin/agentctl status --markdown` |
| You want to know what the conductor will do next | `gh workflow run conductor.yml -f dry_run=true`, then read the run log. A dry run creates nothing. While paused it shows only `halt` |
| A story has been labelled `needs-human` | The conductor mentions the humans in a comment on the story issue; it does not assign the issue to anyone. Read the triage explanation and options on the issue, decide, then remove the label; if the spec needs changing, change the spec |
| A harness's quota is exhausted | Set `CONDUCTOR_QUOTA`; when it expires the conductor resumes using the harness automatically |
| You want a story left alone for now | Add the `blocked` label to its issue |
| You want to release | Put a `v*` tag on the commit you want on main and push it. The release fails unless `ci`, `security` and `spec-verify` are each present and green on that commit |
| You want to know how much Actions has been used | `bin/agentctl budget --dry-run`, or look at the first line of the brief. This is an estimate; GitHub's billing page is the source of truth |
| The Actions allowance is running out | Overflow is off: `overflow_runner` in `policy/conductor.toml` is empty, so `agentctl budget` reports usage and moves nothing. When the allowance runs out, CI stops and nothing merges (**To verify**). Your options: wait for the next month; pay for more minutes; or set `overflow_runner` to a runner that is dedicated to these jobs, holds no credentials and is recreated for every job. The Lima VM in `sandbox/` does not qualify: `ci` and `security` execute pull request code, and that VM is long-lived, has passwordless sudo and holds an agent's logins. Running the conductor locally (above) saves its share of the minutes |
| A story should run on a particular person's subscriptions | Name them in the sprint file: `assignee` is the default for the sprint, and an `[owners]` table overrides it per story (`"012" = "alice"`). Issue assignees are not used |
| An approved spec, sprint or chore pull request | Nothing to do. The conductor opened it with auto-merge on, so it merges by itself once the checks are green |
| You need to change the pipeline itself | Ask the agent directly in a session; the work happens on a `chore/` branch and you approve the PR |
| You suspect something is wrong | Pause, then run [redteam-project.md](redteam-project.md) and [redteam-machine.md](redteam-machine.md) |

## 2. Turning on auto-merge

This is about story pull requests. Spec, sprint and chore pull requests are opened with auto-merge on, whatever this setting says: they merge by themselves once the checks are green and every approval they need has been given. A chore pull request that changes only documentation nobody owns is T0 and needs no approval, so it merges on green checks alone, in shadow mode too (**To verify**).

Stay in shadow mode for at least one sprint. Each time the conductor notifies you that a PR "can be merged", spend a minute making your own judgement and note whether you agree. After you have agreed consistently for a while, set this in `policy/conductor.toml`:

```toml
auto_merge_tiers = ["T0"]
```

After a further while, add `"T1"`. A change to this file is itself T2 and needs your approval.

## 3. Adding a person

1. They join the organization and become a repo admin.
2. In `policy/roles.toml`, add them to `humans` and give them a `[developers.LOGIN.stages]` table. In `.github/CODEOWNERS`, add them to the paths they may approve. Add them to `directors` and to the product paths only if they are to approve product decisions.
3. They follow [new-machine.md](new-machine.md) from start to finish: their own agent App, their own secrets, their sandbox and their own cloud accounts. Their secrets go in the `conductor` environment, not in the repository secrets, with their login as the suffix (upper case, any other character as `_`): `DISPATCH_TOKEN_ALICE`.
4. For stories that are theirs: name them in the sprint file's `[owners]` table (`"012" = "alice"`), or make them the sprint's `assignee`. The conductor then uses their harness configuration, their credentials and their subscription. Setting the assignee on the story issue has no effect. A stage that runs in a local sandbox (`via = "sbx"`) only starts on their own Mac, while `conductor here` runs there with `DEVELOPER` set to their login.
5. Product decisions stay with the directors: only they are owners of `docs/specs/`, `docs/sprints/` and `docs/product/`.
