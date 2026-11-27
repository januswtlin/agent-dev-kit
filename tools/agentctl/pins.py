"""One kit version per project: agentdev.toml, and every workflow that calls the kit.

A caller workflow names the kit twice, in `uses: <kit>/.github/workflows/x.yml@<sha>`
and in `kit_version: <sha>`, the second being what the called workflow checks out.
All of them must be the [kit] version, so that the workflows judge with the same
code the Mac runs.
"""

from __future__ import annotations

import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")


def check(root: str | Path, repository: str, version: str) -> list[str]:
    problems: list[str] = []
    if not SHA.match(version or ""):
        return [f"[kit] version in agentdev.toml must be a full 40-character commit SHA, not {version!r}"]
    uses = re.compile(rf"uses:\s*{re.escape(repository)}/\.github/workflows/[\w.-]+\.ya?ml@(\S+)", re.IGNORECASE)
    given = re.compile(r"kit_version:\s*['\"]?([^'\"\s#]+)")
    for path in sorted(Path(root, ".github/workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        refs = uses.findall(text)
        if not refs:
            continue
        for ref in refs:
            if ref != version:
                problems.append(f"{path.name}: calls the kit at {ref}, not at the [kit] version {version}")
        inputs = given.findall(text)
        if len(inputs) != len(refs):
            problems.append(f"{path.name}: each call of the kit needs `kit_version: {version}`")
        for value in inputs:
            if value != version:
                problems.append(f"{path.name}: kit_version is {value}, not the [kit] version {version}")
    return problems
