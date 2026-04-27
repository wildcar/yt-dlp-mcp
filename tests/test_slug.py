"""Slug / output-path tests."""

from __future__ import annotations

from pathlib import Path

from yt_dlp_mcp.slug import allocate_output_path, channel_slug, video_slug


def test_channel_slug_keeps_cyrillic() -> None:
    assert channel_slug("Алексей Семихатов") == "Алексей Семихатов"


def test_channel_slug_strips_unsafe_chars() -> None:
    # Pipe / hash / colon are filesystem-unfriendly; everything else stays.
    assert channel_slug("Channel | Foo / Bar") == "Channel Foo Bar"


def test_channel_slug_falls_back_when_unrenderable() -> None:
    assert channel_slug("") == "Без канала"
    # All-emoji passes through (emoji are valid filename bytes).
    assert channel_slug("🎬🎬") == "🎬🎬"


def test_video_slug_keeps_punctuation() -> None:
    assert (
        video_slug(
            "Натальная карта #58 Артемий Лебедев | Лебедев, Журавлев, Иванченко",
            video_id="abc",
        )
        == "Натальная карта 58 Артемий Лебедев Лебедев, Журавлев, Иванченко"
    )


def test_video_slug_uses_video_id_on_empty() -> None:
    # Title that cleans to empty (just unsafe chars) → fallback.
    assert video_slug("###|||", video_id="abc123") == "abc123"


def test_video_slug_caps_byte_length() -> None:
    long = "Очень" * 100
    out = video_slug(long, video_id="abc")
    assert len(out.encode("utf-8")) <= 200


def test_allocate_output_path_avoids_collision(tmp_path: Path) -> None:
    base = tmp_path / "Clip"
    p1 = allocate_output_path(base, channel="Veritasium", title="Foo", video_id="aa")
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("")
    p2 = allocate_output_path(base, channel="Veritasium", title="Foo", video_id="bb")
    assert p1 != p2
    assert p2.stem.endswith("-2")
