#!/usr/bin/env bash
# Agent sandboxes with Docker Sandboxes (sbx). Run on the Mac, from the project directory.
#
#   sandbox/sbx.sh setup              one-time: lock down sbx and install the token helpers
#   sandbox/sbx.sh job HARNESS STORY STAGE PROMPT
#                                     one unattended stage in a fresh sandbox; used by the conductor
#
# There is no interactive mode. To work with an agent yourself, use sbx directly
# (`sbx create --clone`, `sbx run`): such a sandbox gets the machine-wide deny-all
# preset and allowlist from `setup`, but no GitHub token and no harness deny rules.
#
# What makes this the boundary:
#   - one microVM per agent, with its own kernel
#   - CLONE MODE: the repository is mounted read-only and the agent works on a
#     private clone inside the VM. Nothing the agent does can change files on the
#     Mac, including .git/hooks. Its only way out is `git push`.
#     The WHOLE repository directory is visible read-only, ignored and untracked
#     files included. So no secret may live in it: this script refuses to start
#     while it finds a file whose name looks like one.
#   - network: deny-all preset, plus the hosts in sandbox/allowlist.txt. What a
#     sandbox can really reach is probed from inside it on every start; what
#     `setup` once configured is not taken on trust.
#   - no GitHub credential inside the VM: the sbx proxy on the host swaps a
#     placeholder for a one-hour token of YOUR agent GitHub App, which a helper on
#     the host mints on demand. The App's private key never leaves the host.
#   - SSH agent forwarding and the shared skills store are turned off
#   - one sandbox per stage, never reused, each given only what that stage needs
#     (tools/agentctl/profiles.py)
#
# Nothing from the project directory is executed on the host by this script: the
# tooling it runs is a copy pinned outside the repository, started with an
# isolated Python (-I) so the current directory cannot shadow it.
#
# Before `setup`, put your agent App's id and private key on the HOST:
#   ~/.config/agent-app/app-id      (one line: the App ID)
#   ~/.config/agent-app/key.pem     (chmod 600)
#
# NOT YET RUN on a real machine. The sbx commands follow the Docker Sandboxes
# documentation as read in November 2026; run docs/redteam-machine.md after setup.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# AGENT_PROJECT_DIR: the repository to clone, when this script is run from another
# checkout of it (the local conductor runs the copy on the default branch).
project="$(cd "${AGENT_PROJECT_DIR:-$here/..}" && pwd)"
conf="${AGENT_APP_DIR:-$HOME/.config/agent-app}"

die() { echo "$*" >&2; exit 1; }
need_sbx() { command -v sbx >/dev/null || die "sbx not found. Install Docker Sandboxes: https://docs.docker.com/ai/sandboxes/"; }

case "$project" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Library"*)
    die "Refusing: $project is inside a folder that may be synced or private. Move the project to ~/dev." ;;
esac

# This script runs on the Mac with your permissions. If you have an agent's branch
# checked out, the copy of it you are running is the agent's. So it only runs when
# the files that make up the host side are identical to the default branch.
trusted_checkout() {
  local root default
  root="$(cd "$here/.." && pwd)"
  default="$(git -C "$root" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
  if ! git -C "$root" diff --quiet "$default" -- sandbox tools bin policy 2>/dev/null \
     || [ -n "$(git -C "$root" ls-files --others --exclude-standard -- sandbox tools bin 2>/dev/null)" ]; then
    [ "${AGENT_ALLOW_MODIFIED_SCRIPTS:-0}" = "1" ] && return 0
    die "sandbox/, tools/, bin/ or policy/ in $root differ from $default.
Run this from a clean checkout of the default branch, not from a branch under review.
(To develop these scripts themselves: AGENT_ALLOW_MODIFIED_SCRIPTS=1)"
  fi
}

