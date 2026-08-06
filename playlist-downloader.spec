# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Windows portable .exe, macOS .app.

Bundles bin/<tag>/ (yt-dlp + ffmpeg/ffprobe) and the built React UI in
src/playlist_downloader/web/, resolved at runtime via sys._MEIPASS (see
core/resources.py and server/app.py).
"""
import platform
import sys
from pathlib import Path

VERSION = "0.1.4"


def _tag():
    if sys.platform == "darwin":
        return "darwin-arm64" if platform.machine() == "arm64" else "darwin-x86_64"
    if sys.platform == "win32":
        return "win-amd64"
    return sys.platform


TAG = _tag()
ROOT = Path(SPECPATH)

web_dir = ROOT / "src" / "playlist_downloader" / "web"
if not web_dir.is_dir():
    raise SystemExit(
        "Frontend not built. Run: cd frontend && npm ci && npm run build"
    )

datas = [
    (str(ROOT / "bin" / TAG), f"bin/{TAG}"),
    (str(web_dir), "playlist_downloader/web"),
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "webview",
]

a = Analysis(
    ["app_entry.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "numpy", "tkinter", "test", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "win32":
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="PlaylistDownloader",
        console=False,
        onefile=True,
        upx=False,
        icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None,
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="PlaylistDownloader",
        console=False,
        upx=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="PlaylistDownloader", upx=False)
    app = BUNDLE(
        coll,
        name="PlaylistDownloader.app",
        bundle_identifier="com.playlistdownloader.app",
        icon=str(ROOT / "assets" / "icon.icns") if (ROOT / "assets" / "icon.icns").exists() else None,
        info_plist={
            "CFBundleName": "Playlist Downloader",
            "CFBundleDisplayName": "Playlist Downloader",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
