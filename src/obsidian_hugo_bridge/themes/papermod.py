from typing import Any

# Output order, and the only keys that reach Hugo. Vault-only fields (status,
# created, target_date, series_position, promo_file, the note-type `category`,
# unsplash_*, ...) are consumed or dropped, never passed through.
HUGO_KEYS = [
    "title", "slug", "date", "lastmod", "publishDate", "expiryDate", "description",
    "author", "tags", "categories", "series", "cover", "draft", "ShowToc", "TocOpen",
    "weight", "aliases", "type", "keywords", "math", "url",
]
_CAPITALIZED = {
    "Title": "title", "Series": "series", "Status": "status", "Author": "author",
    "Tags": "tags", "Category": "category", "Created": "created", "Description": "description",
}
_COVER_IMAGE_KEYS = ("image", "featureimage", "featured_image")


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def draft_from_status(metadata: dict[str, Any]) -> bool:
    """status: published -> live; any other status (draft, outline, ...) -> draft.

    With no status at all, an explicit `draft:` wins; otherwise default to draft.
    """
    status = str(metadata.get("status") or "").strip().lower()
    if status:
        return status != "published"
    draft = metadata.get("draft")
    return True if draft is None else bool(draft)


def _cover(m: dict[str, Any], title: str | None) -> dict[str, Any] | None:
    cover = dict(m["cover"]) if isinstance(m.get("cover"), dict) else {}
    image = next((m[k] for k in _COVER_IMAGE_KEYS if not _empty(m.get(k))), None) or cover.get("image")
    if not image:
        return None
    credit = {
        out: m[src] for src, out in
        (("unsplash_name", "name"), ("unsplash_user", "username"), ("unsplash_id", "photo_id"))
        if not _empty(m.get(src))
    }
    cover["image"] = image
    # A standalone `alt:` is how the vault records cover alt text; the title is the
    # fallback so a cover is never announced as an unlabeled image.
    cover["alt"] = m.get("alt") or cover.get("alt") or title or ""
    cover.setdefault("caption", "")
    cover.setdefault("relative", True)
    if credit:
        cover["credit"] = credit
    return cover


def _series(value: Any) -> list[str] | None:
    if isinstance(value, str):
        value = value.strip()
        return [value] if value and value != "[]" else None
    if isinstance(value, list):
        items = [str(v).strip() for v in value if not _empty(v)]
        return items or None
    return None


def normalize_papermod(metadata: dict[str, Any]) -> dict[str, Any]:
    """Map vault frontmatter onto the fields PaperMod uses, in a stable order."""
    m: dict[str, Any] = {}
    for key, value in metadata.items():
        key = _CAPITALIZED.get(key, key)
        if key not in m or _empty(m[key]):
            m[key] = value

    title = m.get("title")
    out: dict[str, Any] = {k: m[k] for k in HUGO_KEYS if k in m and not _empty(m[k])}

    if _empty(out.get("description")) and not _empty(m.get("summary")):
        out["description"] = m["summary"]
    if not _empty(m.get("published_date")):
        out["date"] = m["published_date"]
    if "toc" in m and "ShowToc" not in out:
        out["ShowToc"] = bool(m["toc"])
        out["TocOpen"] = False
    if isinstance(out.get("tags"), list):
        out["tags"] = [t.lstrip("#") for t in (str(t) for t in out["tags"] if not _empty(t)) if t.lstrip("#")]
        if not out["tags"]:
            del out["tags"]
    series = _series(m.get("series"))
    out.pop("series", None)
    if series:
        out["series"] = series
    cover = _cover(m, title)
    out.pop("cover", None)
    if cover:
        out["cover"] = cover
    out["draft"] = draft_from_status(m)

    return {k: out[k] for k in HUGO_KEYS if k in out}