# owner-name of the origin remote: two clones of different repositories never share state.
origin="$(git -C "$project" config --get remote.origin.url)" || die "$project has no origin remote."
full="$(printf '%s' "$origin" | sed -E 's#^.*[:/]([^/:]+)/([^/]+)$#\1/\2#; s#\.git$##' | tr '[:upper:]' '[:lower:]')"
slug="$(printf '%s' "$origin" | sed -E 's#^.*[:/]([^/:]+)/([^/]+)$#\1-\2#; s#\.git$##' | tr -c 'A-Za-z0-9._-' '-' | sed 's/-*$//')"
[ -n "$slug" ] || die "cannot derive a name from the origin remote: $origin"
# Sandbox names are limited to 63 characters, so they carry a short tag instead of
# the full owner-name: its first 8 characters and 6 of a hash of owner/name. The
# hash also keeps "a-b/c" and "a/b-c", which share a slug, apart.
tag="$(printf '%s' "$slug" | tr '[:upper:]' '[:lower:]' | cut -c1-8 | sed 's/[^a-z0-9]*$//')-$(printf '%s' "$full" | git hash-object --stdin | cut -c1-6)"

helper_dir="${XDG_DATA_HOME:-$HOME/.local/share}/agent-dev/$slug"
helper="$helper_dir/github-token"   # followed by -write or -read
log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/agent-dev/$slug"

# The pinned tooling, isolated from the current directory and from PYTHONPATH.
agentctl() { python3 -I "$helper_dir/run.py" "$@"; }

valid_harness() { case "$1" in claude|codex|ollama) ;; *) die "unknown harness: $1" ;; esac; }
valid_stage() { [[ "$1" =~ ^[a-z][a-z-]{1,30}$ ]] || die "not a stage name: $1"; }
valid_story() { [[ "$1" =~ ^([0-9]{3}|sprint)$ ]] || die "not a story id: $1"; }
valid_name() { [ "${#1}" -le 63 ] || die "sandbox name too long (${#1} > 63 characters): $1"; }

# Two repositories whose owner-name collide ("a-b/c" and "a/b-c") would share the
# pinned tooling and the token helpers. The directory records whose it is.
same_repository() {
  [ ! -e "$helper_dir/origin" ] || [ "$(cat "$helper_dir/origin")" = "$full" ] \
    || die "$helper_dir belongs to $(cat "$helper_dir/origin"), not to $full. Their names collide; set XDG_DATA_HOME to keep them apart."
}

no_secrets_in_tree() {
  # Clone mode mounts the whole directory: every file that is not tracked is listed
  # here, whether git ignores it or not.
  local found
  # -z: names arrive as they are. Otherwise git quotes a path with unusual
  # characters, and the closing quote would hide the file's ending from the pattern.
  found="$(git -C "$project" ls-files --others -z 2>/dev/null | tr '\n\0' '?\n' \
    | grep -iE '(^|/)(\.env[^/]*|[^/]*\.pem|[^/]*\.key|[^/]*\.p12|[^/]*\.pfx|id_rsa[^/]*|id_ed25519[^/]*|id_ecdsa[^/]*|credentials[^/]*|[^/]*secret[^/]*|\.netrc|\.npmrc|\.pypirc)$' || true)"
  if [ -n "$found" ] && [ "${AGENT_ALLOW_FILES_IN_TREE:-0}" != "1" ]; then
    echo "These untracked files in $project would be readable from inside every sandbox:" >&2
    printf '%s\n' "$found" | sed 's/^/  /' >&2
    die "Move them out of the repository (conductor credentials belong in ~/.config/agent-dev/). To proceed anyway: AGENT_ALLOW_FILES_IN_TREE=1"
  fi
}

