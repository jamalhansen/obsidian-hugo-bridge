from datetime import date
from pathlib import Path

import frontmatter
import pytest
from typer.testing import CliRunner

from obsidian_hugo_bridge.cli import app
from obsidian_hugo_bridge.core import OverwriteRefusedError
from obsidian_hugo_bridge.drift import drift_for
from obsidian_hugo_bridge.handlers.find import captured_date, handle_find
from obsidian_hugo_bridge.handlers.post import handle_post
from obsidian_hugo_bridge.site import canonical_url, existing_bundle
from obsidian_hugo_bridge.themes.papermod import normalize_papermod
from obsidian_hugo_bridge.writeback import apply_updates, write_back

runner = CliRunner()

VAULT_NOTE = """---
title: Joins Explained
slug: joins-explained
status: published
published_date: 2026-02-10
series: '[[SQL for Python Developers]]'
series_position: 7
category: '[[Blog Post]]'
created: 2026-01-20
target_date: 2026-02-10
tags:
- '#sql'
- '#duckdb'
featureimage: joins.jpg
unsplash_name: Ann Photog
canonical_url:
---

Body with ![[diagram.png]] and text.
"""


@pytest.fixture
def site(tmp_path: Path) -> Path:
    hugo = tmp_path / "site"
    (hugo / "content" / "blog").mkdir(parents=True)
    (hugo / "config" / "_default").mkdir(parents=True)
    (hugo / "config" / "_default" / "hugo.yaml").write_text(
        'baseURL: "https://example.com/"\npermalinks:\n  blog: "/blog/:slug/"\n'
    )
    return hugo


@pytest.fixture
def note(tmp_path: Path) -> Path:
    folder = tmp_path / "vault" / "series" / "sql" / "posts" / "07-joins"
    folder.mkdir(parents=True)
    (folder / "joins.jpg").write_bytes(b"jpg")
    (folder / "diagram.png").write_bytes(b"png")
    f = folder / "joins-explained.md"
    f.write_text(VAULT_NOTE, encoding="utf-8")
    return f


class TestNormalize:
    def test_status_decides_draft(self):
        assert normalize_papermod({"status": "published"})["draft"] is False
        assert normalize_papermod({"status": "outline"})["draft"] is True
        assert normalize_papermod({"status": "draft", "draft": False})["draft"] is True
        assert normalize_papermod({"draft": False})["draft"] is False
        assert normalize_papermod({})["draft"] is True

    def test_vault_only_fields_never_reach_hugo(self):
        out = normalize_papermod(frontmatter.loads(VAULT_NOTE).metadata)
        for key in ("status", "category", "created", "target_date", "series_position",
                    "featureimage", "unsplash_name", "canonical_url", "published_date"):
            assert key not in out

    def test_cover_from_featureimage_with_title_alt_and_credit(self):
        out = normalize_papermod({"title": "T", "featureimage": "a.jpg", "unsplash_user": "u"})
        assert out["cover"] == {"image": "a.jpg", "alt": "T", "caption": "", "relative": True,
                                "credit": {"username": "u"}}

    def test_standalone_alt_wins(self):
        assert normalize_papermod({"title": "T", "image": "a.jpg", "alt": "A cat"})["cover"]["alt"] == "A cat"

    def test_capitalized_keys_and_tags(self):
        out = normalize_papermod({"Title": "T", "Tags": ["#a", "", None, "b"], "Series": "S"})
        assert out["title"] == "T"
        assert out["tags"] == ["a", "b"]
        assert out["series"] == ["S"]

    def test_published_date_becomes_date(self):
        assert normalize_papermod({"published_date": date(2026, 2, 10)})["date"] == date(2026, 2, 10)


class TestHandlePost:
    def test_new_series_post_gets_numbered_folder(self, note, site):
        bundle = handle_post(note, site)
        assert bundle == site / "content/blog/sql-for-python-developers/07-joins-explained"
        meta = frontmatter.load(bundle / "index.md").metadata
        assert meta["slug"] == "joins-explained"
        assert meta["draft"] is False
        assert meta["cover"]["image"] == "joins.jpg"
        assert (bundle / "joins.jpg").exists()
        assert "![Image](diagram.png)" in (bundle / "index.md").read_text()

    def test_republish_reuses_existing_bundle_wherever_it_lives(self, note, site):
        legacy = site / "content/blog/old-place/joins-explained"
        legacy.mkdir(parents=True)
        (legacy / "index.md").write_text("---\nslug: joins-explained\n---\nold\n")
        assert existing_bundle(site, "joins-explained") == legacy
        assert handle_post(note, site) == legacy

    def test_overwrite_refused_leaves_everything_untouched(self, note, site):
        live = site / "content/blog/sql-for-python-developers/07-joins-explained"
        live.mkdir(parents=True)
        (live / "index.md").write_text("---\nslug: joins-explained\n---\nEdited in Hugo\n")
        with pytest.raises(OverwriteRefusedError) as err:
            handle_post(note, site, overwrite=False)
        assert "- Edited in Hugo" in str(err.value) or "-Edited in Hugo" in str(err.value)
        assert (live / "index.md").read_text().endswith("Edited in Hugo\n")
        assert not (live / "joins.jpg").exists()

    def test_identical_republish_is_allowed_without_overwrite(self, note, site):
        handle_post(note, site)
        handle_post(note, site, overwrite=False)

    def test_preview_is_a_draft_outside_the_published_tree(self, note, site):
        bundle = handle_post(note, site, preview=True)
        assert bundle == site / "content/blog/_preview/joins-explained"
        assert frontmatter.load(bundle / "index.md").metadata["draft"] is True
        assert existing_bundle(site, "joins-explained") is None


