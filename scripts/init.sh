#!/usr/bin/env bash
# Fill in who is on the project. Run once, right after creating a repository
# from this template:
#
#   scripts/init.sh DIRECTOR [OTHER_HUMAN ...]
#
# DIRECTOR approves product decisions (specs, sprints) and is the code owner of
# the guardrail paths. Every login given can approve a T2 change. One person is
# enough; add people later by editing policy/roles.toml and .github/CODEOWNERS.
set -euo pipefail

[ $# -ge 1 ] || { sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1; }
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
director="$1"

for login in "$@"; do
  case "$login" in
    *[!A-Za-z0-9-]*|"") echo "not a GitHub login: $login" >&2; exit 1 ;;
  esac
done

grep -q "@DIRECTOR_LOGIN" "$root/.github/CODEOWNERS" \
  || { echo "already initialised: no owner placeholder left in .github/CODEOWNERS" >&2; exit 1; }

humans=""
for login in "$@"; do humans="${humans:+$humans, }\"$login\""; done

sed -i.bak "s/@DIRECTOR_LOGIN/@$director/g" "$root/.github/CODEOWNERS"
sed -i.bak -e "s/^directors = .*/directors = [\"$director\"]/" -e "s/^humans = .*/humans = [$humans]/" "$root/policy/roles.toml"
rm -f "$root/.github/CODEOWNERS.bak" "$root/policy/roles.toml.bak"

echo "director: $director"
echo "humans:   $*"
echo "Next: review policy/roles.toml (which harness does which stage for each person), then docs/new-project.md."