# What the sandbox can really reach, asked from inside it. `setup` configures a
# deny-all preset once, but the preset is machine-wide and can be changed behind
# this script's back.
#
# This is a spot check, not a proof of the allowlist: it asks for one host that must
# be reachable and one or two that must not be. The three URLs all answer 200 when
# they are reached, which is what lets the answers be told apart:
#   "HTTP 2xx/3xx"  the request got through
#   "HTTP 4xx/5xx"  something answered in the host's place: taken as the proxy's refusal
#   "NONE"          no answer at all: refused, or no network
# The first probe (a host on the allowlist) separates "refused" from "no network".
probe() {  # probe NAME URL -> prints "HTTP <code>", NONE or NOCURL; nothing if sbx exec failed
  # shellcheck disable=SC2016  # expanded by the shell inside the sandbox
  sbx exec "$1" -- sh -c 'command -v curl >/dev/null 2>&1 || { echo NOCURL; exit 0; }
    code="$(curl -sS -o /dev/null -m 10 -w "%{http_code}" "$1" 2>/dev/null)" || code=000
    if [ "$code" = "000" ]; then echo NONE; else echo "HTTP $code"; fi' sh "$2" 2>/dev/null | tail -n 1 || true
}
verify_network() {  # verify_network NAME NETWORK
  local result url
  cannot_check() {
    [ "${AGENT_SKIP_NETWORK_PROBE:-0}" = "1" ] && return 0
    die "cannot check what sandbox $1 can reach: $2.
To proceed without the check: AGENT_SKIP_NETWORK_PROBE=1"
  }
  result="$(probe "$1" https://github.com/)"
  case "$result" in
    "HTTP 2"??|"HTTP 3"??) ;;
    *) cannot_check "$1" "github.com, which is on the allowlist, did not answer from inside it (${result:-sbx exec failed})" ;;
  esac
  for url in https://example.com/ $([ "$2" = "build" ] || echo https://registry.npmjs.org/); do
    result="$(probe "$1" "$url")"
    case "$result" in
      NONE|"HTTP 4"??|"HTTP 5"??) ;;
      "HTTP 2"??|"HTTP 3"??) die "sandbox $1 can reach $url, which no rule of this project allows for it.
The sbx network preset is not deny-all, or a machine-wide rule allows it. See docs/new-machine.md, section 4." ;;
      *) cannot_check "$1" "${result:-sbx exec failed}" ;;
    esac
  done
}

install_helper() {
  if [ ! -s "$conf/app-id" ] || [ ! -s "$conf/key.pem" ]; then
    die "Put your agent App's id in $conf/app-id and its private key in $conf/key.pem first."
  fi
  chmod 600 "$conf/key.pem"
  mkdir -p "$helper_dir"
  same_repository
  printf '%s\n' "$full" > "$helper_dir/origin"
  rm -rf "$helper_dir/agentctl" "$helper_dir/run.py"
  # Copy the tooling from the default branch, not from the working tree.
  git -C "$project" fetch --quiet origin
  default="$(git -C "$project" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
  git -C "$project" archive "$default" tools/agentctl tools/run.py | tar -x -C "$helper_dir" --strip-components=1
  repo="$(agentctl repo-name "$origin")"
  [ -n "$repo" ] || die "origin is not a GitHub repository: $origin"
  # One helper per permission set. A sandbox is pointed at exactly one of them.
  for scope in write read; do
    cat > "$helper-$scope" <<EOF
#!/usr/bin/env bash
# Prints a one-hour "$scope" token for the agent GitHub App. Run by the sbx proxy on the host.
set -euo pipefail
cd /
export AGENT_APP_ID="\$(cat "$conf/app-id")" AGENT_APP_KEY="$conf/key.pem"
exec python3 -I "$helper_dir/run.py" app-token --repo "$repo" --profile $scope
EOF
    chmod 700 "$helper-$scope"
  done
  echo "token helpers installed in $helper_dir (tooling from $default, repository $repo)"
}

allow_hosts() {  # allow_hosts FILE [sbx policy options...]
  local file="$1"; shift
  while IFS= read -r line; do
    host="${line%%#*}"; host="$(echo "$host" | tr -d '[:space:]')"
    [ -z "$host" ] || sbx policy allow network "$@" "$host"
  done < "$file"
}

create() {  # create NAME HARNESS STAGE
  [ -x "$helper-write" ] || die "Run sandbox/sbx.sh setup first."
  same_repository
  valid_name "$1"
  no_secrets_in_tree
  # What this stage may hold comes from the pinned copy of the tooling, not from the
  # checked-out branch: token scope, network, settings.
  read -r scope network settings < <(agentctl stage-profile "$3")
  # Never reuse a sandbox: one left over from another stage would keep that stage's rules.
  if sbx ls 2>/dev/null | grep -qw -- "$1"; then
    # Exit status 3: the caller must not remove a sandbox it did not create.
    echo "sandbox $1 already exists. Remove it first: sbx rm --force $1" >&2; exit 3
  fi
  (cd "$project" && sbx create --clone --name "$1" "$2" .)
  # The real token never enters the VM: the proxy asks the helper when it needs one.
  # A "read" token can comment and label but cannot push.
  sbx secret set github --sandbox "$1" --command "$helper-$scope" --refresh 50m
  # Package registries only for stages that build.
  if [ "$network" = "build" ]; then allow_hosts "$here/allowlist-build.txt" --sandbox "$1"; fi
  # Deny rules for the harness: a second, soft layer under the two above.
  if [ "$2" = "claude" ]; then
    sbx exec "$1" -- mkdir -p /home/agent/.claude
    sbx cp "$here/$settings-agent.claude-settings.json" "$1:/home/agent/.claude/settings.json"
  fi
  verify_network "$1" "$network"
  echo "sandbox $1: stage=$3 token=$scope network=$network settings=$settings"
}

