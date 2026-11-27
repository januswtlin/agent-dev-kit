#!/usr/bin/env bash
# PreToolUse hook for Bash: block commands that are destructive or that reach
# outside the repository. Exit code 2 blocks the call and shows stderr to the agent.
#
# This is a second layer. The real boundary is the sandbox VM and the token scope;
# a pattern list like this one can always be worked around.
set -euo pipefail

command="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))')"

deny() {
  echo "Blocked by .claude/hooks/guard.sh: $1" >&2
  echo "If this is needed for the story, stop and report it on the story issue." >&2
  exit 2
}

# The patterns are literal regular expressions, so nothing in them should expand.
# shellcheck disable=SC2016
patterns=(
  'rm[[:space:]]+(-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+)+("|'"'"')?(/|~|\$HOME|\.\.)|recursive delete outside the repository'
  'git[[:space:]]+push[[:space:]].*(--force|-f([[:space:]]|$)|--force-with-lease)|force push'
  'git[[:space:]]+push[[:space:]].*[[:space:]](main|master)([[:space:]]|$)|push to the default branch'
  'git[[:space:]]+push[[:space:]].*(--delete|[[:space:]]:[^[:space:]])|deleting a remote branch'
  'git[[:space:]]+(tag|reset[[:space:]]+--hard[[:space:]]+origin|clean[[:space:]]+-[a-zA-Z]*f[a-zA-Z]*d|filter-branch|filter-repo)|history or tag manipulation'
  'gh[[:space:]]+(pr[[:space:]]+(merge|review|create)|repo[[:space:]]+(delete|edit)|secret|ruleset|api[[:space:]].*(-X|--method)[[:space:]]*(DELETE|PUT|PATCH))|GitHub administration'
  '(^|[;&|[:space:]])(sudo|aws|gcloud|az|terraform|kubectl|doctl|flyctl|heroku|vercel|railway)([[:space:]]|$)|cloud or privileged command'
  '(psql|mysql|mariadb|sqlite3|mongosh|redis-cli)[^;&|]*(drop[[:space:]]+(database|table|schema)|truncate[[:space:]]|flushall|dropdatabase)|destructive database command'
  '(~|\$HOME|/Users/[^/]+)/(\.ssh|\.aws|\.config/gcloud|\.gnupg|Library|Documents|Desktop|Downloads)|reading private host data'
  '(curl|wget)[^|]*\|[[:space:]]*(ba|z)?sh|piping a download into a shell'
)

lowered="$(printf '%s' "$command" | tr '[:upper:]' '[:lower:]')"
for entry in "${patterns[@]}"; do
  regex="${entry%|*}"
  reason="${entry##*|}"
  if printf '%s' "$lowered" | grep -Eq -- "$(printf '%s' "$regex" | tr '[:upper:]' '[:lower:]')"; then
    deny "$reason"
  fi
done
exit 0
