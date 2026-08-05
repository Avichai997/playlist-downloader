"""Reading a playlist's contents.

A flat extraction is one cheap request for the whole playlist — it returns every
video's id, title and duration without touching the videos themselves, which is
what makes an 882-entry sync fast.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ytdlp
from .errors import ExtractionError


@dataclass(frozen=True)
class Entry:
    video_id: str
    title: str
    duration: float | None
    position: int

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass(frozen=True)
class Snapshot:
    playlist_id: str
    url: str
    title: str
    uploader: str
    entries: tuple[Entry, ...]

    @property
    def total_duration(self) -> float:
        return sum(entry.duration or 0.0 for entry in self.entries)

    @property
    def known_durations(self) -> int:
        return sum(1 for entry in self.entries if entry.duration)


def _is_playlist_url(url: str) -> bool:
    return "list=" in url or "/playlist" in url


def fetch(url: str) -> Snapshot:
    args = ["--flat-playlist", "--dump-single-json"]
    if _is_playlist_url(url):
        args.append("--yes-playlist")
    args.append(url)

    info = ytdlp.run_json(args)

    if info.get("_type") not in ("playlist", "multi_video"):
        entry = Entry(
            video_id=info.get("id", ""),
            title=info.get("title") or "Untitled",
            duration=info.get("duration"),
            position=1,
        )
        if not entry.video_id:
            raise ExtractionError("That link does not point to a video or a playlist.")
        return Snapshot(
            playlist_id=entry.video_id,
            url=url,
            title=entry.title,
            uploader=info.get("uploader") or info.get("channel") or "",
            entries=(entry,),
        )

    entries: list[Entry] = []
    for position, raw in enumerate(info.get("entries") or [], start=1):
        if not raw:
            continue
        video_id = raw.get("id")
        if not video_id:
            continue
        entries.append(
            Entry(
                video_id=video_id,
                title=raw.get("title") or "Untitled",
                duration=raw.get("duration"),
                position=position,
            )
        )

    if not entries:
        raise ExtractionError(
            "The playlist came back empty. It may be private, deleted, or region locked."
        )

    return Snapshot(
        playlist_id=info.get("id") or url,
        url=url,
        title=info.get("title") or "Playlist",
        uploader=info.get("uploader") or info.get("channel") or "",
        entries=tuple(entries),
    )
