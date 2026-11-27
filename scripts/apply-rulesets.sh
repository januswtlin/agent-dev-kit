#!/usr/bin/env bash
# Create or update the repository rulesets from .github/rulesets/*.json.
# Run by a repository admin (a human), never by an agent:
#
#   scripts/apply-rulesets.sh              # current repository
#   scripts/apply-rulesets.sh owner/repo
#
# Private repositories need the GitHub Team plan for rulesets.
set -euo pipefail

repo="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.github/rulesets" && pwd)"

for file in "$dir"/*.json; do
  name="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["name"])' "$file")"
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