class TestWriteBack:
    def test_fills_missing_and_empty_fields_only(self, note, tmp_path):
        before = note.read_text()
        written = write_back(note, {"canonical_url": "https://example.com/blog/joins-explained/",
                                    "published_date": "2099-01-01"}, backup_dir=tmp_path / "bk")
        assert written == {"canonical_url": "https://example.com/blog/joins-explained/"}
        after = note.read_text()
        assert "canonical_url: https://example.com/blog/joins-explained/\n" in after
        assert "published_date: 2026-02-10" in after
        assert after.replace("canonical_url: https://example.com/blog/joins-explained/\n", "canonical_url:\n") == before
        assert list((tmp_path / "bk").rglob("joins-explained.md"))

    def test_no_change_means_no_backup(self, note, tmp_path):
        assert write_back(note, {"title": "x"}, backup_dir=tmp_path / "bk") == {}
        assert not (tmp_path / "bk").exists()

    def test_appends_a_new_key_inside_the_block(self):
        assert apply_updates("---\na: 1\n---\nbody\n", {"b": "2"}) == "---\na: 1\nb: 2\n---\nbody\n"


def test_canonical_url_uses_site_config(site):
    assert canonical_url(site, "x") == "https://example.com/blog/x/"


class TestCli:
    def test_publish_records_url_and_date_on_the_note(self, note, site):
        result = runner.invoke(app, ["publish", "post", str(note), "--hugo-dir", str(site)])
        assert result.exit_code == 0, result.output
        assert "canonical_url: https://example.com/blog/joins-explained/" in note.read_text()

    def test_draft_publish_leaves_the_note_alone(self, note, site):
        note.write_text(VAULT_NOTE.replace("status: published", "status: draft"))
        before = note.read_text()
        result = runner.invoke(app, ["publish", "post", str(note), "--hugo-dir", str(site)])
        assert result.exit_code == 0, result.output
        assert note.read_text() == before

    def test_refusal_exits_1_with_the_diff(self, note, site):
        live = site / "content/blog/sql-for-python-developers/07-joins-explained"
        live.mkdir(parents=True)
        (live / "index.md").write_text("---\nslug: joins-explained\n---\nEdited in Hugo\n")
        result = runner.invoke(app, ["publish", "post", str(note), "--hugo-dir", str(site)])
        assert result.exit_code == 1
        assert "--overwrite" in result.output
        ok = runner.invoke(app, ["publish", "post", str(note), "--hugo-dir", str(site), "--overwrite"])
        assert ok.exit_code == 0, ok.output


def test_drift_reports_fields_and_body(note, site):
    handle_post(note, site)
    live = site / "content/blog/sql-for-python-developers/07-joins-explained/index.md"
    post = frontmatter.load(live)
    post["title"] = "Joins, Explained"
    post.content += "\nA cross-link added in Hugo."
    live.write_text(frontmatter.dumps(post))
    d = drift_for(note, site)
    assert d.fields == {"title": ("Joins Explained", "Joins, Explained")}
    assert d.body_differs


class TestFinds:
    def test_captured_date_accepts_yaml_dates(self):
        assert captured_date(date(2026, 9, 1)) == "2026-09-01"
        assert captured_date("2026-09-01") == "2026-09-01"

    def test_find_fields(self, tmp_path, site):
        (site / "content" / "finds").mkdir()
        f = tmp_path / "0001-a-find.md"
        f.write_text("---\nsource_title: A Find\nsource_url: https://example.com/@me/123\n"
                     "captured: 2026-09-01\ntags: ['#ai']\n---\n\nWorth reading.\n")
        bundle = handle_find(f, site, no_llm=True)
        meta = frontmatter.load(bundle / "index.md").metadata
        assert str(meta["date"]) == "2026-09-01"
        assert meta["tags"] == ["ai"]
        assert meta["source_type"] == "Mastodon Post"


def test_formatting_only_differences_do_not_block(note, site):
    bundle = handle_post(note, site)
    index = bundle / "index.md"
    post = frontmatter.load(index)
    reformatted = frontmatter.dumps(post, sort_keys=True, default_flow_style=True)
    index.write_text(reformatted)
    handle_post(note, site, overwrite=False)
