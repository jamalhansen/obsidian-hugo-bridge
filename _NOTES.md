# obsidian-hugo-bridge — Dev Notes

Running log of decisions, discoveries, and model behavior. Updated as the project evolves.

---

## How to run

```bash
# Publish a blog post (dry-run first)
obsidian-hugo publish post path/to/post.md --hugo-dir ~/projects/jamalhansen.com --dry-run --verbose

# Publish for real
obsidian-hugo publish post path/to/post.md --hugo-dir ~/projects/jamalhansen.com

# Publish a find
obsidian-hugo publish find path/to/find.md --hugo-dir ~/projects/jamalhansen.com

# Override slug
obsidian-hugo publish post path/to/post.md --hugo-dir ~/projects/jamalhansen.com --slug my-slug

# With vault path for image search
obsidian-hugo publish post path/to/post.md \
  --hugo-dir ~/projects/jamalhansen.com \
  --vault-path ~/vaults/BrainSync \
  --attachment-folder attachments \
  --attachment-folder images

# Env var shorthand (set in shell profile)
export BLOG_PATH=~/projects/jamalhansen.com
export OBSIDIAN_VAULT_PATH=~/vaults/BrainSync
obsidian-hugo publish post path/to/post.md
```

Run tests:
```bash
uv run pytest
```

---

## Architecture

### python-frontmatter instead of regex YAML parsing

**What:** Uses the `python-frontmatter` library to parse and serialize frontmatter rather than hand-rolled regex.
**Why:** The original `obsidian-to-hugo.py` script used regex for everything. Fine for simple cases but fragile on multiline values, quoted strings, and nested YAML. `python-frontmatter` gives a real parse tree and round-trips correctly.
**Tradeoff:** Adds a dependency; YAML serialization output order can differ from input.

### Theme normalization in a separate module

**What:** PaperMod-specific field transformations live in `themes/papermod.py`, not in the core handler.
**Why:** Keeps `handle_post` and `handle_find` theme-agnostic. A different Hugo theme only needs a new mapping module.
**Tradeoff:** One extra indirection for the common case (everyone using PaperMod).

### LLM auto-alt via vision model

**What:** Optional `--auto-alt` flag generates alt text for images using a local vision model (Ollama default).
**Why:** Blog posts often have images with empty or generic alt text. Auto-generation at publish time costs nothing extra.
**Tradeoff:** Requires a vision-capable model to be running locally. Skipped silently if model unavailable.

### Attachment folder priority search

**What:** `copy_images` checks named attachment folders (e.g. `attachments/`, `images/`) before falling back to full vault `rglob`.
**Why:** Full `rglob` on a large vault is slow. Most images live in a known subfolder.
**Tradeoff:** Requires knowing folder names; falls back to rglob if not found.

---

## Changes Log

Most recent first.

### 2026-04-14 — Fix CLI crash; fix slug stripping; add tag-based folder routing

**Changed:**
- Inlined `dry_run_option()`, `no_llm_option()`, `verbose_option()` calls in `cli.py` — replaced `Annotated[bool, factory()]` pattern with direct `typer.Option(...)` in each annotation.
- Removed `"slug"` from `to_strip` list in `themes/papermod.py`.
- Added `TAG_FOLDERS` routing to `handle_post` — mirrors `obsidian-to-hugo.py`'s tag-based subfolder logic.

**Because:**
- CLI crashed on `--help` with `AttributeError: 'bool' object has no attribute 'isidentifier'`. Root cause: `typer.Option(False, "--dry-run", ...)` passes `False` as a positional arg; newer Click's `_parse_decls` calls `.isidentifier()` on each decl and fails on the bool. Using `Annotated` + a factory that embeds a default this way is the incompatible pattern. Fix: inline options without passing default as positional.
- `papermod.py` was stripping `slug` from output frontmatter. Hugo uses `slug` for URL overrides — removing it silently breaks post URLs for any post that sets it explicitly.
- Tag-based routing (`tsql2sday` → `tsql-tuesday`) existed in the original `obsidian-to-hugo.py` but wasn't ported to the bridge. Posts tagged `tsql2sday` would land in the wrong directory.

**Learned:** `Annotated[T, typer.Option(default, ...)]` is fragile — the default in the `Option()` call and the `= default` in the function signature can conflict depending on Typer/Click version. Inline `typer.Option("--flag", ...)` with `= default` in the signature is unambiguous.

---

## Known Issues / Next Steps

- [ ] Verify dry-run output matches `scripts/obsidian-to-hugo.py` on a real post before switching over
- [ ] `scripts/obsidian-to-hugo.py` converts `published_date:` → `date:` — verify bridge handles this (papermod.py strips `published_date` without converting it; may need fix)
- [ ] Add `target_date`, `post`, `series_position` to `to_strip` (already present; verify they are not in use)
- [ ] Batch mode (`--dir`) not yet implemented

---

## Patterns Observed

- **Annotated + factory option anti-pattern:** Using `Annotated[bool, factory()]` where the factory embeds a default value is fragile across Typer versions. Prefer inline `typer.Option("--flag")` with `= default` in the function signature.
- **Slug-as-routing vs slug-as-URL-override:** The `slug` field serves two purposes — routing the output directory AND overriding the Hugo URL. Stripping it from output frontmatter silently breaks the second purpose even when the first is handled correctly.
