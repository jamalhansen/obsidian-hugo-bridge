import os
from pathlib import Path
from typing import Optional, List
import typer
from typing_extensions import Annotated
from git import Repo

from local_first_common.cli import resolve_dry_run
from .handlers.post import handle_post
from .handlers.find import handle_find

app = typer.Typer(help="Obsidian to Hugo Converter")
publish_app = typer.Typer(help="Publish content to Hugo")
app.add_typer(publish_app, name="publish")

BLOG_PATH = os.environ.get("BLOG_PATH")
OBSIDIAN_VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH")

def commit_changes(hugo_dir: Path, target_dir: Path, slug: str, content_type: str):
    """Git add and commit the changes."""
    try:
        repo = Repo(hugo_dir)
        # Relative path from repo root
        rel_path = target_dir.relative_to(hugo_dir)
        repo.index.add([str(rel_path)])
        repo.index.commit(f"publish({content_type}): {slug}")
        print(f"   ✓ Committed: publish({content_type}): {slug}")
    except Exception as e:
        print(f"   ⚠️  Git commit failed: {e}")

@publish_app.command("post")
def publish_post(
    input_file: Annotated[Path, typer.Argument(help="Path to Obsidian markdown file")],
    hugo_dir: Annotated[Optional[Path], typer.Option("--hugo-dir", "-d", help="Path to Hugo site root")] = None,
    vault_path: Annotated[Optional[Path], typer.Option("--vault-path", "-v", help="Vault root for image search")] = None,
    attachment_folder: Annotated[Optional[List[str]], typer.Option("--attachment-folder", "-a", help="Subfolder in vault to search for images (repeatable)")] = None,
    slug: Annotated[Optional[str], typer.Option("--slug", "-s", help="Override output slug")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without writing to disk.")] = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Skip LLM calls. Implies --dry-run.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V", help="Show extra debug output.")] = False,
    commit: Annotated[bool, typer.Option("--commit", help="Git commit after writing")] = False,
    auto_alt: Annotated[bool, typer.Option("--auto-alt", help="Automatically generate alt text for images using vision LLM")] = False,
    vision_model: Annotated[str, typer.Option("--vision-model", help="Vision model to use for alt text generation")] = "@vision",
):
    """Publish a blog post."""
    dry_run = resolve_dry_run(dry_run, no_llm)
    hugo_dir = hugo_dir or (Path(BLOG_PATH) if BLOG_PATH else None)
    if not hugo_dir:
        typer.secho("Error: Hugo site directory not specified. Use --hugo-dir or set BLOG_PATH.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    vault_path = vault_path or (Path(OBSIDIAN_VAULT_PATH) if OBSIDIAN_VAULT_PATH else None)
    
    # Use defaults if not provided
    folders = attachment_folder or ["attachments", "images"]
    
    if verbose:
        print(f"🚀 Publishing post: {input_file.name}")
        
    target_dir = handle_post(
        input_file,
        hugo_dir,
        slug=slug,
        vault_path=vault_path,
        attachment_folders=folders,
        dry_run=dry_run,
        no_llm=no_llm,
        verbose=verbose,
        auto_alt=auto_alt,
        vision_model=vision_model
    )
    
    if commit and not dry_run:
        final_slug = slug or target_dir.name
        commit_changes(hugo_dir, target_dir, final_slug, "post")
        
    if not dry_run:
        print(f"\n🎉 Done! Published to: {target_dir}")

@publish_app.command("find")
def publish_find(
    input_file: Annotated[Path, typer.Argument(help="Path to Obsidian markdown file")],
    hugo_dir: Annotated[Optional[Path], typer.Option("--hugo-dir", "-d", help="Path to Hugo site root")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without writing to disk.")] = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Skip LLM calls. Implies --dry-run.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V", help="Show extra debug output.")] = False,
    commit: Annotated[bool, typer.Option("--commit", help="Git commit after writing")] = False,
    vision_model: Annotated[str, typer.Option("--vision-model", help="Vision model to use for alt text generation")] = "@vision",
):
    """Publish a find."""
    dry_run = resolve_dry_run(dry_run, no_llm)
    hugo_dir = hugo_dir or (Path(BLOG_PATH) if BLOG_PATH else None)
    if not hugo_dir:
        typer.secho("Error: Hugo site directory not specified. Use --hugo-dir or set BLOG_PATH.", fg=typer.colors.RED)
        raise typer.Exit(1)
        
    if verbose:
        print(f"🚀 Publishing find: {input_file.name}")
        
    target_dir = handle_find(
        input_file,
        hugo_dir,
        dry_run=dry_run,
        no_llm=no_llm,
        verbose=verbose
    )
    
    if commit and not dry_run:
        commit_changes(hugo_dir, target_dir, target_dir.name, "find")
        
    if not dry_run:
        print(f"\n🎉 Done! Published to: {target_dir}")

if __name__ == "__main__":
    app()
