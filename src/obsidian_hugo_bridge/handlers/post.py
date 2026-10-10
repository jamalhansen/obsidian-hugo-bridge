import difflib
import re
import shutil
from datetime import date, datetime
from pathlib import Path

import frontmatter

from ..core import (
    HugoBridgeError,
    OverwriteRefusedError,
    convert_body_syntax,
    find_images,
    generate_image_alt,
    parse_obsidian_post,
    publish_image,
    published_image_name,
    strip_leading_h1,
)
from ..site import PREVIEW_DIR, derived_bundle, existing_bundle, index_is_tracked
from ..themes.papermod import normalize_papermod
from ..utils import slugify

KNOWN_STATUSES = ("outline", "draft", "published")
STARTERS = Path("blog") / "starters"
POSTS = Path("blog") / "posts"


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
    max_width: int = 1600,
    keep_images: bool = False,
) -> Path:
    """Convert a vault post into a Hugo page bundle and return the bundle directory.

    Re-publishing overwrites the post's existing bundle wherever it lives. `preview`
    writes a draft copy under content/blog/_preview/ instead (gitignored). With
    `overwrite=False`, an existing bundle whose index.md would change is left alone and
    OverwriteRefusedError carries the diff -- the live copy may hold edits the vault lacks.
    A bundle that isn't in the site's git is not live and is replaced without that check.

    Images wider than `max_width` are resized and PNGs without transparency ship as JPEG,
    with the body and cover rewritten to match; `keep_images` copies them byte for byte.
    """
    content = input_path.read_text(encoding="utf-8")
    post = parse_obsidian_post(content)
    source = post.metadata
    status = str(source.get("status") or "").strip().lower()
    if status and status not in KNOWN_STATUSES:
        print(
            f"   ⚠️  status '{status}' isn't one of {', '.join(KNOWN_STATUSES)}: publishing as a draft, "
            "and calib and fm-validate won't recognise it"
        )

    slug = slugify(str(slug or source.get("slug") or source.get("title") or input_path.stem))

    post.metadata = normalize_papermod(source)
    meta = post.metadata
    meta.setdefault("title", input_path.stem.replace("-", " ").title())
    meta["slug"] = slug
    meta.setdefault("date", datetime.now().astimezone().date())
    meta.setdefault("author", ["Jamal Hansen"])
    if preview:
        meta["draft"] = True
    post.metadata = {"title": meta.pop("title"), "slug": meta.pop("slug"), **meta}

    post.content, dropped_h1 = strip_leading_h1(post.content, str(source.get("title") or ""))
    if dropped_h1 and verbose:
        print("   ✂️  Dropped the body's leading H1: Hugo renders the title")
    post.content = convert_body_syntax(post.content)

    # Image names are settled before the live-edit check so a re-publish compares like with like.
    cover = post.metadata.get("cover")
    cover_names = [str(cover["image"])] if isinstance(cover, dict) and cover.get("image") else None
    found = find_images(post.content, input_path.parent, vault_path, attachment_folders, cover_names, verbose)
    renames = {} if keep_images else {n: published_image_name(n, src) for n, src in found.items()}
    for old, new in renames.items():
        if old == new:
            continue
        post.content = post.content.replace(f"]({old})", f"]({new})")
        if isinstance(cover, dict) and cover.get("image") == old:
            cover["image"] = new

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
        if index_is_tracked(hugo_dir, index):
            # Checked before anything is written, images included.
            changes = semantic_diff(frontmatter.loads(index.read_text(encoding="utf-8")), post)
            if changes:
                raise OverwriteRefusedError(f"{index.relative_to(hugo_dir)} (- live, + vault)\n{changes}")
        elif verbose:
            print("   ℹ️  Existing bundle isn't in git, so it isn't live: replacing it")

    if not dry_run:
        blog_dir.mkdir(parents=True, exist_ok=True)
        for name, src in found.items():
            dest = blog_dir / renames.get(name, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if keep_images:
                shutil.copy2(src, dest)
                note = None
            else:
                note = publish_image(src, dest, max_width)
            if verbose:
                print(f"   ✓ {note or f'Copied: {name}'}")
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
    body = list(
        difflib.unified_diff(
            live.content.strip().splitlines(),
            proposed.content.strip().splitlines(),
            "live",
            "vault",
            n=1,
            lineterm="",
        )
    )
    if body:
        lines.append("  body:")
        lines.extend(f"    {line}" for line in body[2:])
    return "\n".join(lines)


def _fill_alt_text(post: frontmatter.Post, blog_dir: Path, vision_model: str, verbose: bool) -> None:
    """Replace missing, generic or title-fallback alt text with a vision-model description."""
    cover = post.metadata.get("cover")
    needs_alt = (
        isinstance(cover, dict)
        and cover.get("image")
        and (not cover.get("alt") or cover.get("alt") == post.metadata.get("title"))
    )
    if needs_alt and isinstance(cover, dict):
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


def promote_note(note: Path, vault_path: Path, today: date | None = None) -> Path:
    """Move a starter's folder from blog/starters/<group>/<slug>/ to blog/posts/YYYY/MM/<slug>/.

    YYYY/MM comes from `published_date` when set, else today. Returns the note's new path; a
    note that isn't under starters is left alone and its own path returned. Never clobbers an
    existing post folder.
    """
    note = note.resolve()
    root = vault_path.resolve()
    try:
        rel = note.relative_to(root)
    except ValueError as e:
        raise HugoBridgeError(f"{note} is not inside the vault {vault_path}") from e
    if rel.parts[:2] != STARTERS.parts or len(rel.parts) != 5:
        print(f"   ℹ️  Not a starter (expected {STARTERS}/<group>/<slug>/<note>.md): leaving {rel} where it is")
        return note
    raw = frontmatter.load(str(note)).metadata.get("published_date")
    when = today or datetime.now().astimezone().date()
    if isinstance(raw, date):
        when = raw
    elif raw:
        try:
            when = date.fromisoformat(str(raw)[:10])
        except ValueError:
            pass
    dest = root / POSTS / f"{when:%Y}" / f"{when:%m}" / note.parent.name
    if dest.exists():
        raise HugoBridgeError(f"{dest.relative_to(root)} already exists; move the starter by hand")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(note.parent), str(dest))
    print(f"   ✓ Promoted to {dest.relative_to(root)}")
    return dest / note.name
