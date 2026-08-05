"""Post-download audio enhancement with ffmpeg.

Uses broadcast-standard loudness normalization (EBU R128 via loudnorm) plus optional
noise reduction and band limiting — the same building blocks used in podcast and
streaming pipelines.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import resources
from .errors import PlaylistDownloaderError
from .settings import Settings

PRESETS = ("off", "studio", "podcast", "music", "voice")


@dataclass(frozen=True)
class AudioPreset:
    id: str
    label: str
    description: str
    denoise: bool
    normalize: bool
    highpass_hz: int
    lowpass_hz: int


PRESET_CATALOG: tuple[AudioPreset, ...] = (
    AudioPreset("off", "Original", "No processing — exactly as downloaded", False, False, 0, 0),
    AudioPreset(
        "studio",
        "Studio clean",
        "Light denoise, rumble cut, EBU R128 loudness (-14 LUFS)",
        True,
        True,
        80,
        16000,
    ),
    AudioPreset(
        "podcast",
        "Podcast / speech",
        "Stronger denoise and compression for spoken word",
        True,
        True,
        100,
        12000,
    ),
    AudioPreset(
        "music",
        "Music",
        "Gentle loudness match — preserves dynamics",
        False,
        True,
        40,
        18000,
    ),
    AudioPreset(
        "voice",
        "Voice isolate",
        "High-pass + denoise for lectures and tutorials",
        True,
        True,
        120,
        14000,
    ),
)


def preset_by_id(preset_id: str) -> AudioPreset:
    for preset in PRESET_CATALOG:
        if preset.id == preset_id:
            return preset
    return PRESET_CATALOG[0]


def effective_preset(settings: Settings) -> AudioPreset:
    if not settings.audio_enhance or settings.audio_preset == "off":
        return PRESET_CATALOG[0]
    base = preset_by_id(settings.audio_preset)
    return AudioPreset(
        id=base.id,
        label=base.label,
        description=base.description,
        denoise=settings.audio_denoise if settings.audio_preset == "custom" else base.denoise,
        normalize=settings.audio_normalize if settings.audio_preset == "custom" else base.normalize,
        highpass_hz=settings.audio_highpass_hz or base.highpass_hz,
        lowpass_hz=settings.audio_lowpass_hz or base.lowpass_hz,
    )


def build_audio_filter(settings: Settings) -> str | None:
    preset = effective_preset(settings)
    if preset.id == "off":
        return None

    parts: list[str] = []
    if preset.highpass_hz > 0:
        parts.append(f"highpass=f={preset.highpass_hz}")
    if preset.lowpass_hz > 0:
        parts.append(f"lowpass=f={preset.lowpass_hz}")
    if preset.denoise:
        parts.append("afftdn=nr=12:nf=-25")
    if preset.normalize:
        parts.append("loudnorm=I=-14:TP=-1.5:LRA=11")

    return ",".join(parts) if parts else None


def _ffmpeg_base() -> list[str]:
    ffmpeg = resources.find_binary("ffmpeg")
    if ffmpeg is None:
        raise PlaylistDownloaderError("ffmpeg is required for audio enhancement.")
    return [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y"]


def enhance_file(source: Path, destination: Path, settings: Settings) -> None:
    """Write an enhanced copy to destination (video files: audio stream only path re-muxes)."""
    filt = build_audio_filter(settings)
    if not filt:
        if source != destination:
            destination.write_bytes(source.read_bytes())
        return

    argv = _ffmpeg_base() + ["-i", str(source), "-af", filt]
    if source.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
        argv += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        argv += ["-c:a", "libmp3lame", "-q:a", "2"]
    argv.append(str(destination))

    proc = subprocess.run(argv, capture_output=True, text=True, **resources.popen_kwargs())
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        raise PlaylistDownloaderError(tail[-1] if tail else "Audio enhancement failed.")


def enhance_in_place(path: Path, settings: Settings) -> None:
    filt = build_audio_filter(settings)
    if not filt or not path.exists():
        return
    with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False, dir=path.parent) as tmp:
        temp = Path(tmp.name)
    try:
        enhance_file(path, temp, settings)
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def preview_clip(source: Path, settings: Settings, *, start_sec: float = 30, duration_sec: float = 20) -> bytes:
    """Extract a short segment, apply filters, return AAC bytes for browser preview."""
    filt = build_audio_filter(settings)
    argv = _ffmpeg_base() + [
        "-ss",
        str(start_sec),
        "-t",
        str(duration_sec),
        "-i",
        str(source),
    ]
    if filt:
        argv += ["-af", filt]
    argv += ["-f", "mp4", "-c:a", "aac", "-b:a", "128k", "pipe:1"]

    proc = subprocess.run(argv, capture_output=True, **resources.popen_kwargs())
    if proc.returncode != 0 or not proc.stdout:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise PlaylistDownloaderError(err.splitlines()[-1] if err else "Preview failed.")
    return proc.stdout


def catalog_dict() -> list[dict]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "denoise": p.denoise,
            "normalize": p.normalize,
        }
        for p in PRESET_CATALOG
    ]
