#!/usr/bin/env bash
# Agent sandboxes with Docker Sandboxes (sbx). Run on the Mac, from the project directory.
#
#   sandbox/sbx.sh setup              one-time: lock down sbx and install the token helper
#   sandbox/sbx.sh up HARNESS [STAGE] interactive agent in a clone-mode sandbox (claude | codex);
#                                     STAGE picks the privileges, default impl
#   sandbox/sbx.sh job HARNESS STORY STAGE PROMPT
#                                     one unattended stage; used by the local conductor
#   sandbox/sbx.sh check [HARNESS]    run the boundary checks from inside
#   sandbox/sbx.sh rm [HARNESS]       remove the interactive sandbox
#
# What makes this the boundary:
#   - one microVM per agent, with its own kernel
#   - CLONE MODE: the repository is mounted read-only and the agent works on a
#     private clone inside the VM. Nothing the agent does can change files on the
#     Mac, including .git/hooks. Its only way out is `git push`.
#   - all outbound traffic is denied except the hosts in sandbox/allowlist.txt
#   - no GitHub credential inside the VM: the sbx proxy on the host swaps a
#     placeholder for a one-hour token of YOUR agent GitHub App, which a helper on
#     the host mints on demand. The App's private key never leaves the host.
#   - SSH agent forwarding is turned off, so the agent cannot use your SSH identity
#   - one sandbox per stage, each given only what that stage needs: a reviewer's
#     token cannot push, and only building stages reach the package registries
#     (tools/agentctl/profiles.py)
#
# Before `setup`, put your agent App's id and private key on the HOST:
#   ~/.config/agent-app/app-id      (one line: the App ID)
#   ~/.config/agent-app/key.pem     (chmod 600)
#
# NOT YET RUN on a real machine. The sbx commands follow the Docker Sandboxes
# documentation as read in November 2026; run docs/redteam-checklist.md after setup.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# AGENT_PROJECT_DIR: the repository to clone, when this script is run from another
# checkout of it (the local conductor runs the copy on the default branch).
project="$(cd "${AGENT_PROJECT_DIR:-$here/..}" && pwd)"
repo_name="$(basename "$project")"
conf="${AGENT_APP_DIR:-$HOME/.config/agent-app}"
# The helper is a pinned copy outside the repository: the proxy runs it on the host,
# so it must not be something a checked-out branch can change.
helper_dir="${XDG_DATA_HOME:-$HOME/.local/share}/agent-dev/$repo_name"
helper="$helper_dir/github-token"   # followed by -write or -read
log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/agent-dev/$repo_name"

die() { echo "$*" >&2; exit 1; }
need_sbx() { command -v sbx >/dev/null || die "sbx not found. Install Docker Sandboxes: https://docs.docker.com/ai/sandboxes/"; }
sandbox_name() { echo "agent-$repo_name-$1"; }

case "$project" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Library"*)
    die "Refusing: $project is inside a folder that may be synced or private. Move the project to ~/dev." ;;
esac

install_helper() {
  [ -s "$conf/app-id" ] && [ -s "$conf/key.pem" ] || die "Put your agent App's id in $conf/app-id and its private key in $conf/key.pem first."
  chmod 600 "$conf/key.pem"
  origin="$(git -C "$project" remote get-url origin)"
  mkdir -p "$helper_dir"
  rm -rf "$helper_dir/agentctl"
  # Copy the tooling from the default branch, not from the working tree.
  git -C "$project" fetch --quiet origin
  default="$(git -C "$project" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
  git -C "$project" archive "$default" tools/agentctl | tar -x -C "$helper_dir" --strip-components=1
  # One helper per permission set. A sandbox is pointed at exactly one of them.
  for scope in write read; do
    cat > "$helper-$scope" <<EOF
#!/usr/bin/env bash
# Prints a one-hour "$scope" token for the agent GitHub App. Run by the sbx proxy on the host.
set -euo pipefail
export AGENT_APP_ID="\$(cat "$conf/app-id")" AGENT_APP_KEY="$conf/key.pem"
repo="\$(PYTHONPATH="$helper_dir" python3 -c 'import sys; from agentctl.apptoken import repo_from_remote; print(repo_from_remote(sys.argv[1]))' "$origin")"
PYTHONPATH="$helper_dir" exec python3 -m agentctl app-token --repo "\$repo" --profile $scope
EOF
    chmod 700 "$helper-$scope"
  done
  echo "token helpers installed in $helper_dir (tooling from $default)"
}

allow_hosts() {  # allow_hosts FILE [sbx policy options...]
  local file="$1"; shift
  while IFS= read -r line; do
    host="${line%%#*}"; host="$(echo "$host" | tr -d '[:space:]')"
    [ -z "$host" ] || sbx policy allow network "$@" "$host"
  done < "$file"
}

create() {  # create NAME HARNESS STAGE
  # What this stage may hold comes from the pinned copy of the tooling, not from the
  # checked-out branch: token scope, network, settings.
  read -r scope network settings < <(PYTHONPATH="$helper_dir" python3 -m agentctl stage-profile "$3")
  if ! sbx ls 2>/dev/null | grep -q -- "$1"; then
    (cd "$project" && sbx create --clone --name "$1" "$2" .)
  fi
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
  echo "sandbox $1: stage=$3 token=$scope network=$network settings=$settings"
}

case "${1:-}" in
  setup)
    need_sbx
    sbx settings set ssh.agentForwardingEnabled false
    sbx daemon restart
    install_helper
    # Every sandbox: source control and model providers. Registries are added per sandbox.
    allow_hosts "$here/allowlist.txt"
    if [ "${AGENT_OLLAMA:-0}" = "1" ]; then sbx policy allow network localhost:11434; fi
    echo "Done. Log in to your harnesses as the sbx documentation describes, then: sandbox/sbx.sh up claude"
    ;;
  up)
    need_sbx
    harness="${2:?usage: sbx.sh up HARNESS [STAGE]}"
    name="$(sandbox_name "$harness")"
    [ -x "$helper-write" ] || die "Run sandbox/sbx.sh setup first."
    create "$name" "$harness" "${3:-impl}"
    sbx run --name "$name"
    ;;
  job)
    need_sbx
    harness="${2:?usage: sbx.sh job HARNESS STORY STAGE PROMPT}"; story="${3:?story id}"; stage="${4:?stage}"; prompt="${5:?prompt}"
    [ -x "$helper-write" ] || die "Run sandbox/sbx.sh setup first."
    name="$(sandbox_name "$story-$stage-$harness")"
    mkdir -p "$log_dir"
    create "$name" "$harness" "$stage" > "$log_dir/$story-$stage-$harness.log" 2>&1
    case "$harness" in
      claude) set -- -p "$prompt" ;;
      codex)  set -- exec "$prompt" ;;
      ollama) set -- exec --oss --model "${OLLAMA_MODEL:-devstral}" "$prompt" ;;
      *) die "unknown harness $harness" ;;
    esac
    # Unattended: the stage's whole result is what it pushes. The sandbox is removed
    # afterwards whatever happened; the log stays on the host.
    status=0
    sbx run --name "$name" -- "$@" >> "$log_dir/$story-$stage-$harness.log" 2>&1 || status=$?
    sbx rm --force "$name" >/dev/null 2>&1 || true
    exit "$status"
    ;;
  check)
    need_sbx
    name="$(sandbox_name "${2:-claude}")"
    sbx exec "$name" -- env PYTHONPATH=/run/sandbox/source/tools python3 -m agentctl doctor --inside
    ;;
  rm)
    need_sbx
    sbx rm --force "$(sandbox_name "${2:-claude}")"
    ;;
  *)
    sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
