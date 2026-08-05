"""Command line entry point.

Given a link it downloads headlessly and reports progress on stdout; given
nothing it opens the desktop window.
"""
from __future__ import annotations

import argparse
import sys
import time

from . import APP_NAME, __version__
from .core import db as db_module
from .core.errors import PlaylistDownloaderError
from .core.service import Service

POLL_SECONDS = 2.0


def _human_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playlist-downloader",
        description=f"{APP_NAME} — download a YouTube playlist, numbered and subtitled.",
    )
    parser.add_argument("url", nargs="?", help="playlist or video link; omit to open the window")
    parser.add_argument("--quality", type=int, help="maximum height, e.g. 1080")
    parser.add_argument("--start", type=int, help="first video number to download")
    parser.add_argument("--end", type=int, help="last video number to download")
    parser.add_argument("--output", help="folder to download into")
    parser.add_argument("--workers", type=int, help="videos to download at once")
    parser.add_argument("--audio", action="store_true", help="extract audio only")
    parser.add_argument("--redownload", action="store_true", help="include finished videos")
    parser.add_argument("--no-verify", action="store_true", help="skip the integrity check")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def _download(args: argparse.Namespace) -> int:
    service = Service()

    changes: dict = {}
    if args.output:
        changes["output_root"] = args.output
    if args.quality:
        changes["max_height"] = args.quality
    if args.workers:
        changes["parallel_videos"] = args.workers
    if args.audio:
        changes["audio_only"] = True
    if args.no_verify:
        changes["verify_downloads"] = False
    if changes:
        service.update_settings(changes)

    service.start()
    try:
        print(f"Reading {args.url}")
        analysis = service.analyze(args.url)
        playlist = analysis["playlist"]
        print(f"{playlist['title']} — {playlist['count']} videos")

        height = args.quality or service.settings.max_height
        for quality in analysis["qualities"]:
            marker = "->" if quality["height"] == height else "  "
            print(
                f" {marker} {quality['label']:>6}  "
                f"~{_human_bytes(quality['estimatedTotalBytes'])} for the playlist"
            )

        queued = service.enqueue_range(
            playlist["id"],
            height=height,
            start_from=args.start,
            end_at=args.end,
            redownload=args.redownload,
        )
        print(f"Queued {queued['queued']} of {queued['selected']} selected videos.\n")

        return _follow(service, playlist["id"])
    finally:
        service.shutdown()


def _follow(service: Service, playlist_id: str) -> int:
    while True:
        stats = service.db.stats(playlist_id)
        active = stats[db_module.QUEUED] + stats[db_module.RUNNING]
        done = stats[db_module.DONE]
        failed = stats[db_module.FAILED]
        total = stats["total"]
        print(
            f"\r{done}/{total} done · {stats[db_module.RUNNING]} downloading · "
            f"{failed} failed · {_human_bytes(service.db.downloaded_bytes(playlist_id))}",
            end="",
            flush=True,
        )
        if active == 0:
            break
        time.sleep(POLL_SECONDS)

    print()
    if failed:
        print(f"{failed} videos failed. Re-run to retry them.")
        return 1
    print("Done.")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    if not args.url:
        from .desktop.shell import main as open_window

        return open_window()
    try:
        return _download(args)
    except PlaylistDownloaderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped. Progress is saved — run the same command to carry on.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
