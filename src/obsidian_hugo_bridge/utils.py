import re
import unicodedata

def slugify(text: str) -> str:
    """
    Convert to ASCII. Convert spaces to hyphens.
    Remove characters that aren't alphanumerics, underscores, or hyphens.
    Convert to lowercase. Strip leading and trailing whitespace.
    """
    text = str(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)

def clean_wikilinks(text: str) -> str:
    """
    Remove Obsidian wiki-link syntax [[...]] from string.
    Handles aliased links [[Link|Alias]] -> Alias
    and headers [[Link#Header]] -> Link
    """
    # Pattern to match [[Link#Header|Alias]]
    # Group 1: Link, Group 2: Alias (optional)
    return re.sub(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)

def yaml_str(value: str) -> str:
    """Escape a value for embedding in a YAML double-quoted string."""
    return str(value).replace("\\", "\\\\").replace("\"", "\\\"")
