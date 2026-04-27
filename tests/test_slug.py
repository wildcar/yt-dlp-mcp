"""Slug / output-path tests."""

from __future__ import annotations

from pathlib import Path

from yt_dlp_mcp.slug import allocate_output_path, channel_slug, video_slug


def test_channel_slug_transliterates_cyrillic() -> None:
    assert channel_slug("Алексей Семихатов") == "aleksei-semikhatov"


def test_channel_slug_falls_back_when_unrenderable() -> None:
    assert channel_slug("") == "unknown-channel"
    # Emoji-only — slugify drops everything, fallback kicks in.
    assert channel_slug("🎬🎬") == "unknown-channel"


def test_video_slug_uses_video_id_on_empty() -> None:
    assert video_slug("🎬", video_id="abc123") == "abc123"


def test_video_slug_caps_length() -> None:
    long = "The " + "very " * 50 + "long title"
    out = video_slug(long, video_id="abc")
    assert len(out) <= 80


def test_allocate_output_path_avoids_collision(tmp_path: Path) -> None:
    base = tmp_path / "Clip"
    p1 = allocate_output_path(base, channel="Veritasium", title="Foo", video_id="aa")
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("")
    p2 = allocate_output_path(base, channel="Veritasium", title="Foo", video_id="bb")
    assert p1 != p2
    assert p2.stem.endswith("-2")
