#!/usr/bin/env python3
"""Populate bin/<platform>/ with the engines the app runs.

  yt-dlp            the downloader itself, as the official standalone build so
                    it can update itself in place at runtime
  ffmpeg, ffprobe   merging video with audio, embedding subtitles and
                    thumbnails, and verifying that finished files are complete

macOS takes static arm64 builds rather than Homebrew's, which would drag in a
hundred-odd dylibs. Windows takes yt-dlp's own ffmpeg build, which carries
patches for exactly this use.

Run once per target platform, on that platform.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import platform
import shutil
import ssl
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

YTDLP_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_ASSETS = {"darwin": "yt-dlp_macos", "win32": "yt-dlp.exe"}

FFMPEG_STATIC_TAG = "b6.1.1"
FFMPEG_STATIC_URL = (
    "https://github.com/eugeneware/ffmpeg-static/releases/download/"
    f"{FFMPEG_STATIC_TAG}/{{name}}-darwin-arm64.gz"
)
FFMPEG_WINDOWS_ZIP = (
    "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)


def platform_tag() -> str:
    if sys.platform == "darwin":
        return "darwin-arm64" if platform.machine() == "arm64" else "darwin-x86_64"
    if sys.platform == "win32":
        return "win-amd64"
    return f"{sys.platform}-{platform.machine()}"


def _ssl_context() -> ssl.SSLContext:
    """Python installed from python.org ships without usable root certificates."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _request_headers() -> dict[str, str]:
    headers = {"User-Agent": "playlist-downloader-build"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    return headers


def _get(url: str, *, timeout: int = 300) -> bytes:
    request = urllib.request.Request(url, headers=_request_headers())
    with urllib.request.urlopen(  # noqa: S310
        request, timeout=timeout, context=_ssl_context()
    ) as response:
        return response.read()


def _write_executable(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  {destination.name}  ({len(payload) / 1e6:.1f} MB)")


def fetch_ytdlp(dest: Path) -> None:
    asset_name = YTDLP_ASSETS.get(sys.platform)
    if not asset_name:
        print(f"  ! no yt-dlp build listed for {sys.platform}")
        return

    release = json.loads(_get(YTDLP_LATEST_API, timeout=60))
    url = next(
        (asset["browser_download_url"] for asset in release["assets"] if asset["name"] == asset_name),
        None,
    )
    if url is None:
        sys.exit(f"yt-dlp release {release.get('tag_name')} has no asset named {asset_name}")

    print(f"yt-dlp {release.get('tag_name')}")
    suffix = ".exe" if sys.platform == "win32" else ""
    _write_executable(dest / f"yt-dlp{suffix}", _get(url))


def fetch_ffmpeg_macos(dest: Path) -> None:
    print(f"ffmpeg {FFMPEG_STATIC_TAG} (static arm64)")
    for name in ("ffmpeg", "ffprobe"):
        payload = gzip.decompress(_get(FFMPEG_STATIC_URL.format(name=name)))
        _write_executable(dest / name, payload)


def fetch_ffmpeg_windows(dest: Path) -> None:
    print("ffmpeg (yt-dlp build, win64-gpl)")
    archive = zipfile.ZipFile(io.BytesIO(_get(FFMPEG_WINDOWS_ZIP)))
    wanted = {"ffmpeg.exe", "ffprobe.exe"}
    for member in archive.namelist():
        name = Path(member).name
        if name in wanted:
            _write_executable(dest / name, archive.read(member))
            wanted.discard(name)
    if wanted:
        sys.exit(f"ffmpeg archive was missing {', '.join(sorted(wanted))}")


def codesign_adhoc(dest: Path) -> None:
    """arm64 refuses to run binaries without a valid signature."""
    if not shutil.which("codesign"):
        return
    for candidate in dest.iterdir():
        if candidate.is_file() and not candidate.suffix:
            subprocess.run(
                ["codesign", "--force", "--sign", "-", str(candidate)],
                check=False,
                capture_output=True,
            )
    print("  ad-hoc signed")


def main() -> None:
    tag = platform_tag()
    dest = ROOT / "bin" / tag
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Target platform: {tag}\n")

    fetch_ytdlp(dest)
    if sys.platform == "darwin":
        fetch_ffmpeg_macos(dest)
        codesign_adhoc(dest)
    elif sys.platform == "win32":
        fetch_ffmpeg_windows(dest)
    else:
        print("  ! ffmpeg is not auto-bundled on this platform; install it yourself")

    print(f"\nDone. Engines are in {dest}")


if __name__ == "__main__":
    main()
