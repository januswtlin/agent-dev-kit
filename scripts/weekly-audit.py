#!/usr/bin/env python3
"""Weekly audit lines for the director's brief.

Reads merged pull requests as JSON on stdin (gh pr list --json number,title,labels).
"""

import json
import random
import sys


def tier(pr: dict) -> str:
    return next((label["name"] for label in pr["labels"] if label["name"].startswith("tier:")), "untiered")


def main() -> None:
    prs = json.load(sys.stdin)
    counts: dict[str, int] = {}
    for pr in prs:
        counts[tier(pr)] = counts.get(tier(pr), 0) + 1
    print("- Merged:", ", ".join(f"{name} {count}" for name, count in sorted(counts.items())) or "none")
    print("- Reverts:", sum(1 for pr in prs if pr["title"].lower().startswith("revert")))
    unattended = [pr for pr in prs if tier(pr) in ("tier:T0", "tier:T1")]
    print("- Audit sample (merged without a human; open these and judge them yourself):")
    for pr in random.sample(unattended, min(3, len(unattended))):
        print(f"  - #{pr['number']} {pr['title']}")


if __name__ == "__main__":
    main()
