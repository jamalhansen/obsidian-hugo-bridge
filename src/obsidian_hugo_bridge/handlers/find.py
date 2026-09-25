import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import frontmatter
import httpx
from local_first_common.cli import resolve_provider

from ..utils import slugify

_EMBED_SOURCE_TYPE = {"x": "X Post", "bluesky": "Bluesky Post", "mastodon": "Mastodon Post"}


def captured_date(value) -> str:
    """`captured` as YYYY-MM-DD. YAML reads a bare date as a date object, not a string."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()):
        return value.strip()
    return datetime.now().astimezone().date().isoformat()


def detect_social_platform(url: str) -> str | None:
    """Return 'x', 'bluesky', 'mastodon', or None based on URL pattern."""
    if not url:
        return None
    if re.search(r"(twitter\.com|x\.com)/\w+/status/\d+", url):
        return "x"
    if re.search(r"bsky\.app/profile/.+/post/", url):
        return "bluesky"
    if re.search(r"/@[\w]+/\d+$", url):
        return "mastodon"
    return None

def fetch_oembed_html(platform: str, url: str) -> str | None:
    """Fetch pre-rendered embed HTML from the platform's oEmbed API."""
    clean_url = re.sub(r"\?.*$", "", url)
    try:
        if platform == "x":
            api = f"https://publish.twitter.com/oembed?url={quote(clean_url, safe='')}&theme=dark&dnt=true&omit_script=false"
        elif platform == "bluesky":
            api = f"https://embed.bsky.app/oembed?url={quote(url, safe='')}"
        else:
            return None
        
        with httpx.Client() as client:
            resp = client.get(api, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("html", "").strip()
    except Exception as e:  # noqa: BLE001 - oEmbed is a nice-to-have preview; any fetch failure should skip it, not crash the publish
        print(f"⚠️  oEmbed fetch failed for {platform}: {e}")
    return None

def extract_description_from_body(body: str, max_len: int = 160) -> str:
    """Pull the first meaningful paragraph from commentary for meta description."""
    # Strip headings
    text = re.sub(r"^#+\s+.*$", "", body, flags=re.MULTILINE).strip()
    if not text:
        return ""
    first_para = re.split(r"\n\n", text)[0].strip()
    if len(first_para) <= max_len:
        return first_para
    return first_para[:max_len].rsplit(" ", 1)[0] + "..."

def handle_find(
    input_path: Path,
    hugo_dir: Path,
    dry_run: bool = False,
    no_llm: bool = False,
    verbose: bool = False
) -> Path:
    """Handle finds conversion."""
    content = input_path.read_text(encoding="utf-8")
    post = frontmatter.loads(content)
    
    # 1. Extraction and Defaults
    source_title = post.metadata.get("source_title")
    if not source_title:
        # Derive from filename: strip leading "0001-" style prefix
        stem = re.sub(r"^\d+-", "", input_path.stem)
        source_title = stem.replace("-", " ").title()
        
    slug = post.metadata.get("slug") or slugify(source_title)
    slug = slugify(slug)
    
    published = captured_date(post.metadata.get("captured"))
        
    description = post.metadata.get("description")
    if not description:
        if no_llm:
            description = extract_description_from_body(post.content)
        else:
            if verbose:
                print("🧠 Generating meta description with LLM...")
            try:
                llm = resolve_provider(no_llm=no_llm, tool_name="obsidian-hugo-bridge")
                system = "You are a helpful assistant that writes concise meta descriptions for blog posts."
                user = f"Write a 1-sentence meta description (max 160 chars) for this blog post snippet:\n\n{post.content[:1000]}"
                
                llm.source_location = str(input_path)
                llm.item_count = 1
                result = llm.complete(system, user)
                description = result.strip().strip('"')

            except Exception as e:  # noqa: BLE001 - LLM description is best-effort; any failure falls back to the extracted-body description, not a crash
                if verbose:
                    print(f"⚠️  LLM description generation failed: {e}")
                description = extract_description_from_body(post.content)
    
    # 2. Build Hugo Metadata
    hugo_meta: dict[str, Any] = {
        "title": source_title,
        "date": published,
        "draft": False,
    }
    if description:
        hugo_meta["description"] = description
        
    tags = [str(t).lstrip("#").strip() for t in post.metadata.get("tags") or [] if t]
    if tags:
        hugo_meta["tags"] = [t for t in tags if t]
        
    source_url = post.metadata.get("source_url")
    if source_url:
        hugo_meta["source_url"] = source_url
        embed_type = detect_social_platform(source_url)
        if embed_type:
            hugo_meta["embed_type"] = embed_type
            post.metadata.setdefault("source_type", _EMBED_SOURCE_TYPE[embed_type])
            if not dry_run:
                if verbose:
                    print(f"🔗 Fetching {embed_type} oEmbed...")
                embed_html = fetch_oembed_html(embed_type, source_url)
                if embed_html:
                    hugo_meta["embed_html"] = embed_html
            else:
                hugo_meta["embed_html"] = "[LLM MOCK EMBED]"
                
    for field in ["source_title", "source_author", "source_type"]:
        if field in post.metadata:
            hugo_meta[field] = post.metadata[field]
            
    # 3. Setup Directory
    find_dir = hugo_dir / "content" / "finds" / slug
    if not dry_run:
        find_dir.mkdir(parents=True, exist_ok=True)
        
    # 4. Save Output
    new_post = frontmatter.Post(post.content.lstrip(), **hugo_meta)
    final_output = frontmatter.dumps(new_post, sort_keys=False) + "\n"
    
    if dry_run:
        print(f"[dry-run] Would write find to: {find_dir}/index.md")
        if verbose:
            print("-" * 20)
            print(final_output[:500] + "...")
            print("-" * 20)
    else:
        (find_dir / "index.md").write_text(final_output, encoding="utf-8")
        if verbose:
            print(f"   ✓ Written: {find_dir}/index.md")
            
    return find_dir
