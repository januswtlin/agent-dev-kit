"""Story specs: <specs dir>/NNN-slug/{story.md, spec.toml}, NNN being [stories] id_digits long.

spec.toml is the machine-readable half of what the product owner approves:
acceptance criteria, test case descriptions and scheduling metadata.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import ids

STORY_MAX_LINES = 80


@dataclass
class TestCase:
    id: str
    ac: list[str]
    level: str
    text: str
    red_exempt: bool = False


@dataclass
class Spec:
    id: str
    slug: str
    title: str
    path: Path
    priority: int = 100
    size: str = "M"
    risk: str = "T1"
    depends_on: list[str] = field(default_factory=list)
    touches: list[str] = field(default_factory=list)
    ac: dict[str, str] = field(default_factory=dict)
    tc: list[TestCase] = field(default_factory=list)
    done_when: list[dict] = field(default_factory=list)

    @property
    def tc_ids(self) -> list[str]:
        return [t.id for t in self.tc]


def load_spec(spec_toml: str | Path) -> Spec:
    spec_toml = Path(spec_toml)
    with open(spec_toml, "rb") as fh:
        raw = tomllib.load(fh)
    return Spec(
        id=str(raw["id"]),
        slug=raw.get("slug", ""),
        title=raw.get("title", ""),
        path=spec_toml.parent,
        priority=int(raw.get("priority", 100)),
        size=raw.get("size", "M"),
        risk=raw.get("risk", "T1"),
        depends_on=[str(d) for d in raw.get("depends_on", [])],
        touches=list(raw.get("touches", [])),
        ac={a["id"]: a.get("text", "") for a in raw.get("ac", [])},
        tc=[
            TestCase(t["id"], list(t.get("ac", [])), t.get("level", "unit"), t.get("text", ""),
                     bool(t.get("red_exempt", False)))
            for t in raw.get("tc", [])
        ],
        done_when=list(raw.get("done_when", [])),
    )


def load_all(specs_dir: str | Path) -> dict[str, Spec]:
    specs: dict[str, Spec] = {}
    for spec_toml in sorted(Path(specs_dir).glob("*/spec.toml")):
        if spec_toml.parent.name.startswith("_"):
            continue
        spec = load_spec(spec_toml)
        specs[spec.id] = spec
    return specs


def load_retired(specs_dir: str | Path) -> set[str]:
    """Test case ids a human agreed to drop: <specs dir>/retired.toml, `retired = ["TC-012-03"]`."""
    path = Path(specs_dir) / "retired.toml"
    if not path.exists():
        return set()
    with open(path, "rb") as fh:
        return {str(x) for x in tomllib.load(fh).get("retired", [])}


def find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return one dependency cycle as a list of ids, or None."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in graph:
                continue
            if state.get(dep) == 1:
                return stack[stack.index(dep):] + [dep]
            if state.get(dep) is None:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in sorted(graph):
        if state.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def _ids_in_order(text: str) -> list[str]:
    seen: list[str] = []
    for m in ids.ANY_ID_RE.finditer(text):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    return seen


def _heading_levels(text: str) -> list[int]:
    return [len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s", text, re.MULTILINE)]


def lint(specs_dir: str | Path, changed: set[str] | None = None, translation: str = "zh-TW",
         max_lines: int = STORY_MAX_LINES) -> list[str]:
    """Consistency checks run on every spec PR. Returns a list of problems.

    `changed` is the set of file paths (relative to the repository root, forward
    slashes) touched by the pull request. When given, a story edited in one
    language only is reported. `translation` names the language of the version
    the director approves (story-<translation>.md); empty means there is none.
    """
    story_zh = f"story-{translation}.md" if translation else ""
    problems: list[str] = []
    specs_dir = Path(specs_dir)
    specs: dict[str, Spec] = {}

    for spec_toml in sorted(specs_dir.glob("*/spec.toml")):
        folder = spec_toml.parent
        if folder.name.startswith("_"):
            continue
        try:
            spec = load_spec(spec_toml)
        except (KeyError, tomllib.TOMLDecodeError, ValueError) as exc:
            problems.append(f"{spec_toml}: cannot parse ({exc})")
            continue
        where = f"spec {spec.id}"
        if spec.id in specs:
            problems.append(f"{where}: duplicate id (also in {specs[spec.id].path})")
        specs[spec.id] = spec

        if not ids.is_story(spec.id):
            problems.append(f"{where}: id must be {ids.DIGITS} digits")
        if not folder.name.startswith(f"{spec.id}-"):
            problems.append(f"{where}: folder {folder.name} must start with '{spec.id}-'")
        if not spec.touches:
            problems.append(f"{where}: 'touches' is empty; the scheduler needs it to avoid parallel conflicts")
        if spec.risk not in ("T0", "T1", "T2"):
            problems.append(f"{where}: risk must be T0, T1 or T2")

        if not spec.ac:
            problems.append(f"{where}: no acceptance criteria")
        if not spec.tc:
            problems.append(f"{where}: no test cases")
        for ac_id in spec.ac:
            m = ids.AC_RE.fullmatch(ac_id)
            if not m or m.group(1) != spec.id:
                problems.append(f"{where}: bad AC id {ac_id} (expected AC-{spec.id}-N)")
        seen_tc: set[str] = set()
        covered: set[str] = set()
        for tc in spec.tc:
            m = ids.TC_RE.fullmatch(tc.id)
            if not m or m.group(1) != spec.id:
                problems.append(f"{where}: bad TC id {tc.id} (expected TC-{spec.id}-NN)")
            if tc.id in seen_tc:
                problems.append(f"{where}: duplicate {tc.id}")
            seen_tc.add(tc.id)
            if tc.level not in ("unit", "integration", "e2e"):
                problems.append(f"{where}: {tc.id} has unknown level '{tc.level}'")
            if not tc.ac:
                problems.append(f"{where}: {tc.id} is not linked to any AC")
            for ac_id in tc.ac:
                if ac_id not in spec.ac:
                    problems.append(f"{where}: {tc.id} references unknown {ac_id}")
                covered.add(ac_id)
        for ac_id in spec.ac:
            if ac_id not in covered:
                problems.append(f"{where}: {ac_id} has no test case")

        story = folder / "story.md"
        if not story.exists():
            problems.append(f"{where}: story.md is missing")
        else:
            text = story.read_text(encoding="utf-8")
            mentioned = {m.group(0) for m in ids.AC_RE.finditer(text)} | {m.group(0) for m in ids.TC_RE.finditer(text)}
            declared = set(spec.ac) | seen_tc
            for missing in sorted(declared - mentioned):
                problems.append(f"{where}: {missing} is in spec.toml but not in story.md")
            for extra in sorted(mentioned - declared):
                problems.append(f"{where}: {extra} is in story.md but not in spec.toml")
            lines = text.count("\n") + 1
            if lines > max_lines:
                problems.append(f"{where}: story.md has {lines} lines; keep it within {max_lines} so it can be reviewed on one screen")

            # The director reads and approves the translated rendering; agents build
            # from the English one. They must at least have the same shape.
            zh_path = folder / story_zh if story_zh else None
            if zh_path and not zh_path.exists():
                problems.append(f"{where}: {story_zh} is missing")
            elif zh_path:
                zh = zh_path.read_text(encoding="utf-8")
                if _ids_in_order(zh) != _ids_in_order(text):
                    problems.append(f"{where}: story.md and {story_zh} do not list the same AC/TC ids in the same order")
                if _heading_levels(zh) != _heading_levels(text):
                    problems.append(f"{where}: story.md and {story_zh} have different sections")
                zh_lines = zh.count("\n") + 1
                if zh_lines > max_lines:
                    problems.append(f"{where}: {story_zh} has {zh_lines} lines; keep it within {max_lines}")
                if changed is not None:
                    touched = {name for name in ("story.md", story_zh)
                               if any(path.endswith(f"/{folder.name}/{name}") for path in changed)}
                    if len(touched) == 1:
                        other = story_zh if "story.md" in touched else "story.md"
                        problems.append(f"{where}: {touched.pop()} changed but {other} did not; update both together")

    for spec in specs.values():
        for dep in spec.depends_on:
            if dep not in specs:
                problems.append(f"spec {spec.id}: depends_on unknown story {dep}")
    cycle = find_cycle({s.id: s.depends_on for s in specs.values()})
    if cycle:
        problems.append("dependency cycle: " + " -> ".join(cycle))
    return problems
