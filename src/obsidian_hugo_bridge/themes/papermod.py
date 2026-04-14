from typing import Any, Dict


def normalize_papermod(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize frontmatter field names to PaperMod theme conventions."""
    new_metadata = metadata.copy()

    # Change summary: to description:
    if "summary" in new_metadata and "description" not in new_metadata:
        new_metadata["description"] = new_metadata.pop("summary")

    # TOC handling
    if "toc" in new_metadata:
        toc_val = new_metadata.pop("toc")
        if toc_val:
            new_metadata["ShowToc"] = True
            new_metadata["TocOpen"] = False
        else:
            new_metadata["ShowToc"] = False

    # Process Unsplash credit and Cover images
    unsplash_info = {}
    for key in ["unsplash_name", "unsplash_user", "unsplash_id"]:
        if key in new_metadata:
            unsplash_info[key.replace("unsplash_", "")] = new_metadata.pop(key)

    if "user" in unsplash_info:
        unsplash_info["username"] = unsplash_info.pop("user")
    if "id" in unsplash_info:
        unsplash_info["photo_id"] = unsplash_info.pop("id")

    # Cover image handling
    if "image" in new_metadata:
        img = new_metadata.pop("image")
        if img:
            cover = {
                "image": img,
                "alt": "",
                "caption": "",
                "relative": True,
            }
            if unsplash_info:
                cover["credit"] = unsplash_info
            new_metadata["cover"] = cover
    elif unsplash_info:
        if "cover" in new_metadata and isinstance(new_metadata["cover"], dict):
            new_metadata["cover"]["credit"] = unsplash_info

    # Convert published_date to date (Hugo field name)
    if "published_date" in new_metadata and "date" not in new_metadata:
        new_metadata["date"] = new_metadata.pop("published_date")
    else:
        new_metadata.pop("published_date", None)

    # Strip tags: remove # prefix from each tag value
    if "tags" in new_metadata and isinstance(new_metadata["tags"], list):
        new_metadata["tags"] = [
            t.lstrip("#") if isinstance(t, str) else t
            for t in new_metadata["tags"]
            if t  # drop empty/null entries
        ]

    # Normalize category: scalar or wikilink → list
    if "category" in new_metadata:
        cat = new_metadata["category"]
        if isinstance(cat, str) and cat.strip():
            new_metadata["category"] = [cat.strip()]
        elif not cat:
            new_metadata.pop("category")

    # Clean up redundant or theme-clashing fields
    # Note: slug is intentionally kept — Hugo uses it for URL overrides
    to_strip = [
        "canonical_url", "layout", "status", "created",
        "Category", "promo_file", "series_position",
        "featureimage", "cardimage",
    ]
    for field in to_strip:
        new_metadata.pop(field, None)

    # Strip null/empty-value fields (Obsidian leaves these as None)
    new_metadata = {k: v for k, v in new_metadata.items() if v is not None and v != ""}

    # Series handling
    if "series" in new_metadata:
        series = new_metadata["series"]
        if isinstance(series, str):
            if series.strip() in ("", "[]"):
                new_metadata.pop("series")
            else:
                new_metadata["series"] = [series.strip()]
        elif isinstance(series, list):
            if not series:
                new_metadata.pop("series")
        else:
            new_metadata.pop("series")

    return new_metadata
