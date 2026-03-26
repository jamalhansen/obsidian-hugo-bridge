from typing import Any, Dict
import re

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
    
    if "name" in unsplash_info: unsplash_info["name"] = unsplash_info.pop("name") # Keep as name
    if "user" in unsplash_info: unsplash_info["username"] = unsplash_info.pop("user")
    if "id" in unsplash_info: unsplash_info["photo_id"] = unsplash_info.pop("id")

    # Cover image handling
    if "image" in new_metadata:
        img = new_metadata.pop("image")
        if img:
            cover = {
                "image": img,
                "alt": "",
                "caption": "",
                "relative": True
            }
            if unsplash_info:
                cover["credit"] = unsplash_info
            new_metadata["cover"] = cover
    elif unsplash_info:
        # Inject credit into existing cover if possible
        if "cover" in new_metadata and isinstance(new_metadata["cover"], dict):
            new_metadata["cover"]["credit"] = unsplash_info

    # Clean up redundant or theme-clashing fields
    to_strip = [
        "canonical_url", "layout", "slug", "status", "created",
        "published_date", "Category", "promo_file", "series_position"
    ]
    for field in to_strip:
        new_metadata.pop(field, None)

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
