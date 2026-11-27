"""Where the conductor runs: in a terminal on the Mac, or on GitHub Actions.

The conductor is a deterministic program, not an agent, so it is safe to run on
the host. Running it locally costs no Actions minutes and reacts within minutes.
Two repository variables make sure only one copy acts at a time:

    CONDUCTOR_HOME    "local" or "actions"
    CONDUCTOR_LEASE   epoch seconds of the local conductor's last completed run

`agentctl conductor here` takes over and renews the lease on every pass.
`agentctl conductor away` (or Ctrl-C) hands back to Actions. If the laptop is
closed without handing over, the lease stops being renewed and the next
scheduled Actions run takes over by itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def decide(home: str, lease: str, now: float, ttl_minutes: float) -> str:
    """What an Actions run should do: run | skip | takeover."""
    if (home or "actions").strip().lower() != "local":
        return "run"
    try:
        age = now - float(lease)
    except (TypeError, ValueError):
        return "takeover"
    return "skip" if age < ttl_minutes * 60 else "takeover"


def load_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines (dispatch secrets for local runs). The file is git-ignored."""
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
