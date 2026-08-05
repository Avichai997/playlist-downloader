"""Error types surfaced to the UI."""
from __future__ import annotations


class PlaylistDownloaderError(Exception):
    """Base class for every error this app raises deliberately."""


class MissingBinaryError(PlaylistDownloaderError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"Could not find {name}. Run `python fetch_binaries.py` to download the "
            f"engines this app needs, or install {name} so it is on your PATH."
        )
        self.name = name


class ExtractionError(PlaylistDownloaderError):
    """yt-dlp could not read the playlist or video metadata."""


class DownloadFailed(PlaylistDownloaderError):
    """Every retry strategy for a video was exhausted."""


class VerificationFailed(PlaylistDownloaderError):
    """The finished file is missing, empty, truncated, or unreadable."""
