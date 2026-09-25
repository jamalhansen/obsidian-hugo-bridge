import difflib
import re
from datetime import date, datetime
from pathlib import Path

import frontmatter

from ..core import (
    OverwriteRefusedError,
    convert_body_syntax,
    copy_images,
    generate_image_alt,
    parse_obsidian_post,
)
from ..site import PREVIEW_DIR, derived_bundle, existing_bundle
from ..themes.papermod import normalize_papermod
from ..utils import slugify


def handle_post(
    input_path: Path,
    hugo_dir: Path,
    slug: str | None = None,
    vault_path: Path | None = None,
    attachment_folders: list[str] | None = None,
    dry_run: bool = False,
    no_llm: bool = False,
    verbose: bool = False,
    auto_alt: bool = False,
    vision_model: str = "@vision",
    preview: bool = False,
    overwrite: bool = True,
) -> Path:
    """Convert a vault post into a Hugo page bundle and return the bundle directory.

    Re-publishing overwrites the post's existing bundle wherever it lives. `preview`
    writes a draft copy under content/blog/_preview/ instead (gitignored). With
    `overwrite=False`, an existing bundle whose index.md would change is left alone and
    OverwriteRefusedError carries the diff -- the live copy may hold edits the vault lacks.
    """
    content = input_path.read_text(encoding="utf-8")
    post = parse_obsidian_post(content)
    source = post.metadata

    slug = slugify(slug or source.get("slug") or source.get("title") or input_path.stem)

    post.metadata = normalize_papermod(source)
    meta = post.metadata
    meta.setdefault("title", input_path.stem.replace("-", " ").title())
    meta["slug"] = slug
    meta.setdefault("date", datetime.now().astimezone().date())
    meta.setdefault("author", ["Jamal Hansen"])
    if preview:
        meta["draft"] = True
    post.metadata = {"title": meta.pop("title"), "slug": meta.pop("slug"), **meta}

    post.content = convert_body_syntax(post.content)

    if preview:
        blog_dir = hugo_dir / PREVIEW_DIR / slug
    else:
        blog_dir = existing_bundle(hugo_dir, slug) or derived_bundle(
            hugo_dir, slug, post.metadata, source.get("series_position")
        )
    if verbose:
        print(f"   📂 Bundle: {blog_dir.relative_to(hugo_dir)}")

    index = blog_dir / "index.md"
    if not overwrite and not preview and index.exists():
        # Checked before anything is written, images included.
        changes = semantic_diff(frontmatter.loads(index.read_text(encoding="utf-8")), post)
        if changes:
            raise OverwriteRefusedError(f"{index.relative_to(hugo_dir)} (- live, + vault)\n{changes}")

    if not dry_run:
        blog_dir.mkdir(parents=True, exist_ok=True)
        copy_images(
            post.content,
            input_path.parent,
            blog_dir,
            vault_path=vault_path,
            attachment_folders=attachment_folders,
            verbose=verbose,
        )
    else:
        print(f"[dry-run] Would copy images to: {blog_dir}")

    if auto_alt and not no_llm:
        _fill_alt_text(post, blog_dir, vision_model, verbose)

    final_output = frontmatter.dumps(post, sort_keys=False, width=4096, allow_unicode=True) + "\n"
    if dry_run:
        print(f"[dry-run] Would write post to: {blog_dir}/index.md")
        if verbose:
            print("-" * 20)
            print(final_output[:500] + "...")
            print("-" * 20)
    else:
        index.write_text(final_output, encoding="utf-8")
        if verbose:
            print(f"   ✓ Written: {blog_dir}/index.md")

    return blog_dir


def _comparable(value):
    if value in (None, "", [], {}):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, dict):
        return {k: _comparable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_comparable(v) for v in value]
    return value


def semantic_diff(live: frontmatter.Post, proposed: frontmatter.Post) -> str:
    """What re-publishing would change, ignoring YAML formatting. Empty when nothing would."""
    lines = []
    for key in dict.fromkeys([*live.metadata, *proposed.metadata]):
        a, b = _comparable(live.metadata.get(key)), _comparable(proposed.metadata.get(key))
        if key == "draft":  # Hugo's default
            a, b = bool(a), bool(b)
        if a != b:
            lines.append(f"  {key}:\n  - {a!r}\n  + {b!r}")
    body = list(difflib.unified_diff(
        live.content.strip().splitlines(), proposed.content.strip().splitlines(),
        "live", "vault", n=1, lineterm="",
    ))
    if body:
        lines.append("  body:")
        lines.extend(f"    {line}" for line in body[2:])
    return "\n".join(lines)


def _fill_alt_text(post: frontmatter.Post, blog_dir: Path, vision_model: str, verbose: bool) -> None:
    """Replace missing, generic or title-fallback alt text with a vision-model description."""
    cover = post.metadata.get("cover")
    needs_alt = isinstance(cover, dict) and cover.get("image") and (
        not cover.get("alt") or cover.get("alt") == post.metadata.get("title")
    )
    if needs_alt:
        alt = generate_image_alt(blog_dir / cover["image"], model=vision_model, verbose=verbose)
        if alt:
            cover["alt"] = alt
            if verbose:
                print(f"   ✓ Generated alt for cover: {alt}")

    for old_alt, img_path_str in re.findall(r"!\[(.*?)\]\((.*?)\)", post.content):
        if old_alt.strip() and old_alt.strip().lower() not in ("image", "img"):
            continue
        actual_path = blog_dir / img_path_str
        if not actual_path.exists():
            continue
        new_alt = generate_image_alt(actual_path, model=vision_model, verbose=verbose)
        if new_alt:
            post.content = post.content.replace(f"![{old_alt}]({img_path_str})", f"![{new_alt}]({img_path_str})")
            if verbose:
                print(f"   ✓ Generated alt for {img_path_str}: {new_alt}")
