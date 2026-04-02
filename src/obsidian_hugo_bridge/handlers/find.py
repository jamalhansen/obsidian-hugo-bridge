import re
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import frontmatter
from ..utils import slugify
from local_first_common.cli import resolve_provider
from local_first_common.tracking import timed_run

def detect_social_platform(url: str) -> Optional[str]:
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

def fetch_oembed_html(platform: str, url: str) -> Optional[str]:
    """Fetch pre-rendered embed HTML from the platform's oEmbed API."""
    clean_url = re.sub(r"\?.*$", "", url)
    try:
        if platform == "x":
            api = f"https://publish.twitter.com/oembed?url={clean_url}&theme=dark&dnt=true&omit_script=false"
        elif platform == "bluesky":
            api = f"https://embed.bsky.app/oembed?url={url}"
        else:
            return None
        
        with httpx.Client() as client:
            resp = client.get(api, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("html", "").strip()
    except Exception as e:
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
    
    captured = post.metadata.get("captured")
    if captured and isinstance(captured, (str, datetime)):
        if isinstance(captured, datetime):
            date = captured.strftime("%Y-%m-%d")
        else:
            date = captured
    else:
        date = datetime.now().strftime("%Y-%m-%d")
        
    description = post.metadata.get("description")
    if not description:
        if no_llm:
            description = extract_description_from_body(post.content)
        else:
            if verbose:
                print("🧠 Generating meta description with LLM...")
            try:
                llm = resolve_provider(no_llm=no_llm)
                system = "You are a helpful assistant that writes concise meta descriptions for blog posts."
                user = f"Write a 1-sentence meta description (max 160 chars) for this blog post snippet:\n\n{post.content[:1000]}"
                
                with timed_run("obsidian-hugo-bridge", llm.model, source_location=str(input_path)) as _run:
                    result = llm.complete(system, user)
                    _run.item_count = 1
                    _run.input_tokens = getattr(llm, "input_tokens", None)
                    _run.output_tokens = getattr(llm, "output_tokens", None)
                    description = result.strip().strip('"')
                
            except Exception as e:
                if verbose:
                    print(f"⚠️  LLM description generation failed: {e}")
                description = extract_description_from_body(post.content)
    
    # 2. Build Hugo Metadata
    hugo_meta: Dict[str, Any] = {
        "title": source_title,
        "date": date,
        "draft": False,
    }
    if description:
        hugo_meta["description"] = description
        
    if "tags" in post.metadata:
        hugo_meta["tags"] = post.metadata["tags"]
        
    source_url = post.metadata.get("source_url")
    if source_url:
        hugo_meta["source_url"] = source_url
        embed_type = detect_social_platform(source_url)
        if embed_type:
            hugo_meta["embed_type"] = embed_type
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
    new_post = frontmatter.Post(post.content, **hugo_meta)
    final_output = frontmatter.dumps(new_post)
    
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
