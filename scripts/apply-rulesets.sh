#!/usr/bin/env bash
# Create or update the repository rulesets from .github/rulesets/*.json.
# Run by a repository admin (a human), never by an agent:
#
#   scripts/apply-rulesets.sh              # current repository
#   scripts/apply-rulesets.sh owner/repo
#
# Private repositories need the GitHub Team plan for rulesets.
#
# CONDUCTOR_APP_ID must be set: the `main-merge` ruleset lets only repository
# admins and the Conductor App update the default branch, so that an agent's
# token, which can push branches, cannot merge a pull request even when every
# check on it is green. The other ruleset, `main`, has no bypass at all, so those
# two still have to satisfy every check and approval.
set -euo pipefail

: "${CONDUCTOR_APP_ID:?set CONDUCTOR_APP_ID to the numeric id of the Conductor App}"
case "$CONDUCTOR_APP_ID" in *[!0-9]*) echo "CONDUCTOR_APP_ID must be a number" >&2; exit 1 ;; esac

repo="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.github/rulesets" && pwd)"

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
for source in "$dir"/*.json; do
  file="$work/$(basename "$source")"
  # Fill in the id of the Conductor App where a ruleset names an Integration.
  python3 -I - "$source" "$CONDUCTOR_APP_ID" > "$file" <<'PY'
import json, sys
ruleset = json.load(open(sys.argv[1]))
for actor in ruleset.get("bypass_actors", []):
    if actor.get("actor_type") == "Integration":
        actor["actor_id"] = int(sys.argv[2])
print(json.dumps(ruleset))
PY
  name="$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["name"])' "$file")"
  id="$(gh api "repos/$repo/rulesets" --jq ".[] | select(.name==\"$name\") | .id")"
  if [ -n "$id" ]; then
    gh api --method PUT "repos/$repo/rulesets/$id" --input "$file" >/dev/null
    echo "updated ruleset '$name'"
  else
    gh api --method POST "repos/$repo/rulesets" --input "$file" >/dev/null
    echo "created ruleset '$name'"
  fi
done

echo
echo "Also set, under Settings > General > Pull Requests:"
echo "  - Allow auto-merge: on"
echo "  - Allow squash merging only"
echo "  - Automatically delete head branches: on"
