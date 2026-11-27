"""Risk tiering of a change set, driven by policy/risk-tiers.toml.

T0: documentation-only. Merges when checks are green.
T1: ordinary code change tied to an approved story. Merges when checks and agent review pass.
T2: needs a human approval.
"""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .globs import matches


@dataclass(frozen=True)
class Change:
    path: str
    added: int = 0
    deleted: int = 0


@dataclass
class Assessment:
    tier: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"tier": self.tier, "reasons": self.reasons}


def load_policy(path: str | Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def assess(changes: list[Change], policy: dict, has_story: bool) -> Assessment:
    if not changes:
        return Assessment("T0", ["empty change set"])

    t2 = policy.get("t2", {})
    reasons: list[str] = []

    for group in ("guardrails", "human_gated", "high_risk", "dependency_manifests"):
        patterns = t2.get(group, [])
        hits = sorted({c.path for c in changes if matches(c.path, patterns)})
        if hits:
            shown = ", ".join(hits[:5]) + (" ..." if len(hits) > 5 else "")
            reasons.append(f"{group}: {shown}")

    limits = policy.get("thresholds", {})
    ignore = limits.get("ignore_for_size", [])
    sized = [c for c in changes if not matches(c.path, ignore)]
    lines = sum(c.added + c.deleted for c in sized)
    if lines > limits.get("max_changed_lines", 600):
        reasons.append(f"size: {lines} changed lines exceeds {limits.get('max_changed_lines', 600)}")
    if len(sized) > limits.get("max_changed_files", 40):
        reasons.append(f"size: {len(sized)} files exceeds {limits.get('max_changed_files', 40)}")

    t0_patterns = policy.get("t0", {}).get("paths", [])
    all_t0 = all(matches(c.path, t0_patterns) for c in changes)

    if not all_t0 and not has_story:
        reasons.append("no approved story: a code change must reference a story (branch story/NNN-*)")

    if reasons:
        return Assessment("T2", reasons)
    if all_t0:
        return Assessment("T0", ["documentation-only change"])
    return Assessment("T1", ["code change within an approved story"])


def changes_from_git(base: str, head: str = "HEAD", cwd: str | None = None) -> list[Change]:
    out = subprocess.run(
        ["git", "diff", "--numstat", "--no-renames", f"{base}...{head}"],
        check=True, capture_output=True, text=True, cwd=cwd,
    ).stdout
    changes = []
    for line in out.splitlines():
        added, deleted, path = line.split("\t", 2)
        changes.append(Change(path, 0 if added == "-" else int(added), 0 if deleted == "-" else int(deleted)))
    return changes
