import base64
import re
import shutil
from pathlib import Path

import frontmatter
from local_first_common.cli import resolve_provider
from local_first_common.tracking import register_tool
from PIL import Image, UnidentifiedImageError

from .utils import clean_wikilinks

_TOOL = register_tool("obsidian-hugo-bridge")
TOOL_NAME = "obsidian-hugo-bridge"
DEFAULTS = {"provider": "ollama", "model": "llama3"}


class HugoBridgeError(Exception):
    """Base typed error for obsidian-hugo-bridge."""


class ImageAltError(HugoBridgeError):
    """Raised when alt text generation fails unrecoverably."""


class ConversionError(HugoBridgeError):
    """Raised when Obsidian-to-Hugo content conversion fails."""


class OverwriteRefusedError(HugoBridgeError):
    """Re-publishing would change a live bundle; the message is the unified diff."""


def parse_obsidian_post(content: str) -> frontmatter.Post:
    """Parse Obsidian markdown content into a frontmatter.Post object."""
    post = frontmatter.loads(content)
    # Clean wikilinks from all frontmatter values
    for key, value in post.metadata.items():
        if isinstance(value, str):
            post.metadata[key] = clean_wikilinks(value)
        elif isinstance(value, list):
            post.metadata[key] = [clean_wikilinks(v) if isinstance(v, str) else v for v in value]
    return post


def strip_leading_h1(body: str, title: str) -> tuple[str, bool]:
    """Drop a body that opens with `# <title>`: Hugo renders the title itself, so it would show twice.

    Post starters carried one (calib wrote it until 2026-10-10); published posts never did.
    Only an H1 that matches the title is dropped -- any other leading H1 is the author's.
    """

    def norm(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    match = re.match(r"\s*#[ \t]+(.+?)[ \t]*(?:\n|$)", body)
    if not match or not title or norm(match.group(1)) != norm(title):
        return body, False
    return body[match.end() :].lstrip("\n"), True


def convert_body_syntax(body: str) -> str:
    """Convert Obsidian-specific syntax to Hugo-compatible markdown."""
    # ![[image.jpg]] -> ![Image](image.jpg)
    body = re.sub(r"!\[\[([^\]|]+)\]\]", r"![Image](\1)", body)
    # ![[image.jpg|alt]] -> ![alt](image.jpg)
    body = re.sub(r"!\[\[([^\]|]+)\|([^\]]+)\]\]", r"![\2](\1)", body)
    # Obsidian callouts [!info] -> Hugo/Goldmark blockquotes (basic support)
    # This is a simple conversion, theme might handle it better with shortcodes
    body = re.sub(
        r"^>\s+\[!(\w+)\]\+?\s*(.*)",
        r"> **\1**: \2",
        body,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    return body


def generate_image_alt(image_path: Path, model: str = "@vision", verbose: bool = False) -> str | None:
    """Generate an alt tag for an image using a vision model."""
    if not image_path.exists():
        if verbose:
            print(f"   ⚠️  Image not found for alt generation: {image_path}")
        return None

    try:
        with open(image_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")

        # Vision model is always local (Ollama) as per user request
        llm = resolve_provider(provider_name="ollama", model=model, tool_name=TOOL_NAME)
        system = "You are a helpful assistant that writes concise, descriptive alt text for images."
        user = "Describe this image in one short sentence (max 120 characters) for use as alt text. Be objective and specific."

        if verbose:
            print(f"🧠 Generating alt text for {image_path.name}...")

        llm.source_location = str(image_path)
        llm.item_count = 1
        description = llm.complete(system, user, images=[img_base64])

        if isinstance(description, dict):
            # This shouldn't happen based on the prompt but handle it just in case
            description = str(description)

        return description.strip().strip('"')
    except Exception as e:  # noqa: BLE001 - alt-text generation is best-effort; any LLM failure should skip it, not crash the publish
        if verbose:
            print(f"   ⚠️  Alt generation failed for {image_path.name}: {e}")
        return None


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
JPEG_QUALITY = 85


def find_images(
    body: str,
    source_dir: Path,
    vault_path: Path | None = None,
    attachment_folders: list[str] | None = None,
    extra_images: list[str] | None = None,
    verbose: bool = False,
) -> dict[str, Path]:
    """Referenced image name -> the vault file it resolves to. Nothing is written.

    Searched in order: next to the note (other files there, like social cards, are not part
    of the post), the attachment folders under the vault, then the whole vault.
    """
    referenced = re.findall(r"!\[.*?\]\(([^)]+)\)", body) + list(extra_images or [])
    found: dict[str, Path] = {}
    for name in dict.fromkeys(referenced):
        if ".." in name or name.startswith("/"):  # keep the bundle inside its folder
            continue
        local = source_dir / name
        if local.is_file() and local.suffix.lower() in IMAGE_EXTS:
            found[name] = local
            continue
        if not (vault_path and vault_path.exists()):
            continue
        for folder in attachment_folders or []:
            candidate = vault_path / folder / name
            if candidate.is_file():
                found[name] = candidate
                break
        else:
            if verbose:
                print(f"   🔍 Image not in priority folders, searching full vault: {name}")
            matches = list(vault_path.rglob(name))
            if matches:
                found[name] = matches[0]
    return found


def copy_images(
    body: str,
    source_dir: Path,
    dest_dir: Path,
    vault_path: Path | None = None,
    attachment_folders: list[str] | None = None,
    verbose: bool = False,
    extra_images: list[str] | None = None,
) -> list[str]:
    """Copy the images `find_images` resolves into dest_dir, byte for byte. Returns the copied names."""
    copied: list[str] = []
    for name, src in find_images(body, source_dir, vault_path, attachment_folders, extra_images, verbose).items():
        dest = dest_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(name)
        if verbose:
            print(f"   ✓ Copied: {name}")
    return copied


def _open_image(path: Path) -> Image.Image | None:
    """The image, or None when Pillow can't read it (then it ships byte for byte)."""
    try:
        img = Image.open(path)
        img.load()
        return img
    except (UnidentifiedImageError, OSError):
        return None


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)


def published_image_name(name: str, src: Path) -> str:
    """The name an image gets in the bundle: a PNG without transparency ships as JPEG.

    Decided from the vault file alone, so a re-publish rewrites the body the same way every
    time and the live-edit check compares like with like.
    """
    if src.suffix.lower() != ".png":
        return name
    img = _open_image(src)
    if img is None or _has_alpha(img):
        return name
    return name[: -len(src.suffix)] + ".jpg"


def publish_image(src: Path, dest: Path, max_width: int = 1600) -> str | None:
    """Write src into the bundle at dest: resized down to max_width, and as JPEG when dest says so.

    A raster the bundle would ship unchanged is copied byte for byte. Returns a one-line note
    of what changed, or None when nothing did. The vault file is never touched.
    """
    img = _open_image(src) if src.suffix.lower() in (".png", ".jpg", ".jpeg") else None
    if img is None:
        shutil.copy2(src, dest)
        return None
    notes: list[str] = []
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.Resampling.LANCZOS)
        notes.append(f"resized to {img.width}x{img.height}")
    to_jpeg = dest.suffix.lower() in (".jpg", ".jpeg")
    if to_jpeg and src.suffix.lower() != dest.suffix.lower():
        notes.append("converted to JPEG")
    if not notes:
        shutil.copy2(src, dest)
        return None
    if to_jpeg:
        img.convert("RGB").save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
    else:
        img.save(dest)
    return f"{src.name} -> {dest.name}: {', '.join(notes)}"
