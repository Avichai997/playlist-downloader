"""Check GitHub Releases for a newer app version (notify only, never auto-replace).

Tries the GitHub API first, then falls back to following the /releases/latest
redirect (no API quota). Any failure returns None so the app is never blocked.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass

from .. import __version__

REPO = "Avichai997/playlist-downloader"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
_TAG_RE = re.compile(r"/releases/tag/v?([^/?#]+)", re.I)


@dataclass
class UpdateInfo:
    version: str
    url: str  # direct download for this OS, else the releases page


def _ver_tuple(tag: str) -> tuple[int, ...]:
    nums: list[int] = []
    for part in tag.lstrip("vV").split("."):
        digits = "".join(c for c in part if c.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums)


def _platform_suffix() -> str | None:
    if sys.platform == "darwin":
        return ".dmg"
    if sys.platform == "win32":
        return ".exe"
    return None


def _direct_download_url(version: str) -> str:
    suffix = _platform_suffix()
    if suffix == ".dmg":
        filename = "PlaylistDownloader-macOS-arm64.dmg"
    elif suffix == ".exe":
        filename = "PlaylistDownloader.exe"
    else:
        return RELEASES_PAGE
    tag = version if version.startswith("v") else f"v{version}"
    return f"https://github.com/{REPO}/releases/download/{tag}/{filename}"


def _latest_tag_from_redirect(timeout: float = 5.0) -> str | None:
    req = urllib.request.Request(
        RELEASES_PAGE,
        headers={"User-Agent": "playlist-downloader-updater"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        match = _TAG_RE.search(resp.url)
        if match:
            return match.group(1).lstrip("vV")
    return None


def _from_api(current: str, timeout: float) -> UpdateInfo | None:
    req = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "playlist-downloader-updater",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        data = json.load(resp)

    tag = data.get("tag_name") or ""
    if not tag or _ver_tuple(tag) <= _ver_tuple(current):
        return None

    url = RELEASES_PAGE
    suffix = _platform_suffix()
    if suffix:
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(suffix):
                url = asset.get("browser_download_url", url)
                break
    return UpdateInfo(version=tag.lstrip("vV"), url=url)


def check_for_update(current: str = __version__, timeout: float = 5.0) -> UpdateInfo | None:
    try:
        info = _from_api(current, timeout)
        if info:
            return info
    except Exception:
        pass

    try:
        tag = _latest_tag_from_redirect(timeout)
        if tag and _ver_tuple(tag) > _ver_tuple(current):
            return UpdateInfo(version=tag.lstrip("vV"), url=_direct_download_url(tag))
    except Exception:
        pass

    return None
