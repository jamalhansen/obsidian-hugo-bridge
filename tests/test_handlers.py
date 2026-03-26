import pytest
from unittest.mock import patch
from obsidian_hugo_bridge.handlers.post import handle_post
from obsidian_hugo_bridge.handlers.find import handle_find

@pytest.fixture
def mock_hugo_dir(tmp_path):
    hugo_dir = tmp_path / "hugo"
    hugo_dir.mkdir()
    (hugo_dir / "content").mkdir()
    (hugo_dir / "content" / "blog").mkdir()
    (hugo_dir / "content" / "finds").mkdir()
    return hugo_dir

@pytest.fixture
def mock_input_file(tmp_path):
    input_file = tmp_path / "post.md"
    input_file.write_text("---\ntitle: Test Post\n---\n# Body content", encoding="utf-8")
    return input_file

def test_handle_post_basic(mock_input_file, mock_hugo_dir):
    target_dir = handle_post(mock_input_file, mock_hugo_dir, dry_run=False)
    assert target_dir.exists()
    assert (target_dir / "index.md").exists()
    assert "Test Post" in (target_dir / "index.md").read_text()

def test_handle_find_basic(tmp_path, mock_hugo_dir):
    input_file = tmp_path / "find.md"
    input_file.write_text("---\nsource_title: Great Resource\nsource_url: https://example.com\n---\nCommentary", encoding="utf-8")
    
    target_dir = handle_find(input_file, mock_hugo_dir, dry_run=False, no_llm=True)
    assert target_dir.exists()
    assert (target_dir / "index.md").exists()
    content = (target_dir / "index.md").read_text()
    assert "Great Resource" in content
    assert "source_url: https://example.com" in content

def test_handle_post_auto_alt(mock_input_file, mock_hugo_dir):
    # Setup cover image in input
    mock_input_file.write_text("---\ntitle: Post\nimage: cover.jpg\n---\n![](img.png)", encoding="utf-8")
    
    # Create fake image files in a fake blog dir
    target_blog_dir = mock_hugo_dir / "content" / "blog" / "post"
    target_blog_dir.mkdir(parents=True, exist_ok=True)
    (target_blog_dir / "cover.jpg").write_text("fake")
    (target_blog_dir / "img.png").write_text("fake")

    with patch("obsidian_hugo_bridge.handlers.post.generate_image_alt") as mock_gen:
        mock_gen.return_value = "A generated description"
        
        target_dir = handle_post(
            mock_input_file, 
            mock_hugo_dir, 
            dry_run=False, 
            auto_alt=True
        )
        
        content = (target_dir / "index.md").read_text()
        assert "alt: A generated description" in content
        assert "![A generated description](img.png)" in content
