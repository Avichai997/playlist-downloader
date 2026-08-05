"""Filename numbering and sanitizing.

With hundreds of videos a plain ``1.`` prefix sorts wrong in Finder and
Explorer — ``10.`` lands directly after ``1.``. Padding to the width of the
playlist keeps lexical order equal to playlist order.
"""
from __future__ import annotations

import re

PADDED = "padded"
PLAIN = "plain"
NONE = "none"

MIN_PAD_WIDTH = 3

_WINDOWS_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAILING_JUNK = re.compile(r"[ .]+$")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def pad_width(total: int, configured: int | None = None) -> int:
    if configured:
        return configured
    return max(MIN_PAD_WIDTH, len(str(max(total, 1))))


def number_prefix(number: int, width: int, mode: str = PADDED) -> str:
    if mode == NONE:
        return ""
    if mode == PLAIN:
        return f"{number}. "
    return f"{number:0{width}d}. "


def output_template(number: int, width: int, mode: str = PADDED) -> str:
    """yt-dlp output template for one video, e.g. ``001. %(title)s.%(ext)s``."""
    return f"{number_prefix(number, width, mode)}%(title)s.%(ext)s"


def sanitize(name: str, *, max_length: int = 120) -> str:
    """Make a string safe as a single path component on macOS and Windows.

    Non-Latin scripts are preserved; only characters that are actually illegal
    or that break round-tripping between the two platforms are replaced.
    """
    cleaned = _WINDOWS_ILLEGAL.sub("_", name).strip()
    cleaned = _TRAILING_JUNK.sub("", cleaned)
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    if len(cleaned) > max_length:
        cleaned = _TRAILING_JUNK.sub("", cleaned[:max_length])
    return cleaned or "untitled"
