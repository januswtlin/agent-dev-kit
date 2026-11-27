"""Bilingual documentation lint ([docs] in agentdev.toml).

English is the source: `name.md`. The translation sits next to it as
`name-<lang>.md`, for example `name-zh-TW.md`. This check catches structural drift (a missing file, a
section added to one side only). Whether the two say the same thing is for
review; a program cannot tell.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def translated(path: Path, translation: str) -> Path:
    return path.with_name(path.name[: -len(".md")] + f"-{translation}.md")


def lint(root: str | Path, translation: str = "", required: list[str] | None = None) -> list[str]:
    """Problems with the required documents and, when `translation` is set, their pairs."""
    root = Path(root)
    problems: list[str] = []
    pairs: set[Path] = set()

    for rel in required or []:
        source = root / rel
        if not source.exists():
            problems.append(f"{rel}: missing")
            continue
        if translation and not translated(source, translation).exists():
            problems.append(f"{rel}: no {translated(source, translation).name} next to it")
            continue
        pairs.add(source)
    if not translation:
        return problems
    suffix = f"-{translation}.md"

    for zh in root.rglob(f"*{suffix}"):
        if SKIP_DIRS & set(zh.relative_to(root).parts):
            continue
        source = zh.with_name(zh.name[: -len(suffix)] + ".md")
        if not source.exists():
            problems.append(f"{zh.relative_to(root)}: no English source {source.name}")
        else:
            pairs.add(source)

    for source in sorted(pairs):
        zh = translated(source, translation)
        a, b = headings(source.read_text(encoding="utf-8")), headings(zh.read_text(encoding="utf-8"))
        if a != b:
            problems.append(
                f"{source.relative_to(root)} and {zh.name} have different heading structure "
                f"({len(a)} vs {len(b)} headings); update both in the same commit"
            )
    return problems
