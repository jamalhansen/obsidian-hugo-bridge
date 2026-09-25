"""Shape checks for Hugo post frontmatter -- the problems a by-hand edit introduces.

The bridge writes valid frontmatter; these catch what happens afterwards in Hugo:
a block indented under the wrong key, a missing description, an empty tag, a cover
with no alt text. Errors fail; warnings are reported (e.g. vault-only leftovers).
"""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import frontmatter
import yaml

from .site import PREVIEW_DIR
from .themes.papermod import HUGO_KEYS

_DATE_KEYS = ("date", "publishDate", "pubdate", "published")
# Extra keys Hugo or the site's own layouts read (date aliases, finds) -- not leftovers.
_SITE_KEYS = {"published", "pubdate", "source_url", "source_title", "source_author", "source_type", "embed_type", "embed_html"}


@dataclass
class CheckResult:
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def check_post(index: Path) -> CheckResult:
    result = CheckResult(index)
    try:
        meta = frontmatter.load(index).metadata
    except yaml.YAMLError as e:
        result.errors.append(f"frontmatter is not valid YAML: {e}")
        return result

    if not meta.get("title"):
        result.errors.append("missing title")
    # Hugo takes the page date from the first of these that's set.
    when = next((meta[k] for k in _DATE_KEYS if meta.get(k)), None)
    if when is None:
        result.errors.append("missing date")
    elif not isinstance(when, (date, str)):
        result.errors.append(f"date is not a date: {when!r}")
    if not str(meta.get("description") or "").strip():
        result.errors.append("missing description")
    if "draft" in meta and not isinstance(meta["draft"], bool):
        result.errors.append(f"draft must be true/false, got {meta['draft']!r}")
    for key in ("tags", "series", "categories"):
        if key in meta and meta[key] is not None and not _str_list(meta[key]) and meta[key] != []:
            result.errors.append(f"{key} must be a list of non-empty strings, got {meta[key]!r}")
    if "tags" in meta and not meta["tags"]:
        result.warnings.append("no tags")
    cover = meta.get("cover")
    if cover is not None:
        if not isinstance(cover, dict):
            result.errors.append(f"cover must be a mapping, got {cover!r}")
        elif cover.get("image") and not str(cover.get("alt") or "").strip():
            result.errors.append("cover image has no alt text")
    leftovers = sorted(set(meta) - set(HUGO_KEYS) - _SITE_KEYS)
    if leftovers:
        result.warnings.append(f"fields Hugo ignores: {', '.join(leftovers)}")
    return result


def check_site(hugo_dir: Path, paths: list[Path] | None = None) -> list[CheckResult]:
    """Check the given index.md files, or every post under content/blog."""
    blog = hugo_dir / "content" / "blog"
    targets = paths or sorted(blog.rglob("index.md"))
    preview = hugo_dir / PREVIEW_DIR
    return [check_post(p) for p in targets if not p.resolve().is_relative_to(preview.resolve())]
