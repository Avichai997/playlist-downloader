"""Check GitHub Releases for a newer app version (notify only, never auto-replace).

Makes one best-effort HTTPS GET to the GitHub API on launch. Sends no user
data — just reads the latest release tag. Any failure (offline, rate limit)
returns None so the app is never blocked.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass

from .. import __version__

REPO = "Avichai997/playlist-downloader"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


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


def check_for_update(current: str = __version__, timeout: float = 5.0) -> UpdateInfo | None:
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "playlist-downloader-updater",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (pinned HTTPS)
            data = json.load(resp)
    except Exception:
        return None

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
