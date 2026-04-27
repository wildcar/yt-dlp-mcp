"""Filename helpers for downloaded videos.

We keep the original title and channel name as the human reads them —
Cyrillic, accents, mixed scripts — and only strip characters that are
unsafe on the filesystem (or that mangle URLs / shells later in the
pipeline). Linux ext4 and Plex both handle Unicode names fine; the
old all-ASCII transliteration was over-cautious.

Removed characters get replaced with a space, then runs of whitespace
collapse to a single space and the result is trimmed. Length is capped
at a UTF-8 *byte* count because ext4 caps file names at 255 bytes.
"""

from __future__ import annotations

import re
from pathlib import Path

# Filesystem caps (UTF-8 bytes, not characters). 200 leaves room for
# a "-2"/"-3" collision suffix and the ".mp4" extension under the
# 255-byte limit.
_MAX_NAME_BYTES = 200
_MAX_CHANNEL_BYTES = 150

# Characters we replace with a space before name normalisation:
# - / \\           — path separators (Linux + Windows)
# - : * ? " < > | — Windows-reserved (keep names portable for backups)
# - #              — fragment / route confusion
# - control chars  — never useful in a filename
_UNSAFE_RE = re.compile(r'[\\/:*?"<>|#\x00-\x1f]')
_WHITESPACE_RE = re.compile(r"\s+")


def _clean(name: str, *, max_bytes: int) -> str:
    s = _UNSAFE_RE.sub(" ", name or "")
    s = _WHITESPACE_RE.sub(" ", s).strip()
    # Strip trailing dots / spaces — POSIX accepts them but most cross-
    # platform tooling chokes (Windows refuses, Samba normalises away).
    s = s.rstrip(". ")
    if not s:
        return s
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    # Truncate by bytes, then back up to a valid UTF-8 boundary.
    truncated = encoded[:max_bytes]
    while truncated and (truncated[-1] & 0xC0) == 0x80:
        truncated = truncated[:-1]
    return truncated.decode("utf-8", errors="ignore").rstrip(". ")


def channel_slug(channel: str) -> str:
    return _clean(channel, max_bytes=_MAX_CHANNEL_BYTES) or "Без канала"


def video_slug(title: str, *, video_id: str) -> str:
    """Cleaned-up filename stem. Falls back to ``video_id`` when the
    title cleans to an empty string (emoji-only titles, single-`#`,
    etc.)."""
    return _clean(title, max_bytes=_MAX_NAME_BYTES) or video_id


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
