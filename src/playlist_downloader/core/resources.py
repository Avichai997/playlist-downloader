"""Locate the engine binaries (yt-dlp, ffmpeg, ffprobe).

Both a source checkout and a frozen build keep them in ``bin/<platform-tag>/``;
``fetch_binaries.py`` populates that directory and the PyInstaller spec ships it
as bundle data. yt-dlp is additionally mirrored into the user data directory,
because it updates itself in place and the bundle it ships in is read-only.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
from pathlib import Path

from .errors import MissingBinaryError

APP_DIR_NAME = "PlaylistDownloader"
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

_CREATE_NO_WINDOW = 0x08000000


def platform_tag() -> str:
    if sys.platform == "darwin":
        return "darwin-arm64" if platform.machine() == "arm64" else "darwin-x86_64"
    if sys.platform == "win32":
        return "win-amd64"
    return f"{sys.platform}-{platform.machine()}"


def _search_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parents[3])
    roots.append(Path.cwd())
    return roots


def bin_dir() -> Path | None:
    tag = platform_tag()
    for root in _search_roots():
        candidate = root / "bin" / tag
        if candidate.is_dir():
            return candidate
    return None


def _make_executable(path: Path) -> None:
    if sys.platform == "win32":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def find_binary(name: str, *, required: bool = True) -> Path | None:
    directory = bin_dir()
    if directory:
        candidate = directory / f"{name}{EXE_SUFFIX}"
        if candidate.exists():
            _make_executable(candidate)
            return candidate
    on_path = shutil.which(name)
    if on_path:
        return Path(on_path)
    if required:
        raise MissingBinaryError(name)
    return None


def app_data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    directory = base / APP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ytdlp_path() -> Path:
    """Return a writable yt-dlp so ``--update-to`` can replace it in place.

    A newer bundled copy (i.e. the app itself was updated) wins over the mirror,
    otherwise the mirror is kept because it may have self-updated since.
    """
    local = app_data_dir() / "bin" / f"yt-dlp{EXE_SUFFIX}"
    bundled = find_binary("yt-dlp", required=False)

    if bundled is not None and bundled != local:
        bundled_is_newer = (
            not local.exists() or bundled.stat().st_mtime > local.stat().st_mtime
        )
        if bundled_is_newer:
            local.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled, local)

    if not local.exists():
        if bundled is None:
            raise MissingBinaryError("yt-dlp")
        return bundled

    _make_executable(local)
    return local


def ffmpeg_location() -> Path | None:
    """Directory holding ffmpeg/ffprobe, in the form yt-dlp's flag expects."""
    directory = bin_dir()
    if directory and (directory / f"ffmpeg{EXE_SUFFIX}").exists():
        return directory
    on_path = shutil.which("ffmpeg")
    return Path(on_path).parent if on_path else None


def ffprobe_path() -> Path | None:
    return find_binary("ffprobe", required=False)


def popen_kwargs() -> dict:
    """Keep console windows from flashing on Windows for every subprocess."""
    if sys.platform == "win32":
        return {"creationflags": _CREATE_NO_WINDOW}
    return {}
