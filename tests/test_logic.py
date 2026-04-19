from obsidian_hugo_bridge.utils import slugify, clean_wikilinks
from obsidian_hugo_bridge.logic import (
    convert_body_syntax,
    HugoBridgeError,
    ImageAltError,
    ConversionError,
)
from obsidian_hugo_bridge.themes.papermod import normalize_papermod


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
    assert (
        clean_wikilinks("Text with [[Link]] and [[Another]]")
        == "Text with Link and Another"
    )
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
