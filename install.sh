#!/usr/bin/env bash
# Install one version of the kit on this Mac, outside every project.
#
#   ./install.sh [REF]     REF: a commit, branch or tag of this clone (default: HEAD)
#
# Run it from a clone of the kit. The version is unpacked, by its full commit SHA,
# into ~/.local/share/agent-dev-kit/versions/<sha>/ and made read-only, and the
# `agentctl` launcher is put in ~/.local/bin. Several versions can sit side by
# side: each project names the one it uses in agentdev.toml ([kit] version), and
# the launcher runs that one.
#
# Why outside the project: the tools run on the Mac with your permissions, and
# an agent can change anything in a project's tree. Code an agent cannot change
# needs no "is this checkout trusted" check.
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
data="${AGENTDEV_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/agent-dev-kit}"
bindir="${AGENTDEV_BIN:-$HOME/.local/bin}"

ref="${1:-HEAD}"
sha="$(git -C "$src" rev-parse --verify --quiet "$ref^{commit}")" || { echo "not a commit in $src: $ref" >&2; exit 1; }
dest="$data/versions/$sha"

if [ -f "$dest/tools/run.py" ]; then
  echo "kit $sha is already installed in $dest"
else
  mkdir -p "$data/versions"
  tmp="$(mktemp -d "$data/versions/.tmp.XXXXXX")"
  git -C "$src" archive "$sha" | tar -x -C "$tmp"
  printf '%s\n' "$sha" > "$tmp/.kit-version"
  mv "$tmp" "$dest"
  # Read-only, so nothing run later (by you or by a tool) edits it by accident.
  # To remove a version: chmod -R u+w "$dest" && rm -rf "$dest"
  chmod -R a-w "$dest"
  echo "installed kit $sha in $dest"
fi

mkdir -p "$bindir"
# Replace, never edit in place: a running launcher must not see a half-written file.
cp "$dest/libexec/agentctl" "$bindir/.agentctl.new"
chmod 755 "$bindir/.agentctl.new"
mv -f "$bindir/.agentctl.new" "$bindir/agentctl"
echo "launcher: $bindir/agentctl"
case ":$PATH:" in *":$bindir:"*) ;; *) echo "add $bindir to your PATH" ;; esac
echo "In a project, set [kit] version = \"$sha\" in agentdev.toml (on its default branch)."
