"""Which qualities a playlist offers, and how much disk each one costs.

Probing 882 videos to answer "how big is 1080p?" would take minutes, so a small
sample is probed in parallel and its measured bitrate is applied to the total
playlist duration, which the flat extraction already gave us for free.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import ytdlp
from .playlist import Entry

DEFAULT_SAMPLE_SIZE = 12
DEFAULT_PROBE_WORKERS = 6


@dataclass(frozen=True)
class Quality:
    height: int
    label: str
    vcodec: str
    bytes_per_second: float
    estimated_total_bytes: int
    coverage: float

    def to_dict(self) -> dict:
        return {
            "height": self.height,
            "label": self.label,
            "vcodec": self.vcodec,
            "bytesPerSecond": self.bytes_per_second,
            "estimatedTotalBytes": self.estimated_total_bytes,
            "coverage": self.coverage,
        }


def probe_video(video_id: str) -> dict:
    return ytdlp.run_json(
        ["--dump-single-json", "--no-download", f"https://www.youtube.com/watch?v={video_id}"],
        timeout=120,
    )


def _format_bytes(fmt: dict, duration: float | None) -> int:
    for key in ("filesize", "filesize_approx"):
        value = fmt.get(key)
        if value:
            return int(value)
    tbr = fmt.get("tbr")
    if tbr and duration:
        return int(tbr * 1000 / 8 * duration)
    return 0


def _is_video(fmt: dict) -> bool:
    return fmt.get("vcodec") not in (None, "none") and bool(fmt.get("height"))


def _is_audio_only(fmt: dict) -> bool:
    return fmt.get("acodec") not in (None, "none") and fmt.get("vcodec") in (None, "none")


def _best_audio(formats: Sequence[dict], container: str) -> dict | None:
    candidates = [f for f in formats if _is_audio_only(f)]
    if not candidates:
        return None
    if container == "mp4":
        preferred = [f for f in candidates if str(f.get("acodec", "")).startswith("mp4a")]
        candidates = preferred or candidates
    if container == "webm":
        preferred = [f for f in candidates if str(f.get("acodec", "")).startswith("opus")]
        candidates = preferred or candidates
    return max(candidates, key=lambda f: f.get("abr") or f.get("tbr") or 0)


def _best_video_per_height(formats: Sequence[dict], container: str) -> dict[int, dict]:
    by_height: dict[int, list[dict]] = {}
    for fmt in formats:
        if _is_video(fmt):
            by_height.setdefault(int(fmt["height"]), []).append(fmt)

    chosen: dict[int, dict] = {}
    for height, candidates in by_height.items():
        if container == "mp4":
            preferred = [f for f in candidates if str(f.get("vcodec", "")).startswith("avc1")]
            candidates = preferred or candidates
        if container == "webm":
            preferred = [f for f in candidates if str(f.get("vcodec", "")).startswith("vp9")]
            candidates = preferred or candidates
        chosen[height] = max(candidates, key=lambda f: f.get("tbr") or 0)
    return chosen


def analyze(
    entries: Sequence[Entry],
    *,
    container: str = "mkv",
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    workers: int = DEFAULT_PROBE_WORKERS,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[Quality]:
    """Return the qualities on offer, each with an estimated total size."""
    sample = list(entries[: max(1, sample_size)])
    total_duration = sum(entry.duration or 0.0 for entry in entries)
    if not total_duration:
        total_duration = sum(entry.duration or 0.0 for entry in sample) * len(entries) / max(
            len(sample), 1
        )

    rates: dict[int, list[float]] = {}
    codecs: dict[int, str] = {}
    seen = 0
    probed = 0

    def probe(entry: Entry) -> dict | None:
        try:
            return probe_video(entry.video_id)
        except Exception:  # noqa: BLE001 - a private or removed video must not stop analysis
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for info in pool.map(probe, sample):
            seen += 1
            if on_progress:
                on_progress(seen, len(sample))
            if not info:
                continue
            duration = info.get("duration")
            if not duration:
                continue
            formats = info.get("formats") or []
            audio = _best_audio(formats, container)
            audio_bytes = _format_bytes(audio, duration) if audio else 0
            for height, fmt in _best_video_per_height(formats, container).items():
                video_bytes = _format_bytes(fmt, duration)
                if not video_bytes:
                    continue
                rates.setdefault(height, []).append((video_bytes + audio_bytes) / duration)
                codecs.setdefault(height, str(fmt.get("vcodec") or "").split(".")[0])
            probed += 1

    qualities: list[Quality] = []
    for height, samples in rates.items():
        average = sum(samples) / len(samples)
        qualities.append(
            Quality(
                height=height,
                label=f"{height}p",
                vcodec=codecs.get(height, ""),
                bytes_per_second=average,
                estimated_total_bytes=int(average * total_duration),
                coverage=len(samples) / probed if probed else 0.0,
            )
        )

    qualities.sort(key=lambda q: q.height, reverse=True)
    return qualities
