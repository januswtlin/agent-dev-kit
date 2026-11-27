"""`agentctl init`: put the kit's project files into a repository, once.

Copies templates/project/ into the project, filling in the kit version, the kit
repository and the people, and generates .github/CODEOWNERS from the resulting
agentdev.toml. A file that already exists is never overwritten: it is listed, so
that someone adopting the kit in an existing project can merge it by hand.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import config, owners, prompts

KIT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = KIT_ROOT / "templates" / "project"
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
TEXT_SUFFIXES = {".md", ".toml", ".yml", ".yaml", ".json", ".sh", ""}
PROMPT = re.compile(r"__PROMPT:([a-z-]+)__")


def kit_version() -> str:
    marker = KIT_ROOT / ".kit-version"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    out = subprocess.run(["git", "-C", str(KIT_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()


def init(root: Path, people: list[str], version: str = "", dry_run: bool = False) -> tuple[list[str], list[str]]:
    """Returns (created, kept) as paths relative to `root`."""
    if root.resolve() == KIT_ROOT:
        raise SystemExit("this is the kit itself; run `agentctl init` inside a project")
    if not people:
        raise SystemExit("name at least one person: agentctl init DIRECTOR [OTHER_HUMAN ...]")
    for login in people:
        if not LOGIN.match(login):
            raise SystemExit(f"not a GitHub login: {login!r}")
    version = version or kit_version()
    if not re.fullmatch(r"[0-9a-f]{40}", version):
        raise SystemExit(f"the kit version must be a full commit SHA, not {version!r}")
    repository = config.defaults()["kit"]["repository"]
    values = {
        "__KIT_VERSION__": version,
        "__KIT_REPOSITORY__": repository,
        "__DIRECTORS__": json.dumps(people[:1]),
        "__HUMANS__": json.dumps(people),
    }
    created, kept = [], []
    # agentdev.toml first: the prompts embedded in other files are filled in from it.
    files = sorted((p for p in TEMPLATE.rglob("*") if p.is_file()), key=lambda p: (p.name != config.FILE, str(p)))
    for source in files:
        rel = source.relative_to(TEMPLATE)
        dest = root / rel
        if dest.exists():
            kept.append(str(rel))
            continue
        created.append(str(rel))
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix in TEXT_SUFFIXES and source.name != ".gitkeep":
            text = source.read_text(encoding="utf-8")
            for key, value in values.items():
                text = text.replace(key, value)
            text = PROMPT.sub(lambda m: prompts.render(m.group(1), config.load(root)), text)
            dest.write_text(text, encoding="utf-8")
            shutil.copymode(source, dest)
        else:
            shutil.copy2(source, dest)
    codeowners = root / ".github" / "CODEOWNERS"
    if codeowners.exists():
        kept.append(".github/CODEOWNERS")
    else:
        created.append(".github/CODEOWNERS")
        if not dry_run:
            codeowners.parent.mkdir(parents=True, exist_ok=True)
            codeowners.write_text(owners.codeowners(config.load(root)), encoding="utf-8")
    return created, kept
