"""Short-lived GitHub token for an agent, minted from a GitHub App.

Each developer has their own GitHub App for their agents ("alice-agent"). An App
is a better agent identity than a personal token or an extra user account:

  - its permissions are exactly what it was granted (no Workflows, no
    Administration, no Commit statuses), whatever the developer's own role is
  - its tokens expire after an hour
  - commits and comments show which developer's agent made them
  - it does not take a seat

The private key signs a JWT; GitHub exchanges the JWT for an installation token.
Signing uses the `openssl` command so this stays free of dependencies.

Configuration, from the environment:
    AGENT_APP_ID    the App's id (or client id)
    AGENT_APP_KEY   path to the App's private key (.pem)
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

API = "https://api.github.com"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "agentctl" / "app-token.json"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(app_id: str, key_path: str | Path, now: float | None = None) -> str:
    """A JWT identifying the App, valid for nine minutes (GitHub allows at most ten)."""
    now = int(now if now is not None else time.time())
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key_path)],
                               input=signing_input, capture_output=True, check=True).stdout
    return f"{header}.{payload}.{_b64(signature)}"


def repo_from_remote(url: str) -> str | None:
    """owner/name from an HTTPS or SSH GitHub remote URL."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _call(method: str, url: str, bearer: str) -> dict:
    request = urllib.request.Request(url, method=method, headers={
        "Authorization": f"Bearer {bearer}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "agentctl"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _fresh(cached: dict, repo: str, app_id: str, now: float, margin: float = 300) -> bool:
    return (cached.get("repo") == repo and str(cached.get("app_id")) == str(app_id)
            and float(cached.get("expires", 0)) - now > margin)


def installation_token(app_id: str, key_path: str | Path, repo: str, now: float | None = None) -> str:
    """Return a token for the App's installation on `repo`, reusing a cached one while it is valid."""
    now = now if now is not None else time.time()
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if _fresh(cached, repo, app_id, now):
            return cached["token"]
    except (OSError, ValueError, KeyError):
        pass
    jwt = make_jwt(app_id, key_path, now)
    installation = _call("GET", f"{API}/repos/{repo}/installation", jwt)
    granted = _call("POST", f"{API}/app/installations/{installation['id']}/access_tokens", jwt)
    expires = time.mktime(time.strptime(granted["expires_at"], "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.touch(mode=0o600, exist_ok=True)
    os.chmod(CACHE, 0o600)
    CACHE.write_text(json.dumps({"repo": repo, "app_id": str(app_id), "token": granted["token"], "expires": expires}),
                     encoding="utf-8")
    return granted["token"]
