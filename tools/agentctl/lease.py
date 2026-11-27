"""Where the conductor runs: in a terminal on the Mac, or on GitHub Actions.

The conductor is a deterministic program, not an agent, so it is safe to run on
the host. Running it locally costs no Actions minutes and reacts within minutes.
Two repository variables make sure only one copy acts at a time:

    CONDUCTOR_HOME    "local" or "actions"
    CONDUCTOR_LEASE   epoch seconds of the local conductor's last completed run

`agentctl conductor here` takes the lease (naming this process as the holder),
renews it after every pass that worked, and stops as soon as the lease names
someone else. `agentctl conductor away` (or Ctrl-C) hands back to Actions. If the
laptop is closed without handing over, or the local passes keep failing, the
lease stops being renewed and the next scheduled Actions run takes over.

Repository variables are not a lock: there is no compare-and-set. Two conductors
can overlap for one pass around a hand-over. Dispatches are recorded before they
are sent and each stage waits for its marker to expire, so the cost of an
overlap is at worst one duplicated dispatch, never a lost one.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def parse(value: str) -> tuple[float | None, str]:
    """A lease is "<epoch seconds> <holder>". Returns (when, who)."""
    parts = (value or "").split(None, 1)
    try:
        return float(parts[0]), (parts[1] if len(parts) > 1 else "")
    except (IndexError, ValueError):
        return None, ""


def decide(home: str, lease: str, now: float, ttl_minutes: float) -> str:
    """What an Actions run should do: run | skip | takeover."""
    if (home or "actions").strip().lower() != "local":
        return "run"
    when, _ = parse(lease)
    if when is None:
        return "takeover"
    return "skip" if now - when < ttl_minutes * 60 else "takeover"


def still_mine(home: str, lease: str, holder: str) -> bool:
    """A local conductor keeps going only while the lease names it."""
    return (home or "").strip().lower() == "local" and parse(lease)[1] == holder


def conductor_env_path(repo: Path) -> Path:
    """Where the local conductor's dispatch credentials live: outside the repository.

    A clone-mode sandbox sees the whole repository directory read-only, ignored
    files included, so a .env file in the project would be readable by every agent.
    """
    from .apptoken import repo_from_remote
    remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=repo).stdout
    slug = (repo_from_remote(remote) or repo.name).replace("/", "-")
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "agent-dev" / slug / "conductor.env"


def load_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines (dispatch secrets for local runs)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fresh_main_checkout(repo: Path, branch: str = "main") -> Path:
    """A detached worktree of origin/<branch>, refreshed on every call.

    The conductor must read the approved sprint, specs and policy from the default
    branch, never from whatever happens to be checked out in the working directory.
    """
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            check=True, capture_output=True, text=True, cwd=repo).stdout.strip()
    worktree = Path(common) / "agentctl-main"
    subprocess.run(["git", "fetch", "--quiet", "origin", branch], check=True, cwd=repo)
    if not (worktree / ".git").exists():
        subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(worktree), f"origin/{branch}"],
                       check=True, cwd=repo)
    else:
        subprocess.run(["git", "checkout", "--quiet", "--detach", f"origin/{branch}"], check=True, cwd=worktree)
    return worktree
