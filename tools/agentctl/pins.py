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
    # Any reusable workflow from another repository: the kit is the only one expected.
    uses = re.compile(r"uses:\s*['\"]?([\w.-]+/[\w.-]+)/\.github/workflows/[\w.-]+\.ya?ml@([^'\"\s#]+)")
    given = re.compile(r"kit_version:\s*['\"]?([^'\"\s#]+)")
    repos = re.compile(r"kit_repository:\s*['\"]?([^'\"\s#]+)")
    for path in sorted(Path(root, ".github/workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        calls = uses.findall(text)
        if not calls:
            continue
        for repo, ref in calls:
            if repo.lower() != repository.lower():
                problems.append(f"{path.name}: calls a reusable workflow of {repo}, not of the kit ({repository})")
            if ref != version:
                problems.append(f"{path.name}: calls {repo} at {ref}, not at the [kit] version {version}")
        inputs = given.findall(text)
        if len(inputs) != len(calls):
            problems.append(f"{path.name}: each call of the kit needs `kit_version: {version}`")
        for value in inputs:
            if value != version:
                problems.append(f"{path.name}: kit_version is {value}, not the [kit] version {version}")
        for value in repos.findall(text):
            if value.lower() != repository.lower():
                problems.append(f"{path.name}: kit_repository is {value}, not the [kit] repository {repository}")
    return problems
