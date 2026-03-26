from pathlib import Path
from datetime import datetime
from typing import Optional, List
import re
import frontmatter
from ..core import parse_obsidian_post, convert_body_syntax, copy_images, generate_image_alt
from ..themes.papermod import normalize_papermod
from ..utils import slugify

def handle_post(
    input_path: Path,
    hugo_dir: Path,
    slug: Optional[str] = None,
    vault_path: Optional[Path] = None,
    attachment_folders: Optional[List[str]] = None,
    dry_run: bool = False,
    no_llm: bool = False,
    verbose: bool = False,
    auto_alt: bool = False,
    vision_model: str = "@vision"
) -> Path:
    """Handle blog post conversion."""
    content = input_path.read_text(encoding="utf-8")
    post = parse_obsidian_post(content)
    
    # 1. Normalize slug
    if not slug:
        title = post.metadata.get("title") or input_path.stem
        slug = slugify(title)
    else:
        slug = slugify(slug)
        
    # 2. Frontmatter normalization
    post.metadata = normalize_papermod(post.metadata)
    
    # Inject defaults if missing
    if "title" not in post.metadata:
        post.metadata["title"] = input_path.stem.replace("-", " ").title()
    if "date" not in post.metadata:
        post.metadata["date"] = datetime.now().strftime("%Y-%m-%d")
    if "author" not in post.metadata:
        post.metadata["author"] = ["Jamal Hansen"]
    if "draft" not in post.metadata:
        post.metadata["draft"] = True
        
    # 3. Body syntax conversion
    post.content = convert_body_syntax(post.content)
    
    # 4. Setup directory
    blog_dir = hugo_dir / "content" / "blog" / slug
    if not dry_run:
        blog_dir.mkdir(parents=True, exist_ok=True)
        
    # 5. Image handling (copy first so we can run vision on them)
    if not dry_run:
        copy_images(
            post.content,
            input_path.parent,
            blog_dir,
            vault_path=vault_path,
            attachment_folders=attachment_folders,
            verbose=verbose
        )
    else:
        print(f"[dry-run] Would copy images to: {blog_dir}")

    # 6. Auto-alt generation
    if auto_alt and not no_llm:
        # Cover image alt
        cover = post.metadata.get("cover")
        if isinstance(cover, dict) and cover.get("image"):
            image_path = blog_dir / cover["image"]
            if not cover.get("alt"):
                alt = generate_image_alt(image_path, model=vision_model, verbose=verbose)
                if alt:
                    cover["alt"] = alt
                    if verbose:
                        print(f"   ✓ Generated alt for cover: {alt}")

        # Inline images alt
        # Find all ![alt](path)
        img_pattern = r"!\[(.*?)\]\((.*?)\)"
        matches = re.findall(img_pattern, post.content)
        for old_alt, img_path_str in matches:
            if not old_alt.strip() or old_alt.strip().lower() in ("image", "img"):
                # Potential candidate for auto-alt
                # Resolve path relative to blog_dir
                actual_path = blog_dir / img_path_str
                if actual_path.exists():
                    new_alt = generate_image_alt(actual_path, model=vision_model, verbose=verbose)
                    if new_alt:
                        # Replace in content (simple string replace might be risky if same path is used twice, 
                        # but standard markdown uses unique-ish paths usually)
                        old_md = f"![{old_alt}]({img_path_str})"
                        new_md = f"![{new_alt}]({img_path_str})"
                        post.content = post.content.replace(old_md, new_md)
                        if verbose:
                            print(f"   ✓ Generated alt for {img_path_str}: {new_alt}")

    # 7. Save output
    final_output = frontmatter.dumps(post)
    if dry_run:
        print(f"[dry-run] Would write post to: {blog_dir}/index.md")
        if verbose:
            print("-" * 20)
            print(final_output[:500] + "...")
            print("-" * 20)
    else:
        (blog_dir / "index.md").write_text(final_output, encoding="utf-8")
        if verbose:
            print(f"   ✓ Written: {blog_dir}/index.md")
            
    return blog_dir
