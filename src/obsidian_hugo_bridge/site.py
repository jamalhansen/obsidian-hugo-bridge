"""Facts about the target Hugo site: where a post's bundle lives, and its public URL."""

import subprocess
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
    folder = (
        slugify(series[0])
        if series
        else next((TAG_FOLDERS[t.lower()] for t in metadata.get("tags") or [] if t.lower() in TAG_FOLDERS), None)
    )
    name = slug
    if series and isinstance(series_position, int) and not isinstance(series_position, bool):
        name = f"{series_position:02d}-{slug}"
    return blog / folder / name if folder else blog / name


def index_is_tracked(hugo_dir: Path, index: Path) -> bool:
    """Whether a bundle's index.md is in the site's git index, which is what makes it live.

    An untracked bundle was written by an earlier publish and never shipped, so re-publishing
    over it is not clobbering anyone's hand edits (2026-10-10: the guard refused a re-publish
    over a bundle written ten minutes earlier). Outside a git repo everything counts as live.
    """
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=hugo_dir, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return True
    if inside.returncode != 0:
        return True
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(index.resolve())],
        cwd=hugo_dir,
        capture_output=True,
        check=False,
    )
    return tracked.returncode == 0
