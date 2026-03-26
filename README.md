# Obsidian-to-Hugo Converter (`obsidian-hugo-bridge`)

A standalone CLI tool that converts Obsidian markdown to Hugo-compatible page bundles. Reusable across any Obsidian + Hugo setup, not tied to a specific blog or vault.

## Installation

```bash
uv tool install obsidian-hugo-bridge
```

## Usage

### Publish a blog post
```bash
obsidian-hugo publish post input.md --hugo-dir ~/projects/jamalhansen.com
```

### Publish a "find" (bookmark)
```bash
obsidian-hugo publish find input.md --hugo-dir ~/projects/jamalhansen.com
```

### Preview without writing
```bash
obsidian-hugo publish post input.md --hugo-dir ~/projects/mysite --dry-run
```

## Configuration

The tool respects the following environment variables:
- `HUGO_SITE_DIR`: Path to the Hugo site root.
- `OBSIDIAN_VAULT`: Path to the Obsidian vault root (used for image search).

## Features

- **Frontmatter normalization**: Converts Obsidian fields to PaperMod theme conventions (extensible).
- **Body syntax conversion**: Handles Obsidian wikilinks (`![[image]]`), callouts, etc.
- **Image copying**: Automatically copies referenced images from the source or the vault into the page bundle.
- **Vision-powered Alt Tags**: Automatically generates descriptive alt text for images (including the cover image) using a local Ollama vision model (e.g., `llama3.2-vision`) when `--auto-alt` is used.
- **oEmbed support**: Fetches pre-rendered embed HTML for X, Bluesky, and Mastodon links in "finds".
- **LLM-generated descriptions**: (Optional) Generates meta descriptions if missing.
- **Git integration**: Automatically adds and commits changes if `--commit` is used.

## Tech Stack

- **Python 3.12+**
- **Typer**: CLI interface
- **python-frontmatter**: Metadata parsing
- **httpx**: oEmbed fetching
- **GitPython**: Git integration
- **local-first-common**: Shared utilities and tracking
