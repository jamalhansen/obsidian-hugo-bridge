import json
import os
import shutil
import subprocess
import webbrowser
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import frontmatter
import typer
from git import Repo
from local_first_common.cli import init_config_option, json_option, resolve_dry_run

from .core import OverwriteRefusedError
from .drift import drift_for, published_notes
from .handlers.find import handle_find
from .handlers.post import handle_post
from .site import PREVIEW_DIR, canonical_url
from .writeback import write_back

TOOL_NAME = "obsidian-hugo-bridge"
DEFAULTS = {"provider": "ollama", "model": "llama3"}

app = typer.Typer(help="Obsidian to Hugo Converter")
publish_app = typer.Typer(help="Publish content to Hugo")
app.add_typer(publish_app, name="publish")

BLOG_PATH = os.environ.get("BLOG_PATH")
OBSIDIAN_VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH")
DEFAULT_VAULT_BLOG = Path.home() / "vaults" / "BrainSync" / "blog"

HugoDir = Annotated[Path | None, typer.Option("--hugo-dir", "-d", help="Path to Hugo site root (or BLOG_PATH)")]
VaultPath = Annotated[
    Path | None, typer.Option("--vault-path", "-v", help="Vault root for image search (or OBSIDIAN_VAULT_PATH)")
]
AttachmentFolders = Annotated[
    list[str] | None,
    typer.Option("--attachment-folder", "-a", help="Subfolder in vault to search for images (repeatable)"),
]


def _hugo_dir(hugo_dir: Path | None) -> Path:
    hugo_dir = hugo_dir or (Path(BLOG_PATH) if BLOG_PATH else None)
    if not hugo_dir:
        typer.secho("Error: Hugo site directory not specified. Use --hugo-dir or set BLOG_PATH.", fg=typer.colors.RED)
        raise typer.Exit(1)
    return hugo_dir.expanduser()


def _vault(vault_path: Path | None) -> Path | None:
    return vault_path or (Path(OBSIDIAN_VAULT_PATH) if OBSIDIAN_VAULT_PATH else None)


def commit_changes(hugo_dir: Path, target_dir: Path, slug: str, content_type: str):
    """Git add and commit the changes."""
    try:
        repo = Repo(hugo_dir)
        rel_path = target_dir.relative_to(hugo_dir)
        repo.index.add([str(rel_path)])
        repo.index.commit(f"publish({content_type}): {slug}")
        print(f"   ✓ Committed: publish({content_type}): {slug}")
    except Exception as e:  # noqa: BLE001 - git commit is best-effort here; the file publish itself already succeeded, don't crash on the commit step
        print(f"   ⚠️  Git commit failed: {e}")


def _record_publish(note: Path, hugo_dir: Path, bundle: Path) -> None:
    """Write published_date/canonical_url back to the vault note once a post is live."""
    meta = frontmatter.load(bundle / "index.md").metadata
    if meta.get("draft", True):
        print("   ℹ️  Published as a draft (vault status isn't 'published'); vault note left as is.")
        return
    published = meta.get("date")
    written = write_back(note, {
        "published_date": published.isoformat() if isinstance(published, date) else str(published),
        "canonical_url": canonical_url(hugo_dir, str(meta["slug"])),
    })
    if written:
        print(f"   ✓ Recorded on vault note: {', '.join(f'{k}={v}' for k, v in written.items())}")


