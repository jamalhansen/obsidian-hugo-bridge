import re
import shutil
import base64
from pathlib import Path
from typing import Optional, List
import frontmatter
from .utils import clean_wikilinks
from local_first_common.cli import resolve_provider
from local_first_common.tracking import register_tool, timed_run

_TOOL = register_tool("obsidian-hugo-bridge")

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

def convert_body_syntax(body: str) -> str:
    """Convert Obsidian-specific syntax to Hugo-compatible markdown."""
    # ![[image.jpg]] -> ![Image](image.jpg)
    body = re.sub(r"!\[\[([^\]|]+)\]\]", r"![Image](\1)", body)
    # ![[image.jpg|alt]] -> ![alt](image.jpg)
    body = re.sub(r"!\[\[([^\]|]+)\|([^\]]+)\]\]", r"![\2](\1)", body)
    # Obsidian callouts [!info] -> Hugo/Goldmark blockquotes (basic support)
    # This is a simple conversion, theme might handle it better with shortcodes
    body = re.sub(r"^>\s+\[!(\w+)\]\+?\s*(.*)", r"> **\1**: \2", body, flags=re.MULTILINE | re.IGNORECASE)
    return body

def generate_image_alt(image_path: Path, model: str = "@vision", verbose: bool = False) -> Optional[str]:
    """Generate an alt tag for an image using a vision model."""
    if not image_path.exists():
        if verbose:
            print(f"   ⚠️  Image not found for alt generation: {image_path}")
        return None

    try:
        with open(image_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")

        # Vision model is always local (Ollama) as per user request
        llm = resolve_provider(provider_name="ollama", model=model)
        system = "You are a helpful assistant that writes concise, descriptive alt text for images."
        user = "Describe this image in one short sentence (max 120 characters) for use as alt text. Be objective and specific."

        if verbose:
            print(f"🧠 Generating alt text for {image_path.name}...")

        with timed_run("obsidian-hugo-bridge", llm.model, source_location=str(image_path)) as _run:
            description = llm.complete(system, user, images=[img_base64])
            _run.item_count = 1
            
        if isinstance(description, dict):
            # This shouldn't happen based on the prompt but handle it just in case
            description = str(description)
            
        return description.strip().strip("\"")
    except Exception as e:
        if verbose:
            print(f"   ⚠️  Alt generation failed for {image_path.name}: {e}")
        return None

def copy_images(
    body: str, 
    source_dir: Path, 
    dest_dir: Path, 
    vault_path: Optional[Path] = None,
    verbose: bool = False
) -> List[str]:
    """
    Find images in body and copy them to dest_dir.
    Searches in source_dir and then vault_path if provided.
    Returns list of copied image names.
    """
    copied = []
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
    
    # 1. Copy all images from the source directory (common for page bundles or attachments)
    if source_dir.exists():
        for img_file in source_dir.iterdir():
            if img_file.is_file() and img_file.suffix.lower() in image_exts:
                shutil.copy2(img_file, dest_dir / img_file.name)
                copied.append(img_file.name)
                if verbose:
                    print(f"   ✓ Copied from source: {img_file.name}")

    # 2. Extract referenced images from body to ensure we didn't miss any in the vault
    # Standard markdown syntax: ![alt](path)
    referenced = re.findall(r"!\[.*?\]\(([^)]+)\)", body)
    
    if vault_path and vault_path.exists():
        dest_dir_resolved = dest_dir.resolve()
        for img_name in referenced:
            # Skip if already copied
            if img_name in copied:
                continue
            
            # Basic security check for path traversal
            if ".." in img_name or img_name.startswith("/"):
                continue
                
            dest = (dest_dir / img_name).resolve()
            if not dest.is_relative_to(dest_dir_resolved):
                continue
            
            if not dest.exists():
                # Search vault
                matches = list(vault_path.rglob(img_name))
                if matches:
                    shutil.copy2(matches[0], dest)
                    copied.append(img_name)
                    if verbose:
                        print(f"   ✓ Copied from vault: {img_name}")
    
    return copied
