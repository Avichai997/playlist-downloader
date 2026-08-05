"""PyInstaller entry point.

No arguments -> open the desktop window.
A link       -> download it headlessly and exit (terminal / scripting).
"""
from playlist_downloader.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
