"""Where the vault and the live site disagree about a published post.

Edits made directly in Hugo after publishing (alt text, a retitle, test annotations)
leave the vault stale; re-publishing from the vault would then undo them. This lists
those differences so they can be backported before the vault is treated as truth.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import frontmatter

from .core import convert_body_syntax, parse_obsidian_post
from .site import existing_bundle
from .themes.papermod import normalize_papermod
from .utils import slugify

COMPARED = ("title", "description", "date", "tags", "series", "cover.image", "cover.alt")


@dataclass
class Drift:
    note: Path
    slug: str
    live: Path | None
    fields: dict[str, tuple[object, object]] = field(default_factory=dict)  # name -> (vault, live)
    body_differs: bool = False

    @property
    def clean(self) -> bool:
        return self.live is not None and not self.fields and not self.body_differs


def _value(meta: dict, dotted: str):
    cur = meta
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    if isinstance(cur, date):
        return cur.isoformat()[:10]
    if isinstance(cur, str) and dotted == "series":
        return [cur]
    if isinstance(cur, list):
        return sorted(str(x) for x in cur if x not in (None, ""))
    return cur


def _normalized_body(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def published_notes(vault_blog: Path) -> list[Path]:
    notes = []
    for f in sorted(vault_blog.rglob("*.md")):
        if "posts" not in f.parts or f.name == "promo.md":
            continue
        if str(frontmatter.load(f).metadata.get("status", "")).lower() == "published":
            notes.append(f)
    return notes


def drift_for(note: Path, hugo_dir: Path) -> Drift:
    post = parse_obsidian_post(note.read_text(encoding="utf-8"))
    slug = slugify(post.metadata.get("slug") or post.metadata.get("title") or note.stem)
    live_dir = existing_bundle(hugo_dir, slug)
    d = Drift(note, slug, live_dir)
    if live_dir is None:
        return d
    vault_meta = normalize_papermod(post.metadata)
    live = frontmatter.load(live_dir / "index.md")
    for name in COMPARED:
        v, lv = _value(vault_meta, name), _value(live.metadata, name)
        if v != lv:
            d.fields[name] = (v, lv)
    d.body_differs = _normalized_body(convert_body_syntax(post.content)) != _normalized_body(live.content)
    return d
