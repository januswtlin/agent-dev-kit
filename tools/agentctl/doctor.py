"""Host and sandbox hygiene checks.

`agentctl doctor`          run on the Mac: is the host set up so agents cannot reach private data?
`agentctl doctor --inside` run inside the sandbox VM: is the boundary actually holding?
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "FAIL"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return proc.returncode, proc.stdout + proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def host_checks(project: Path) -> list[tuple[str, str, str]]:
    results = []
    home = Path.home()
    project = project.resolve()

    synced = [home / "Documents", home / "Desktop", home / "Library/Mobile Documents", home / "Library/CloudStorage"]
    inside = next((p for p in synced if p in project.parents or p == project), None)
    results.append(("project location", FAIL if inside else OK,
                    f"{project} is under {inside}, which may be synced to the cloud; move it to ~/dev" if inside
                    else f"{project} is outside synced folders"))

    if platform.system() == "Darwin":
        # Reading these folders only works when the terminal has Full Disk Access,
        # a permission every agent started from that terminal would inherit.
        protected = [home / "Library/Mail", home / "Library/Safari", home / "Library/Messages"]
        readable = [p for p in protected if p.exists() and os.access(p, os.R_OK) and _listable(p)]
        results.append(("full disk access", FAIL if readable else OK,
                        "this terminal can read " + ", ".join(map(str, readable)) + "; remove Full Disk Access for it"
                        if readable else "terminal does not have Full Disk Access"))

        code, out = _run(["tmutil", "destinationinfo"])
        has_backup = code == 0 and "Name" in out
        results.append(("backup", OK if has_backup else WARN,
                        "Time Machine destination configured" if has_backup
                        else "no Time Machine destination found; make sure another backup exists"))
    else:
        results.append(("platform", WARN, f"host checks are written for macOS; running on {platform.system()}"))

    sandbox = shutil.which("sbx") or shutil.which("limactl")
    results.append(("sandbox runtime", OK if sandbox else FAIL,
                    f"found {sandbox}" if sandbox else "neither sbx (Docker Sandboxes) nor limactl (Lima) is installed"))

    for name in ("claude", "codex"):
        path = shutil.which(name)
        if path:
            results.append((f"{name} on host", WARN,
                            f"{path} is installed on the host; run it only inside the sandbox (see docs/guideline.md)"))
    return results


def _listable(path: Path) -> bool:
    try:
        next(iter(path.iterdir()), None)
        return True
    except OSError:
        return False


PRIVATE_MARKERS = ("Documents", "Desktop", "Downloads", "Library", "Pictures", ".ssh", ".aws")
REAL_TOKEN_PREFIXES = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")
CLONE_SOURCE = Path("/run/sandbox/source")


def looks_like_real_github_token(value: str | None) -> bool:
    """True for an actual GitHub credential, False for a proxy placeholder or nothing."""
    return bool(value) and value.startswith(REAL_TOKEN_PREFIXES)


def private_host_paths(users_root: Path) -> list[str]:
    """Private folders of a host user that are visible from here.

    A direct mount exposes the path down to the project and nothing else, so the
    mere existence of /Users/<name> is fine. Seeing Documents or Library is not.
    """
    found = []
    if users_root.exists() and _listable(users_root):
        for home in users_root.iterdir():
            for marker in PRIVATE_MARKERS:
                candidate = home / marker
                if candidate.exists() and _listable(candidate):
                    found.append(str(candidate))
    return found


def inside_checks(blocked_url: str = "https://example.com") -> list[tuple[str, str, str]]:
    results = []
    visible = private_host_paths(Path("/Users"))
    results.append(("host home", FAIL if visible else OK,
                    "private host folders are visible: " + ", ".join(visible) if visible
                    else "no private host folder is visible"))

    if CLONE_SOURCE.exists():
        writable = os.access(CLONE_SOURCE, os.W_OK)
        results.append(("workspace", FAIL if writable else OK,
                        f"{CLONE_SOURCE} is writable; clone mode should mount the repository read-only" if writable
                        else "clone mode: the host repository is read-only, work happens on a private clone"))
    else:
        results.append(("workspace", WARN,
                        "the workspace is mounted from the host and writable: the agent can change files on the "
                        "Mac, including .git/hooks. Prefer clone mode (sandbox/sbx.sh)"))

    secrets = [p for p in (Path.home() / ".ssh", Path.home() / ".aws", Path.home() / ".config/gcloud")
               if p.exists() and any(p.iterdir())]
    results.append(("credentials", FAIL if secrets else OK,
                    "found credential folders: " + ", ".join(map(str, secrets)) if secrets
                    else "no SSH or cloud credential folders present"))

    if os.environ.get("SSH_AUTH_SOCK") and shutil.which("ssh-add"):
        code, _ = _run(["ssh-add", "-l"])
        results.append(("ssh agent", FAIL if code == 0 else OK,
                        "a forwarded SSH agent with keys is reachable: the agent could push as you. "
                        "Turn off SSH agent forwarding" if code == 0 else "no usable SSH agent"))
    else:
        results.append(("ssh agent", OK, "no SSH agent is forwarded"))

    real = [name for name in ("GH_TOKEN", "GITHUB_TOKEN") if looks_like_real_github_token(os.environ.get(name))]
    results.append(("github token", WARN if real else OK,
                    f"{', '.join(real)} holds a real GitHub token inside the sandbox; with sbx the proxy should "
                    "inject it and the sandbox should only see a placeholder" if real
                    else "no real GitHub token in the environment"))

    try:
        urllib.request.urlopen(blocked_url, timeout=8)
        results.append(("egress", FAIL, f"{blocked_url} is reachable; the egress allowlist is not enforced"))
    except (urllib.error.URLError, OSError):
        results.append(("egress", OK, f"{blocked_url} is blocked"))
    return results


def report(results: list[tuple[str, str, str]]) -> int:
    for name, status, detail in results:
        print(f"[{status:>4}] {name}: {detail}")
    return 1 if any(status == FAIL for _, status, _ in results) else 0
