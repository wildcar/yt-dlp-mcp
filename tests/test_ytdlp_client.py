"""Client-level tests for ``YtDlpClient`` — the subprocess is mocked, real
yt-dlp is never invoked.

Focus: the JSON-payload contract of ``probe`` / ``list_playlist``. yt-dlp
can print a bare ``null`` (valid JSON) on stdout when an extractor matches
the URL but yields no info dict. The client must turn that into a
``YtDlpError`` (the handled path) rather than returning a non-dict that
later crashes ``_to_probe`` with «'NoneType' object has no attribute
'get'» — the exact failure a user hit on a pasted video URL.
"""

from __future__ import annotations

import asyncio

import pytest

from yt_dlp_mcp.clients.ytdlp import YtDlpClient, YtDlpError


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _patch_exec(monkeypatch: pytest.MonkeyPatch, proc: _FakeProc) -> None:
    async def _fake_exec(*args: object, **kwargs: object) -> _FakeProc:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)


async def test_probe_raises_on_null_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_exec(
        monkeypatch,
        _FakeProc(b"null\n", b"ERROR: [youtube] xyz: Unable to extract data\n", 1),
    )
    with pytest.raises(YtDlpError, match="Unable to extract"):
        await YtDlpClient().probe("https://youtu.be/xyz")


async def test_probe_raises_on_non_dict_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    # A JSON array is valid JSON but not an info dict; must not slip through
    # as a dict-typed return value.
    _patch_exec(monkeypatch, _FakeProc(b"[]\n"))
    with pytest.raises(YtDlpError):
        await YtDlpClient().probe("https://youtu.be/xyz")


async def test_probe_returns_dict_on_valid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_exec(monkeypatch, _FakeProc(b'{"id": "abc", "title": "Hi"}'))
    raw = await YtDlpClient().probe("https://youtu.be/abc")
    assert raw["id"] == "abc"


async def test_list_playlist_raises_on_null_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_exec(monkeypatch, _FakeProc(b"null\n", b"ERROR: nope\n", 1))
    with pytest.raises(YtDlpError):
        await YtDlpClient().list_playlist("https://youtube.com/playlist?list=PL1", limit=5)