@publish_app.command("post")
def publish_post(
    input_file: Annotated[Path, typer.Argument(help="Path to Obsidian markdown file")],
    hugo_dir: HugoDir = None,
    vault_path: VaultPath = None,
    attachment_folder: AttachmentFolders = None,
    slug: Annotated[str | None, typer.Option("--slug", "-s", help="Override output slug")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without writing to disk.")] = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Skip LLM calls. Implies --dry-run.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V", help="Show extra debug output.")] = False,
    commit: Annotated[bool, typer.Option("--commit", help="Git commit after writing")] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace a live post even if it differs from the vault note.")
    ] = False,
    write_back_: Annotated[
        bool,
        typer.Option("--write-back/--no-write-back", help="Record published_date/canonical_url on the vault note."),
    ] = True,
    auto_alt: Annotated[
        bool, typer.Option("--auto-alt", help="Automatically generate alt text for images using vision LLM")
    ] = False,
    vision_model: Annotated[str, typer.Option("--vision-model", help="Vision model for alt text")] = "@vision",
    init_config: Annotated[bool, init_config_option(TOOL_NAME, DEFAULTS)] = False,
):
    """Publish a blog post. Status `published` goes live; any other status publishes as a draft."""
    dry_run = resolve_dry_run(dry_run, no_llm)
    hugo = _hugo_dir(hugo_dir)
    if verbose:
        print(f"🚀 Publishing post: {input_file.name}")

    try:
        target_dir = handle_post(
            input_file,
            hugo,
            slug=slug,
            vault_path=_vault(vault_path),
            attachment_folders=attachment_folder or ["attachments", "images"],
            dry_run=dry_run,
            no_llm=no_llm,
            verbose=verbose,
            auto_alt=auto_alt,
            vision_model=vision_model,
            overwrite=overwrite,
        )
    except OverwriteRefusedError as e:
        typer.echo(str(e))
        typer.secho(
            "\nThe live post differs from the vault note (above: - live, + vault). Backport any edits made "
            "in Hugo to the note, or re-run with --overwrite to replace it.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1) from e

    if dry_run:
        return
    if write_back_:
        _record_publish(input_file, hugo, target_dir)
    if commit:
        commit_changes(hugo, target_dir, slug or target_dir.name, "post")
    print(f"\n🎉 Done! Published to: {target_dir}")


@publish_app.command("find")
def publish_find(
    input_file: Annotated[Path, typer.Argument(help="Path to Obsidian markdown file")],
    hugo_dir: HugoDir = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without writing to disk.")] = False,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Skip LLM calls. Implies --dry-run.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V", help="Show extra debug output.")] = False,
    commit: Annotated[bool, typer.Option("--commit", help="Git commit after writing")] = False,
):
    """Publish a find."""
    dry_run = resolve_dry_run(dry_run, no_llm)
    hugo = _hugo_dir(hugo_dir)
    if verbose:
        print(f"🚀 Publishing find: {input_file.name}")

    target_dir = handle_find(input_file, hugo, dry_run=dry_run, no_llm=no_llm, verbose=verbose)

    if commit and not dry_run:
        commit_changes(hugo, target_dir, target_dir.name, "find")
    if not dry_run:
        print(f"\n🎉 Done! Published to: {target_dir}")


@app.command()
def preview(
    input_file: Annotated[Path, typer.Argument(help="Path to Obsidian markdown file")],
    hugo_dir: HugoDir = None,
    vault_path: VaultPath = None,
    attachment_folder: AttachmentFolders = None,
    port: Annotated[int, typer.Option("--port", "-p", help="hugo server port")] = 1313,
    serve: Annotated[bool, typer.Option("--serve/--no-serve", help="Start hugo server and open the page")] = True,
):
    """Render a vault note in the real theme as a draft, without touching the published site.

    The bundle goes to content/blog/_preview/ (gitignored) and is removed when the server stops.
    """
    hugo = _hugo_dir(hugo_dir)
    target_dir = handle_post(
        input_file, hugo, vault_path=_vault(vault_path),
        attachment_folders=attachment_folder or ["attachments", "images"], preview=True,
    )
    slug = frontmatter.load(target_dir / "index.md").metadata["slug"]
    url = f"http://localhost:{port}{urlparse(canonical_url(hugo, slug)).path}"
    if not serve:
        print(f"Preview bundle written to {target_dir}")
        return
    print(f"Serving {url}  (Ctrl-C to stop; the preview bundle is removed on exit)")
    server = subprocess.Popen(["hugo", "server", "-D", "--port", str(port)], cwd=hugo)
    try:
        webbrowser.open(url)
        server.wait()
    except KeyboardInterrupt:
        server.terminate()
        server.wait()
    finally:
        shutil.rmtree(hugo / PREVIEW_DIR, ignore_errors=True)


@app.command()
def drift(
    vault_blog: Annotated[
        Path, typer.Option("--vault-blog", help="Vault folder holding series/<series>/posts/...")
    ] = DEFAULT_VAULT_BLOG,
    hugo_dir: HugoDir = None,
    show_values: Annotated[bool, typer.Option("--values", help="Show vault vs live values")] = False,
    as_json: Annotated[bool, json_option()] = False,
):
    """List published posts whose vault note and live copy disagree."""
    hugo = _hugo_dir(hugo_dir)
    results = [drift_for(n, hugo) for n in published_notes(vault_blog)]
    if as_json:
        typer.echo(json.dumps([
            {"note": str(d.note), "slug": d.slug, "live": str(d.live) if d.live else None,
             "fields": {k: {"vault": v, "live": lv} for k, (v, lv) in d.fields.items()},
             "body_differs": d.body_differs}
            for d in results if not d.clean
        ], indent=2, default=str))
        return
    for d in results:
        if d.clean:
            continue
        if d.live is None:
            typer.echo(f"✗ {d.slug}: no live post with this slug  ({d.note.relative_to(vault_blog)})")
            continue
        what = list(d.fields) + (["body"] if d.body_differs else [])
        typer.echo(f"≠ {d.slug}: {', '.join(what)}")
        if show_values:
            for name, (v, lv) in d.fields.items():
                typer.echo(f"      {name}: vault={v!r}  live={lv!r}")
    clean = sum(d.clean for d in results)
    typer.echo(f"\n{clean}/{len(results)} published posts match their live copy")


if __name__ == "__main__":
    app()
