"""2026-10-10: git-aware live-edit guard, bundle image sizing, --promote, and the status warning."""

import subprocess
from datetime import date
from pathlib import Path

import frontmatter
import pytest
from PIL import Image
from typer.testing import CliRunner

from obsidian_hugo_bridge.cli import app
from obsidian_hugo_bridge.core import HugoBridgeError, OverwriteRefusedError, published_image_name
from obsidian_hugo_bridge.handlers.post import handle_post, promote_note
from obsidian_hugo_bridge.site import index_is_tracked

runner = CliRunner()

NOTE = """---
title: Two Artists
slug: two-artists
status: draft
category: '[[Blog Post]]'
created: 2026-10-01
tags:
- art
cover:
  image: cover.png
  alt: A cover
---
Body with ![[wide.png]] and ![[glass.png]] and ![[photo.jpg]].
"""


@pytest.fixture
def site(tmp_path: Path) -> Path:
    hugo = tmp_path / "site"
    (hugo / "content" / "blog").mkdir(parents=True)
    (hugo / "config" / "_default").mkdir(parents=True)
    (hugo / "config" / "_default" / "hugo.yaml").write_text('baseURL: "https://example.com/"\n')
    return hugo


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    folder = v / "blog" / "starters" / "from-building" / "two-artists"
    folder.mkdir(parents=True)
    Image.new("RGB", (2400, 1200), "red").save(folder / "wide.png")
    Image.new("RGBA", (2400, 600), (0, 0, 0, 0)).save(folder / "glass.png")
    Image.new("RGB", (800, 400), "blue").save(folder / "photo.jpg", quality=90)
    Image.new("RGB", (1024, 576), "green").save(folder / "cover.png")
    (folder / "two-artists.md").write_text(NOTE, encoding="utf-8")
    return v


@pytest.fixture
def note(vault: Path) -> Path:
    return vault / "blog" / "starters" / "from-building" / "two-artists" / "two-artists.md"


def _git(site: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=site, check=True, capture_output=True
    )


def _cover_image(index: Path) -> str:
    cover = frontmatter.load(str(index)).metadata["cover"]
    assert isinstance(cover, dict)
    return str(cover["image"])


class TestImages:
    def test_resized_and_opaque_pngs_become_jpeg_with_references_rewritten(self, note: Path, vault: Path, site: Path):
        bundle = handle_post(note, site, vault_path=vault)
        assert sorted(p.name for p in bundle.iterdir()) == [
            "cover.jpg",
            "glass.png",
            "index.md",
            "photo.jpg",
            "wide.jpg",
        ]
        assert Image.open(bundle / "wide.jpg").size == (1600, 800)
        glass = Image.open(bundle / "glass.png")
        assert (glass.size, glass.mode) == ((1600, 400), "RGBA")  # transparency keeps PNG
        assert (bundle / "photo.jpg").read_bytes() == (note.parent / "photo.jpg").read_bytes()  # small: untouched
        post = frontmatter.load(str(bundle / "index.md"))
        assert _cover_image(bundle / "index.md") == "cover.jpg"
        assert "(wide.jpg)" in post.content and "(glass.png)" in post.content and "wide.png" not in post.content
        # the vault is never modified
        assert (note.parent / "wide.png").exists() and not (note.parent / "wide.jpg").exists()

    def test_republish_is_deterministic_so_the_guard_stays_quiet(self, note: Path, vault: Path, site: Path):
        bundle = handle_post(note, site, vault_path=vault)
        first = (bundle / "index.md").read_text()
        handle_post(note, site, vault_path=vault, overwrite=False)
        assert (bundle / "index.md").read_text() == first

    def test_keep_images_copies_bytes(self, note: Path, vault: Path, site: Path):
        bundle = handle_post(note, site, vault_path=vault, keep_images=True)
        assert (bundle / "wide.png").read_bytes() == (note.parent / "wide.png").read_bytes()
        assert _cover_image(bundle / "index.md") == "cover.png"

    def test_max_width_is_a_knob(self, note: Path, vault: Path, site: Path):
        bundle = handle_post(note, site, vault_path=vault, max_width=600)
        assert Image.open(bundle / "wide.jpg").size == (600, 300)
        assert Image.open(bundle / "photo.jpg").size == (600, 300)

    def test_unreadable_image_ships_as_is(self, tmp_path: Path):
        fake = tmp_path / "x.png"
        fake.write_bytes(b"not a png")
        assert published_image_name("x.png", fake) == "x.png"


