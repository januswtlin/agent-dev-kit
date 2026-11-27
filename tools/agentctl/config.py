"""The project's configuration: agentdev.toml at the repository root, over the kit's defaults.

Tables merge key by key; any other value, a list included, replaces the default
as a whole. A few things hold whatever the project writes:
  - .github/** and agentdev.toml are always guardrails (T2), so a pull request
    can never loosen the rules that judge it;
  - T2 is never in auto_merge_tiers.

Where the file is read from matters. In CI the judging jobs read it from a
checkout of the base branch (AGENTCTL_TRUSTED_ROOT), and the conductor from a
fresh checkout of the default branch, never from a pull request's tree.
"""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path

from . import ids

FILE = "agentdev.toml"
DEFAULTS = Path(__file__).with_name("defaults.toml")
ALWAYS_GUARDED = [".github/**", FILE]


def merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def defaults() -> dict:
    with open(DEFAULTS, "rb") as fh:
        return tomllib.load(fh)


def load(root: str | Path) -> dict:
    """The effective configuration for the repository at `root`."""
    path = Path(root) / FILE
    project: dict = {}
    if path.exists():
        try:
            with open(path, "rb") as fh:
                project = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise SystemExit(f"{path}: {exc}") from exc
    cfg = merge(defaults(), project)
    t2 = cfg["risk"]["t2"]
    guardrails = [str(p) for p in t2.get("guardrails", [])]
    t2["guardrails"] = guardrails + [p for p in ALWAYS_GUARDED if p not in guardrails]
    tiers = cfg["conductor"].get("auto_merge_tiers", [])
    if not isinstance(tiers, list) or not set(tiers) <= {"T0", "T1"}:
        raise SystemExit(f"{FILE}: [conductor] auto_merge_tiers may only list T0 and T1, not {tiers!r}")
    ids.configure(cfg["stories"]["id_digits"])
    return cfg


def path(cfg: dict, root: str | Path, name: str) -> Path:
    """A project path from [paths] (specs, sprints, roadmap), under `root`."""
    return Path(root) / cfg["paths"][name]
