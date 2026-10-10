from obsidian_hugo_bridge.core import (
    ConversionError,
    HugoBridgeError,
    ImageAltError,
    convert_body_syntax,
    strip_leading_h1,
)
from obsidian_hugo_bridge.themes.papermod import normalize_papermod
from obsidian_hugo_bridge.utils import clean_wikilinks, slugify


class TestTypedErrors:
    def test_error_hierarchy(self):
        assert issubclass(ImageAltError, HugoBridgeError)
        assert issubclass(ConversionError, HugoBridgeError)

    def test_image_alt_error_message(self):
        err = ImageAltError("vision model unavailable")
        assert "vision model unavailable" in str(err)


def test_slugify():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Python & AI") == "python-ai"
    assert slugify("  Extra   Spaces  ") == "extra-spaces"


def test_clean_wikilinks():
    assert clean_wikilinks("[[Link]]") == "Link"
    assert clean_wikilinks("Text with [[Link]] and [[Another]]") == "Text with Link and Another"
    assert clean_wikilinks("[[Link|Alias]]") == "Alias"
    assert clean_wikilinks("[[Link#Header]]") == "Link"
    assert clean_wikilinks("[[Link#Header|Alias]]") == "Alias"
    assert clean_wikilinks("Check [[Post|this out]]") == "Check this out"


def test_convert_body_syntax():
    body = "![[image.jpg]]\n![[photo.png|Alt Text]]\n> [!info] Tip\n> Content"
    converted = convert_body_syntax(body)
    assert "![Image](image.jpg)" in converted
    assert "![Alt Text](photo.png)" in converted
    assert "> **info**: Tip" in converted


def test_normalize_papermod():
    metadata = {
        "summary": "Short description",
        "toc": True,
        "image": "cover.jpg",
        "unsplash_name": "John Doe",
        "series": "My Series",
    }
    normalized = normalize_papermod(metadata)
    assert normalized["description"] == "Short description"
    assert normalized["ShowToc"] is True
    assert normalized["cover"]["image"] == "cover.jpg"
    assert normalized["cover"]["credit"]["name"] == "John Doe"
    assert normalized["series"] == ["My Series"]
    assert "summary" not in normalized
    assert "toc" not in normalized


def test_strip_leading_h1_only_when_it_repeats_the_title():
    body = "# The Same Bug, Three Ways\n\n> Starter.\n\n## The hook\n"
    assert strip_leading_h1(body, "The Same Bug, Three Ways") == ("> Starter.\n\n## The hook\n", True)
    assert strip_leading_h1(body, "the same bug three ways") == ("> Starter.\n\n## The hook\n", True)
    # a different H1 is the author's; a body without one is untouched
    assert strip_leading_h1(body, "Another Title") == (body, False)
    assert strip_leading_h1("## Section\n", "Section") == ("## Section\n", False)
    assert strip_leading_h1("", "Anything") == ("", False)


def test_drift_ignores_published_notes_that_are_not_blog_posts(tmp_path):
    from obsidian_hugo_bridge.drift import published_notes

    blog = tmp_path / "blog"
    (blog / "posts").mkdir(parents=True)
    (blog / "posts" / "post.md").write_text("---\nstatus: published\ncategory: '[[Blog Post]]'\n---\nx\n")
    (blog / "posts" / "linkedin.md").write_text("---\nstatus: published\ncategory: '[[LinkedIn Post]]'\n---\nx\n")
    (blog / "posts" / "legacy.md").write_text("---\nstatus: published\n---\nx\n")
    assert sorted(p.name for p in published_notes(blog)) == ["legacy.md", "post.md"]
