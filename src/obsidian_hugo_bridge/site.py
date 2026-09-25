"""Facts about the target Hugo site: where a post's bundle lives, and its public URL."""
from pathlib import Path

import frontmatter
import yaml

from .utils import slugify

# Posts without a series that still get a folder, by tag.
TAG_FOLDERS = {"tsql2sday": "tsql-tuesday"}
PREVIEW_DIR = Path("content") / "blog" / "_preview"


def _config(hugo_dir: Path) -> dict:
    for candidate in ("config/_default/hugo.yaml", "hugo.yaml", "config.yaml"):
        f = hugo_dir / candidate
        if f.exists():
            return yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {}


def canonical_url(hugo_dir: Path, slug: str) -> str:
    """Public URL for a blog post, from the site's baseURL and blog permalink pattern."""
    cfg = _config(hugo_dir)
    base = str(cfg.get("baseURL") or "").rstrip("/")
    pattern = (cfg.get("permalinks") or {}).get("blog", "/blog/:slug/")
    return base + pattern.replace(":slug", slug)


def existing_bundle(hugo_dir: Path, slug: str) -> Path | None:
    """The live bundle for `slug`, wherever it was placed (so re-publishing overwrites it)."""
    blog = hugo_dir / "content" / "blog"
    preview = hugo_dir / PREVIEW_DIR
    for index in sorted(blog.rglob("index.md")):
        if index.is_relative_to(preview):
            continue
        folder = index.parent.name
        prefix, _, rest = folder.partition("-")
        if folder == slug or (prefix.isdigit() and rest == slug):
            return index.parent
        if frontmatter.load(index).metadata.get("slug") == slug:
            return index.parent
    return None


def derived_bundle(hugo_dir: Path, slug: str, metadata: dict, series_position=None) -> Path:
    """Where a new post goes: blog/<series-slug>/<NN>-<slug>/, or blog/<slug>/ outside a series."""
    blog = hugo_dir / "content" / "blog"
    series = metadata.get("series")
    folder = slugify(series[0]) if series else next(
        (TAG_FOLDERS[t.lower()] for t in metadata.get("tags") or [] if t.lower() in TAG_FOLDERS), None
    )
    name = slug
    if series and isinstance(series_position, int) and not isinstance(series_position, bool):
        name = f"{series_position:02d}-{slug}"
    return blog / folder / name if folder else blog / name
