"""Path globs with `**` support. Patterns always match the full repo-relative path."""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=None)
def compile_glob(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i : i + 2] == "**":
                i += 2
                if pattern[i : i + 1] == "/":
                    i += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, patterns: list[str]) -> str | None:
    """Return the first pattern that matches `path`, or None."""
    for pattern in patterns:
        if compile_glob(pattern).match(path):
            return pattern
    return None
