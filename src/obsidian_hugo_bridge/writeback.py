"""Record publish facts back on the vault note, so the vault knows what's live.

Only fills fields that are missing or empty -- an existing value is the author's and
is never overwritten. Edits are line-level inside the frontmatter block, so the rest
of the note (key order, quoting, comments, body) stays byte-for-byte the same. The
note is copied to a timestamped backup before it's changed.
"""
import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml
from local_first_common.obsidian import split_frontmatter

BACKUP_DIR = Path.home() / ".local" / "share" / "obsidian-hugo-bridge" / "backups"


def missing_fields(note_text: str, updates: dict[str, str]) -> dict[str, str]:
    parts = split_frontmatter(note_text)
    if parts is None:
        return {}
    try:
        current = yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(current, dict):
        return {}
    return {k: v for k, v in updates.items() if current.get(k) in (None, "", [])}


def apply_updates(note_text: str, updates: dict[str, str]) -> str:
    """Set each key in `updates` inside the frontmatter: replace an empty line, else append."""
    raw, body = split_frontmatter(note_text)
    for key, value in updates.items():
        line = f"{key}: {value}\n"
        pattern = re.compile(rf"^{re.escape(key)}:[ \t]*(?:null|~|''|\"\"|\[\])?[ \t]*\n", re.MULTILINE)
        raw, n = pattern.subn(line, raw, count=1)
        if not n:
            raw += line if raw.endswith("\n") or not raw else "\n" + line
    return f"---\n{raw}---\n{body}"


def write_back(note: Path, updates: dict[str, str], backup_dir: Path = BACKUP_DIR) -> dict[str, str]:
    """Fill missing fields on `note`; return what was written ({} if nothing changed)."""
    text = note.read_text(encoding="utf-8")
    todo = missing_fields(text, updates)
    if not todo:
        return {}
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / stamp / note.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(note, dest)
    note.write_text(apply_updates(text, todo), encoding="utf-8")
    return todo
