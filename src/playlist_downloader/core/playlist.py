"""Reading a playlist's contents.

A flat extraction is one cheap request for the whole playlist — it returns every
video's id, title and duration without touching the videos themselves, which is
what makes an 882-entry sync fast.

YouTube sometimes returns only the first page in a single JSON dump; when
``playlist_count`` exceeds what came back, additional pages are fetched in batches.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ytdlp
from .errors import ExtractionError

_BATCH_SIZE = 100


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


def _entry_from_raw(raw: dict, *, fallback_position: int) -> Entry | None:
    if not raw:
        return None
    video_id = raw.get("id")
    if not video_id:
        return None
    position = raw.get("playlist_index") or raw.get("playlist_automatic_number") or fallback_position
    return Entry(
        video_id=video_id,
        title=raw.get("title") or "Untitled",
        duration=raw.get("duration"),
        position=int(position),
    )


def _entries_from_info(info: dict) -> list[Entry]:
    if info.get("_type") not in ("playlist", "multi_video"):
        entry = _entry_from_raw(info, fallback_position=1)
        return [entry] if entry else []

    entries: list[Entry] = []
    for position, raw in enumerate(info.get("entries") or [], start=1):
        entry = _entry_from_raw(raw, fallback_position=position)
        if entry:
            entries.append(entry)
    return entries


def _dedupe(entries: list[Entry]) -> tuple[Entry, ...]:
    seen: set[str] = set()
    unique: list[Entry] = []
    for entry in entries:
        if entry.video_id in seen:
            continue
        seen.add(entry.video_id)
        unique.append(entry)
    return tuple(unique)


def _fetch_flat_json(url: str, *, playlist_items: str | None = None) -> dict:
    args = ["--flat-playlist", "--ignore-errors", "--dump-single-json"]
    if _is_playlist_url(url):
        args.append("--yes-playlist")
    if playlist_items:
        args.extend(["--playlist-items", playlist_items])
    args.append(url)
    return ytdlp.run_json(args, timeout=900 if playlist_items is None else 300)


def _fetch_all_entries(url: str, info: dict) -> tuple[Entry, ...]:
    entries = _entries_from_info(info)
    expected = info.get("playlist_count") or len(entries)
    if not _is_playlist_url(url) or expected <= len(entries):
        return _dedupe(entries)

    start = len(entries) + 1
    while start <= expected:
        end = min(start + _BATCH_SIZE - 1, expected)
        batch = _fetch_flat_json(url, playlist_items=f"{start}:{end}")
        batch_entries = _entries_from_info(batch)
        if not batch_entries:
            break
        entries.extend(batch_entries)
        if len(batch_entries) < end - start + 1:
            break
        start = end + 1

    return _dedupe(entries)


def fetch(url: str) -> Snapshot:
    info = _fetch_flat_json(url)

    if info.get("_type") not in ("playlist", "multi_video"):
        entries = _entries_from_info(info)
        if not entries:
            raise ExtractionError("That link does not point to a video or a playlist.")
        entry = entries[0]
        return Snapshot(
            playlist_id=entry.video_id,
            url=url,
            title=entry.title,
            uploader=info.get("uploader") or info.get("channel") or "",
            entries=(entry,),
        )

    entries = _fetch_all_entries(url, info)
    if not entries:
        raise ExtractionError(
            "The playlist came back empty. It may be private, deleted, or region locked."
        )

    return Snapshot(
        playlist_id=info.get("id") or url,
        url=url,
        title=info.get("title") or "Playlist",
        uploader=info.get("uploader") or info.get("channel") or "",
        entries=entries,
    )
