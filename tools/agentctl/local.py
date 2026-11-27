"""The local conductor's surroundings on the Mac: credentials and a trusted checkout.

The conductor runs in a terminal on one Mac, never on GitHub Actions. It is a
deterministic program, not an agent, so it is safe to run on the host. Only one
may run per project; a lock file keeps a second one on the same Mac from starting.
Running a second conductor on another Mac is not supported (docs, known limitations).
"""

from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path


def state_dir(repo: Path) -> Path:
    from .apptoken import repo_from_remote
    remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=repo).stdout
    slug = (repo_from_remote(remote) or repo.name).replace("/", "-")
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "agent-dev" / slug


def single_instance(repo: Path):
    """Hold an exclusive lock for this project's conductor, or exit.

    The returned file object must be kept open for as long as the conductor runs.
    """
    path = state_dir(repo) / "conductor.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(f"another conductor for this project is already running on this Mac ({path})")
    return handle


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

    The conductor must read the approved sprint, specs and configuration from the default
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
