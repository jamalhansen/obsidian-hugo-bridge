from pathlib import Path
from datetime import datetime
from typing import Optional
import frontmatter
from ..core import parse_obsidian_post, convert_body_syntax, copy_images
from ..themes.papermod import normalize_papermod
from ..utils import slugify

def handle_post(
    input_path: Path,
    hugo_dir: Path,
    slug: Optional[str] = None,
    vault_path: Optional[Path] = None,
    dry_run: bool = False,
    no_llm: bool = False,
    verbose: bool = False
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
        
    # 5. Save output
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
            
    # 6. Image handling
    if not dry_run:
        copy_images(
            post.content,
            input_path.parent,
            blog_dir,
            vault_path=vault_path,
            verbose=verbose
        )
    else:
        print(f"[dry-run] Would copy images to: {blog_dir}")
        
    return blog_dir
