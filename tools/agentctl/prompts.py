"""Stage prompts: the kit's prompts/<stage>.md, filled in with the project's settings.

The prompts belong to the kit, not to the project, so the text sent to an agent
carries the whole prompt rather than a path it would have to find. Placeholders
are `${name}`; an unknown one is left as it is.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


def values(cfg: dict) -> dict[str, str]:
    paths, tests, stories = cfg["paths"], cfg["tests"], cfg["stories"]
    lang = stories.get("translation", "")
    max_lines = stories.get("max_lines", 80)
    if lang:
        story_translation = f"- `story-{lang}.md`: the same story in {lang}. The director reads and approves this one."
        rule = (f"The two story files are the only thing the director reads. Keep each within {max_lines}\n"
                "lines, with the same sections and the same ids in the same order.\n\n"
                f"**The two must mean the same thing.** The director approves the {lang} version; agents\n"
                "build from the English. Write one, then write the other from it, then compare\n"
                "them line by line as if you were looking for a contract discrepancy: every AC,\n"
                "every TC, every number, every \"only\", \"must\", \"can\", every assumption and\n"
                "out-of-scope item. A reviewer from another vendor will do the same comparison.")
    else:
        story_translation = ""
        rule = f"`story.md` is the only thing the director reads. Keep it within {max_lines} lines."
    return {
        "specs": paths["specs"], "sprints": paths["sprints"], "roadmap": paths["roadmap"],
        "product": paths["product"], "design": paths["design"],
        "test_cmd": tests["test_cmd"], "lint_cmd": tests.get("lint_cmd") or "true",
        "id_digits": str(stories["id_digits"]),
        "story_translation": story_translation, "story_translation_rule": rule,
        "also_in_translation": f" and then in {lang}" if lang else "",
    }


def render(stage_file: str, cfg: dict) -> str:
    text = (PROMPTS / f"{stage_file}.md").read_text(encoding="utf-8")
    return Template(text).safe_substitute(values(cfg))
