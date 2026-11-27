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


def inside_checks(blocked_url: str = "https://example.com") -> list[tuple[str, str, str]]:
    results = []
    mac_home = Path("/Users")
    visible = [str(p) for p in mac_home.iterdir()] if mac_home.exists() and _listable(mac_home) else []
    results.append(("host home", FAIL if visible else OK,
                    "host home directories are visible: " + ", ".join(visible) if visible
                    else "no host home directory is mounted"))

    secrets = [p for p in (Path.home() / ".ssh", Path.home() / ".aws", Path.home() / ".config/gcloud")
               if p.exists() and any(p.iterdir())]
    results.append(("credentials", FAIL if secrets else OK,
                    "found credential folders: " + ", ".join(map(str, secrets)) if secrets
                    else "no SSH or cloud credential folders present"))

    try:
        urllib.request.urlopen(blocked_url, timeout=8)
        results.append(("egress", FAIL, f"{blocked_url} is reachable; the egress allowlist is not enforced"))
    except (urllib.error.URLError, OSError):
        results.append(("egress", OK, f"{blocked_url} is blocked"))

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and shutil.which("gh"):
        code, out = _run(["gh", "api", "user/repos", "--jq", "length"])
        count = out.strip()
        results.append(("github token", WARN if code == 0 and count not in ("", "0", "1") else OK,
                        f"token can list {count} repositories; it should be a fine-grained token for this repository only"
                        if code == 0 and count not in ("", "0", "1") else "token scope looks narrow"))
    return results


def report(results: list[tuple[str, str, str]]) -> int:
    for name, status, detail in results:
        print(f"[{status:>4}] {name}: {detail}")
    return 1 if any(status == FAIL for _, status, _ in results) else 0
