"""Story, acceptance-criterion and test-case ids, and the patterns that find them.

A story id is a fixed number of digits (`[stories] id_digits` in agentdev.toml,
3 by default): story 012 has acceptance criteria AC-012-1, AC-012-2 and test
cases TC-012-01, TC-012-02. The patterns are module attributes, rebuilt by
`configure`, so read them as `ids.TC_RE` at the moment of use, never import them
by name.
"""

from __future__ import annotations

import re

DIGITS = 3
STORY_RE: re.Pattern[str] = re.compile("")
AC_RE: re.Pattern[str] = re.compile("")
TC_RE: re.Pattern[str] = re.compile("")
ANY_ID_RE: re.Pattern[str] = re.compile("")
TC_IN_TEST_RE: re.Pattern[str] = re.compile("")
STORY_BRANCH_RE: re.Pattern[str] = re.compile("")


def configure(digits: int = 3) -> None:
    global DIGITS, STORY_RE, AC_RE, TC_RE, ANY_ID_RE, TC_IN_TEST_RE, STORY_BRANCH_RE
    if not isinstance(digits, int) or not 2 <= digits <= 6:
        raise SystemExit(f"[stories] id_digits must be a whole number from 2 to 6, not {digits!r}")
    DIGITS = digits
    d = f"\\d{{{digits}}}"
    STORY_RE = re.compile(d)
    AC_RE = re.compile(rf"\bAC-({d})-(\d+)\b")
    TC_RE = re.compile(rf"\bTC-({d})-(\d{{2}})\b")
    ANY_ID_RE = re.compile(rf"\b(?:AC-{d}-\d+|TC-{d}-\d{{2}})\b")
    # A test carries its TC id in its name, class name or file name. Many languages
    # forbid '-' in identifiers, so TC-012-03, tc_012_03 and TC01203 all count.
    TC_IN_TEST_RE = re.compile(rf"(?<![A-Za-z0-9])TC[-_ ]?({d})[-_ ]?(\d{{2}})(?!\d)", re.IGNORECASE)
    STORY_BRANCH_RE = re.compile(rf"^(?:refs/heads/)?story/({d})(?:-[A-Za-z0-9._-]*)?$")


def is_story(value: str) -> bool:
    return bool(STORY_RE.fullmatch(value))


def story_from_branch(branch: str | None) -> str | None:
    m = STORY_BRANCH_RE.match(branch or "")
    return m.group(1) if m else None


configure()
