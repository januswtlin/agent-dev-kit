#!/usr/bin/env bash
# Create or update a project's rulesets from the kit's templates/rulesets/*.json.
# Run by a repository admin (a human), never by an agent, from inside the project:
#
#   agentctl rulesets 2 [owner/repo]    layer 2: main, main-merge, release-tags
#   agentctl rulesets 3 [owner/repo]    layer 3: main-checks (the required checks)
#
# Layer 3's ruleset requires the checks the caller workflows produce, so apply it
# only once those workflows are on the default branch and have run.
#
# Private repositories need the GitHub Team plan for rulesets.
#
# For layer 2, CONDUCTOR_APP_ID must be set: the `main-merge` ruleset lets only
# repository admins and the Conductor App update the default branch, so that an
# agent's token, which can push branches, cannot merge a pull request even when
# every check on it is green. `main` has no bypass at all, so those two still have
# to satisfy every check and approval.
set -euo pipefail

layer="${1:-}"
case "$layer" in
  2) names="main main-merge release-tags" ;;
  3) names="main-checks" ;;
  *) sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 1 ;;
esac
if [ "$layer" = 2 ]; then
  : "${CONDUCTOR_APP_ID:?set CONDUCTOR_APP_ID to the numeric id of the Conductor App}"
  case "$CONDUCTOR_APP_ID" in *[!0-9]*) echo "CONDUCTOR_APP_ID must be a number" >&2; exit 1 ;; esac
fi

repo="${2:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../templates/rulesets" && pwd)"

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
for ruleset in $names; do
  source="$dir/$ruleset.json"
  file="$work/$ruleset.json"
  # Fill in the id of the Conductor App where a ruleset names an Integration.
  python3 -I - "$source" "${CONDUCTOR_APP_ID:-0}" > "$file" <<'PY'
import json, sys
ruleset = json.load(open(sys.argv[1]))
for actor in ruleset.get("bypass_actors", []):
    if actor.get("actor_type") == "Integration":
        actor["actor_id"] = int(sys.argv[2])
print(json.dumps(ruleset))
PY
  id="$(gh api "repos/$repo/rulesets" --jq ".[] | select(.name==\"$ruleset\") | .id")"
  if [ -n "$id" ]; then
    gh api --method PUT "repos/$repo/rulesets/$id" --input "$file" >/dev/null
    echo "updated ruleset '$ruleset'"
  else
    gh api --method POST "repos/$repo/rulesets" --input "$file" >/dev/null
    echo "created ruleset '$ruleset'"
  fi
done

if [ "$layer" = 2 ]; then
  echo
  echo "Also set, under Settings > General > Pull Requests:"
  echo "  - Allow auto-merge: on"
  echo "  - Allow squash merging only"
  echo "  - Automatically delete head branches: on"
fi