class TestLiveGuard:
    def test_untracked_bundle_is_not_live(self, note: Path, vault: Path, site: Path):
        _git(site, "init", "-q")
        bundle = handle_post(note, site, vault_path=vault)
        assert not index_is_tracked(site, bundle / "index.md")
        note.write_text(NOTE.replace("Body with", "Edited body with"), encoding="utf-8")
        handle_post(note, site, vault_path=vault, overwrite=False)  # no refusal
        assert "Edited body" in (bundle / "index.md").read_text()

    def test_tracked_bundle_is_live_even_with_uncommitted_changes(self, note: Path, vault: Path, site: Path):
        _git(site, "init", "-q")
        bundle = handle_post(note, site, vault_path=vault)
        _git(site, "add", ".")
        _git(site, "commit", "-qm", "publish")
        assert index_is_tracked(site, bundle / "index.md")
        (bundle / "index.md").write_text((bundle / "index.md").read_text() + "\nHand edit in Hugo\n")
        with pytest.raises(OverwriteRefusedError):
            handle_post(note, site, vault_path=vault, overwrite=False)

    def test_outside_git_everything_counts_as_live(self, note: Path, vault: Path, site: Path):
        bundle = handle_post(note, site, vault_path=vault)
        assert index_is_tracked(site, bundle / "index.md")
        note.write_text(NOTE.replace("Body with", "Edited body with"), encoding="utf-8")
        with pytest.raises(OverwriteRefusedError):
            handle_post(note, site, vault_path=vault, overwrite=False)


class TestPromote:
    def test_moves_the_starter_folder_into_posts_by_month(self, note: Path, vault: Path):
        moved = promote_note(note, vault, today=date(2026, 10, 10))
        assert moved == vault / "blog" / "posts" / "2026" / "10" / "two-artists" / "two-artists.md"
        assert not note.parent.exists()
        assert (moved.parent / "wide.png").exists()
        # already outside starters: left alone
        assert promote_note(moved, vault) == moved

    def test_published_date_decides_the_month_and_existing_folder_is_refused(self, note: Path, vault: Path):
        note.write_text(NOTE.replace("status: draft", "status: published\npublished_date: 2026-02-10"))
        moved = promote_note(note, vault, today=date(2026, 10, 10))
        assert moved.parent == vault / "blog" / "posts" / "2026" / "02" / "two-artists"
        again = vault / "blog" / "starters" / "from-seeds" / "two-artists" / "two-artists.md"
        again.parent.mkdir(parents=True)
        again.write_text(NOTE)
        with pytest.raises(HugoBridgeError):
            promote_note(again, vault, today=date(2026, 2, 1))
        assert again.exists()

    def test_cli_promotes_then_publishes(self, note: Path, vault: Path, site: Path):
        result = runner.invoke(
            app, ["publish", "post", str(note), "--hugo-dir", str(site), "--vault-path", str(vault), "--promote"]
        )
        assert result.exit_code == 0, result.output
        assert "Promoted to blog/posts/" in result.output
        assert not note.exists()
        assert (site / "content" / "blog" / "two-artists" / "wide.jpg").exists()

    def test_cli_promote_needs_a_vault(self, note: Path, site: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("obsidian_hugo_bridge.cli.OBSIDIAN_VAULT_PATH", None)
        result = runner.invoke(app, ["publish", "post", str(note), "--hugo-dir", str(site), "--promote"])
        assert result.exit_code == 1 and "--vault-path" in result.output


def test_unknown_status_warns_and_publishes_as_draft(
    note: Path, vault: Path, site: Path, capsys: pytest.CaptureFixture[str]
):
    note.write_text(NOTE.replace("status: draft", "status: editing"), encoding="utf-8")
    bundle = handle_post(note, site, vault_path=vault)
    assert "status 'editing' isn't one of outline, draft, published" in capsys.readouterr().out
    assert frontmatter.load(str(bundle / "index.md")).metadata["draft"] is True