case "${1:-}" in
  setup)
    need_sbx
    trusted_checkout
    no_secrets_in_tree
    sbx settings set ssh.agentForwardingEnabled false
    sbx settings set skills.defaultMode off
    # The allowlist only means something on top of a deny-all preset. sbx cannot change
    # a preset in place, and resetting removes every custom rule on this machine, so
    # that step needs your explicit say-so.
    # Once this script has set deny-all it remembers, so that re-running setup (to
    # refresh the pinned tooling) does not need a reset. The marker is a convenience
    # only: it cannot know what happened to the preset since. Every sandbox start
    # checks the real thing (verify_network).
    preset_marker="${XDG_STATE_HOME:-$HOME/.local/state}/agent-dev/sbx-deny-all"
    if [ "${AGENT_RESET_POLICY:-0}" = "1" ]; then sbx policy reset --force; rm -f "$preset_marker"; fi
    if [ ! -e "$preset_marker" ]; then
      sbx policy init deny-all || die "sbx already has a network preset. Re-run as: AGENT_RESET_POLICY=1 sandbox/sbx.sh setup
That removes ALL your existing sbx network rules and starts from deny-all."
      mkdir -p "$(dirname "$preset_marker")" && : > "$preset_marker"
    fi
    sbx daemon restart
    install_helper
    # Every sandbox: source control and model providers. Registries are added per sandbox.
    allow_hosts "$here/allowlist.txt"
    if [ "${AGENT_OLLAMA:-0}" = "1" ]; then sbx policy allow network localhost:11434; fi
    echo "Done. Log in to your harnesses as the sbx documentation describes."
    ;;
  job)
    need_sbx
    harness="${2:?usage: sbx.sh job HARNESS STORY STAGE PROMPT}"; story="${3:?story id}"; stage="${4:?stage}"; prompt="${5:?prompt}"
    valid_harness "$harness"; valid_story "$story"; valid_stage "$stage"
    trusted_checkout
    # Unique per invocation: the second in hex, plus a random byte for two jobs
    # started within the same second.
    stamp="$(printf '%x%02x' "$(date +%s)" "$((RANDOM % 256))")"
    name="ag-$tag-$story-$stage-$harness-$stamp"
    valid_name "$name"
    mkdir -p "$log_dir"
    log="$log_dir/$story-$stage-$harness-$stamp.log"
    # In a subshell, so that a refusal inside it comes back here and is shown.
    # A sandbox that failed a check is removed: nobody is there to inspect it. But
    # only if this invocation created it (status 3: the name was already taken).
    rc=0
    ( create "$name" "$harness" "$stage" ) > "$log" 2>&1 || rc=$?
    if [ "$rc" -ne 0 ]; then
      cat "$log" >&2
      [ "$rc" -eq 3 ] || sbx rm --force "$name" >> "$log" 2>&1 || true
      exit 1
    fi
    # From here on the sandbox is this invocation's: remove it however this ends,
    # an interrupt included.
    trap 'sbx rm --force "$name" >> "$log" 2>&1 || echo "WARNING: could not remove sandbox $name" >> "$log"' EXIT
    case "$harness" in
      claude) set -- -p "$prompt" ;;
      codex)  set -- exec "$prompt" ;;
      ollama) set -- exec --oss --model "${OLLAMA_MODEL:-devstral}" "$prompt" ;;
    esac
    # Unattended: the stage's whole result is what it pushes. The sandbox is removed
    # afterwards whatever happened; the log stays on the host.
    status=0
    sbx run --name "$name" -- "$@" >> "$log" 2>&1 || status=$?
    exit "$status"
    ;;
  *)
    sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
