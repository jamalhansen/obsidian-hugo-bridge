import os
from pathlib import Path
from typing import Optional
import typer
from typing_extensions import Annotated
from git import Repo

from local_first_common.cli import (
    dry_run_option,
    no_llm_option,
    verbose_option,
    resolve_dry_run,
)
from local_first_common.tracking import register_tool
from .handlers.post import handle_post
from .handlers.find import handle_find

_TOOL = register_tool("obsidian-hugo-bridge")

app = typer.Typer(help="Obsidian to Hugo Converter")
publish_app = typer.Typer(help="Publish content to Hugo")
app.add_typer(publish_app, name="publish")

HUGO_SITE_DIR = os.environ.get("HUGO_SITE_DIR")
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
    slug: Annotated[Optional[str], typer.Option("--slug", "-s", help="Override output slug")] = None,
    dry_run: Annotated[bool, dry_run_option()] = False,
    no_llm: Annotated[bool, no_llm_option()] = False,
    verbose: Annotated[bool, verbose_option()] = False,
    commit: Annotated[bool, typer.Option("--commit", help="Git commit after writing")] = False,
    auto_alt: Annotated[bool, typer.Option("--auto-alt", help="Automatically generate alt text for images using vision LLM")] = False,
    vision_model: Annotated[str, typer.Option("--vision-model", help="Vision model to use for alt text generation")] = "@vision",
):
    """Publish a blog post."""
    dry_run = resolve_dry_run(dry_run, no_llm)
    hugo_dir = hugo_dir or (Path(HUGO_SITE_DIR) if HUGO_SITE_DIR else None)
    if not hugo_dir:
        typer.secho("Error: Hugo site directory not specified. Use --hugo-dir or set HUGO_SITE_DIR.", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    vault_path = vault_path or (Path(OBSIDIAN_VAULT_PATH) if OBSIDIAN_VAULT_PATH else None)
    
    if verbose:
        print(f"🚀 Publishing post: {input_file.name}")
        
    target_dir = handle_post(
        input_file,
        hugo_dir,
        slug=slug,
        vault_path=vault_path,
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
    dry_run: Annotated[bool, dry_run_option()] = False,
    no_llm: Annotated[bool, no_llm_option()] = False,
    verbose: Annotated[bool, verbose_option()] = False,
    commit: Annotated[bool, typer.Option("--commit", help="Git commit after writing")] = False,
    vision_model: Annotated[str, typer.Option("--vision-model", help="Vision model to use for alt text generation")] = "@vision",
):
    """Publish a find."""
    dry_run = resolve_dry_run(dry_run, no_llm)
    hugo_dir = hugo_dir or (Path(HUGO_SITE_DIR) if HUGO_SITE_DIR else None)
    if not hugo_dir:
        typer.secho("Error: Hugo site directory not specified. Use --hugo-dir or set HUGO_SITE_DIR.", fg=typer.colors.RED)
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
