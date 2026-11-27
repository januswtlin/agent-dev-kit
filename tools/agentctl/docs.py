"""Bilingual documentation lint.

English is the source: `name.md`. The Traditional Chinese rendering sits next to
it as `name-zh-TW.md`. This check catches structural drift (a missing file, a
section added to one side only). Whether the two say the same thing is for
review; a program cannot tell.
"""

from __future__ import annotations

import re
from pathlib import Path

SUFFIX = "-zh-TW.md"

# Documents that must exist in both languages.
REQUIRED = [
    "README.md",
    "docs/guideline.md",
    "docs/new-project.md",
    "docs/new-machine.md",
    "docs/operations.md",
    "docs/threat-model.md",
    "docs/redteam-project.md",
    "docs/redteam-machine.md",
    "docs/product/domain.md",
    "sandbox/runner/README.md",
]

SKIP_DIRS = {".git", "node_modules", "reports", "__pycache__"}


def headings(text: str) -> list[int]:
    """Heading levels in order, ignoring fenced code blocks."""
    levels, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            m = re.match(r"(#{1,6})\s", line)
            if m:
                levels.append(len(m.group(1)))
    return levels


def translated(path: Path) -> Path:
    return path.with_name(path.name[: -len(".md")] + SUFFIX)


def lint(root: str | Path) -> list[str]:
    root = Path(root)
    problems: list[str] = []
    pairs: set[Path] = set()

    for rel in REQUIRED:
        source = root / rel
        if not source.exists():
            problems.append(f"{rel}: missing")
            continue
        if not translated(source).exists():
            problems.append(f"{rel}: no {translated(source).name} next to it")
            continue
        pairs.add(source)

    for zh in root.rglob(f"*{SUFFIX}"):
        if SKIP_DIRS & set(zh.relative_to(root).parts):
            continue
        source = zh.with_name(zh.name[: -len(SUFFIX)] + ".md")
        if not source.exists():
            problems.append(f"{zh.relative_to(root)}: no English source {source.name}")
        else:
            pairs.add(source)

    for source in sorted(pairs):
        zh = translated(source)
        a, b = headings(source.read_text(encoding="utf-8")), headings(zh.read_text(encoding="utf-8"))
        if a != b:
            problems.append(
                f"{source.relative_to(root)} and {zh.name} have different heading structure "
                f"({len(a)} vs {len(b)} headings); update both in the same commit"
            )
    return problems
