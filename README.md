# Obsidian-to-Hugo Converter (`obsidian-hugo-bridge`)

A standalone CLI tool that converts Obsidian markdown to Hugo-compatible page bundles. Reusable across any Obsidian + Hugo setup, not tied to a specific blog or vault.

## Installation

```bash
uv tool install obsidian-hugo-bridge
```

## Usage

```bash
obsidian-hugo publish post <note.md> --hugo-dir ~/projects/jamalhansen.com --vault-path ~/vaults/BrainSync
obsidian-hugo publish find <find.md> --hugo-dir ~/projects/jamalhansen.com
obsidian-hugo preview <note.md> --hugo-dir ~/projects/jamalhansen.com   # draft render in the real theme
obsidian-hugo drift --hugo-dir ~/projects/jamalhansen.com               # vault vs live disagreements
obsidian-hugo check --hugo-dir ~/projects/jamalhansen.com [index.md ...]  # frontmatter shape errors
```

`check` catches what hand edits in Hugo introduce: a block indented under the wrong key, a missing
description or date, empty tags, a scalar where Hugo wants a list, a cover image without alt text.
It exits 1 on errors, so it can gate a pre-commit hook.

`--dry-run` previews without writing. `BLOG_PATH` / `OBSIDIAN_VAULT_PATH` can stand in for
`--hugo-dir` / `--vault-path`. The blog repo wraps these as `make publish POST=...`,
`make find FIND=...`, `make preview POST=...` and `make drift`.

## What publishing does

- **Status decides visibility.** `status: published` publishes live (`draft: false`); any other
  status (`draft`, `outline`, ...) publishes as a Hugo draft.
- **Placement comes from the note.** A post already on the site is overwritten in place, wherever
  its bundle lives. A new post goes to `content/blog/<series-slug>/<NN>-<slug>/` (NN from
  `series_position`) or `content/blog/<slug>/`; `#tsql2sday` posts go to `tsql-tuesday/`.
- **Only Hugo fields reach Hugo.** Frontmatter is mapped to PaperMod (`summary` → `description`,
  `toc` → `ShowToc`, `published_date` → `date`, `image`/`featureimage` + `alt` + `unsplash_*` →
  `cover`); vault-only fields (`status`, `created`, `target_date`, the note-type `category`, ...)
  are dropped. A cover without `alt:` uses the title so it's never unlabeled.
- **Live edits are protected.** If the live `index.md` differs from what the note would produce
  (cross-links, alt text or test annotations added in Hugo), publishing stops and prints the diff.
  Backport the edits to the note, or pass `--overwrite`.
- **The vault learns what's live.** After a live publish, missing `published_date` and
  `canonical_url` are filled in on the note (line-level edit, backed up to
  `~/.local/share/obsidian-hugo-bridge/backups/` first). `--no-write-back` skips it.
- Images next to the note or referenced from the vault are copied into the bundle;
  `--auto-alt` writes alt text with a local vision model; finds get oEmbed HTML for X/Bluesky.

`preview` writes the bundle to `content/blog/_preview/` (gitignore it), runs `hugo server -D`,
opens the page, and deletes the bundle when the server stops.

## Tech Stack

- **Python 3.12+**
- **Typer**: CLI interface
- **python-frontmatter**: Metadata parsing
- **httpx**: oEmbed fetching
- **GitPython**: Git integration
- **local-first-common**: Shared utilities and tracking
