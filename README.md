# Playlist Downloader

A desktop app for macOS and Windows that downloads whole YouTube playlists — numbered
in order, subtitles embedded, many videos at once. Pause whenever you like and come
back later; it picks up exactly where it left off.

<p align="center"><i>macOS + Windows · one click · no install</i></p>

## ⬇️ Download

| Your computer | Download |
|---|---|
| 🪟 **Windows** | **[⬇ Download the app](https://github.com/Avichai997/playlist-downloader/releases/latest/download/PlaylistDownloader.exe)** |
| 🍎 **Mac (Apple Silicon: M1/M2/M3/M4)** | **[⬇ Download the app](https://github.com/Avichai997/playlist-downloader/releases/latest/download/PlaylistDownloader-macOS-arm64.dmg)** |

*(All downloads are on the **[Releases page](https://github.com/Avichai997/playlist-downloader/releases/latest)**.)*

### How to open it (first time only)

The app isn't code-signed yet, so the very first time your computer asks you to
confirm. **One time only:** *(to remove this warning for free, see [SIGNING.md](SIGNING.md))*

- **Windows:** double-click `PlaylistDownloader.exe`. If a blue box says *"Windows
  protected your PC"* → click **More info** → **Run anyway**.
- **Mac:** double-click the `.dmg`, drag **Playlist Downloader** onto the **Applications**
  folder, then open Applications and **right-click** the app → **Open** →
  **Open**. (After the first time, a normal double-click works.)

### Then

1. Paste a playlist link and click **Analyze**
2. Pick a quality — each option shows an estimated total size for the whole playlist
3. Optionally set **Start from #** / **End at #** (e.g. start at 822 after a month)
4. Click **Download**

Files land in `~/Downloads/<Playlist Title>/` as `001. Title.mkv`, `002. …`, so Finder
and Explorer sort them in playlist order.

## Features

- **Parallel downloads** — 4 videos × 16 fragments by default (saturates most home lines)
- **Pause / resume / skip** — per video or the whole queue; safe to quit mid-run
- **Sync later** — keyed by video ID, not playlist position, so re-sync only fetches what's new
- **Quality picker** — real sizes from a sample, extrapolated to the full playlist
- **Subtitles** — embedded in the file (English + Hebrew by default)
- **Reliability** — yt-dlp self-update, infinite retries, alternate clients, ffprobe verification
- **CLI** — `playlist-downloader <url>` or `pldl <url>` for headless use

## How it works

1. **Flat-extract** the playlist (one cheap request for all titles/durations)
2. **Probe** a sample of videos for available heights and byte sizes
3. **Queue** jobs in SQLite, numbered by stable library IDs (not fragile playlist indices)
4. **Download** with bundled `yt-dlp` + `ffmpeg` — concurrent fragments, retry ladder on failure
5. **Verify** with `ffprobe` (truncated files are re-queued automatically)

## Develop / run from source

```bash
python3.11 -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev,build]"
python fetch_binaries.py        # bundle yt-dlp + ffmpeg for this platform
cd frontend && npm ci && npm run build && cd ..
python -m playlist_downloader   # launch the GUI
pytest -q                       # run tests
```

## Build the portable app

`fetch_binaries.py` must have run on the target platform first (it bundles `yt-dlp`
and `ffmpeg`/`ffprobe` into `bin/<tag>/`). The frontend must be built first
(`cd frontend && npm run build`).

```bash
# Windows → dist\PlaylistDownloader.exe (double-click, portable)
pyinstaller --clean --noconfirm playlist-downloader.spec

# macOS → dist/PlaylistDownloader.app (+ .dmg via hdiutil in CI)
pyinstaller --clean --noconfirm playlist-downloader.spec
```

## Releases

Tags like `v0.1.0` trigger [GitHub Actions](.github/workflows/build.yml) to build
both platforms and publish a Release with:

- `PlaylistDownloader.exe` (Windows)
- `PlaylistDownloader-macOS-arm64.dmg` (Apple Silicon Mac)

Download links in this README point at `/releases/latest/download/…` and update
automatically on each new release.

The desktop app checks GitHub on launch and shows a **Download update** banner when
a newer tagged release is available (notify only — you install the `.dmg` or `.exe`
yourself, same as [dwfx2pdf](https://github.com/Avichai997/dwfx2pdf)).

## Bundled components

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — Unlicense
- [ffmpeg](https://ffmpeg.org/) — GPL (static builds via ffmpeg-static / yt-dlp FFmpeg-Builds)

This is a **personal archival tool**. You are responsible for respecting YouTube's
terms of service and the licensing of the content you download.

## License

MIT
