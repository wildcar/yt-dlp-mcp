"""ASCII-slug helpers — stable, Plex-friendly file/dir names.

Plex matches video files by the directory + filename pair, so renames
during library scans are expensive (the watch history rebinds). Slugs
here aim for: deterministic, ASCII-only, no spaces, length-capped, and
collision-aware.
"""

from __future__ import annotations

from pathlib import Path

from slugify import slugify as _slugify

# Filesystem-side caps. Linux ext4 / xfs allow 255 bytes per name; we
# stay well under that with multibyte-safe ASCII slugs (each char = 1
# byte after slugify).
_MAX_NAME_LEN = 80
_MAX_CHANNEL_LEN = 60


def channel_slug(channel: str) -> str:
    s = _slugify(channel or "", max_length=_MAX_CHANNEL_LEN, word_boundary=True)
    return s or "unknown-channel"


def video_slug(title: str, *, video_id: str) -> str:
    """Slug for the *file stem*. Falls back to the video id when the
    title slugifies to an empty string (rare — emoji-only titles, etc.).
    """
    s = _slugify(title or "", max_length=_MAX_NAME_LEN, word_boundary=True)
    if not s:
        return video_id
    return s


def allocate_output_path(
    output_dir: Path,
    *,
    channel: str,
    title: str,
    video_id: str,
    extension: str = "mp4",
) -> Path:
    """Resolve a target path inside ``<output_dir>/<channel>/`` that
    doesn't collide with an existing file.

    Same channel + same slug across two videos is rare but possible
    (re-uploads). We append ``-2``, ``-3``, … to the file stem in that
    case rather than overwriting.
    """
    channel_dir = output_dir / channel_slug(channel)
    channel_dir.mkdir(parents=True, exist_ok=True)

    stem = video_slug(title, video_id=video_id)
    candidate = channel_dir / f"{stem}.{extension}"
    if not candidate.exists():
        return candidate

    for n in range(2, 100):
        candidate = channel_dir / f"{stem}-{n}.{extension}"
        if not candidate.exists():
            return candidate

    # 99 collisions on the same slug means something's deeply wrong;
    # fall back to including the video_id to guarantee uniqueness.
    return channel_dir / f"{stem}-{video_id}.{extension}"
