#!/usr/bin/env bash
# Manage the FALLBACK agent sandbox VM (Lima). Run on the Mac, from the project directory.
# The primary local sandbox is Docker Sandboxes in clone mode: see sandbox/sbx.sh.
# Lima is weaker (read-write mount, address-based egress filter, App key inside the
# VM). Use it only when sbx is unavailable, and for interactive work only: the
# conductor never starts a stage in it.
#
#   sandbox/vm.sh up        create or start the VM, mount this worktree only, apply the egress allowlist
#   sandbox/vm.sh shell     open a shell inside, in /workspace
#   sandbox/vm.sh check     run the boundary checks from inside
#   sandbox/vm.sh down      stop the VM
#   sandbox/vm.sh destroy   delete the VM and everything in it
#
# Agents (claude, codex) are installed and logged in INSIDE the VM. They are
# never started from the host shell.
#
# NOT YET TESTED on a Mac. Run docs/redteam-machine.md after first setup.
set -euo pipefail

name="${AGENT_VM_NAME:-agent}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project="$(cd "$here/.." && pwd)"

case "$project" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Library"*)
    echo "Refusing: $project is inside a folder that may be synced or private. Move the project to ~/dev." >&2
    exit 1 ;;
esac

command -v limactl >/dev/null || { echo "limactl not found. Install Lima: brew install lima" >&2; exit 1; }

case "${1:-}" in
  up)
    if limactl list --quiet | grep -qx "$name"; then
      limactl start "$name"
    else
      limactl start --name "$name" --tty=false "$here/agent-vm.yaml" \
        --set ".mounts[0].location=\"$project\""
    fi
    # One long-lived VM serves every stage here, so it gets the widest list.
    limactl shell "$name" sudo sh -c 'cat /workspace/sandbox/allowlist.txt /workspace/sandbox/allowlist-build.txt > /tmp/allowlist-all.txt && /workspace/sandbox/egress.sh /tmp/allowlist-all.txt'
    echo "VM '$name' is up. Next: sandbox/vm.sh check"
    ;;
  shell)
    limactl shell --workdir /workspace "$name"
    ;;
  check)
    limactl shell --workdir /workspace "$name" bin/agentctl doctor --inside
    ;;
  down)
    limactl stop "$name"
    ;;
  destroy)
    limactl delete --force "$name"
    ;;
  *)
    sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
