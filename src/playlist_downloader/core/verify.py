"""Confirm a finished file is actually complete.

A download cut short by a dropped connection can still exit cleanly and leave a
plausible-looking file behind. Comparing the container's real duration against
the duration the metadata promised is what catches that, and it is the
difference between "the queue said done" and the file actually being watchable.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import resources
from .errors import VerificationFailed

DEFAULT_TOLERANCE_SECONDS = 4.0
MIN_PLAUSIBLE_BYTES = 4096


def _probe(path: Path) -> dict:
    ffprobe = resources.ffprobe_path()
    if ffprobe is None:
        raise VerificationFailed("ffprobe is not available, so the file cannot be checked.")
    proc = subprocess.run(
        [
            str(ffprobe),
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        **resources.popen_kwargs(),
    )
    if proc.returncode != 0:
        raise VerificationFailed(
            f"The file could not be read back: {proc.stderr.strip().splitlines()[-1:] or 'unknown error'}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationFailed("ffprobe returned output that could not be read.") from exc


def verify(
    path: Path,
    *,
    expected_duration: float | None = None,
    expect_video: bool = True,
    tolerance: float = DEFAULT_TOLERANCE_SECONDS,
) -> float | None:
    """Raise VerificationFailed if the file is missing, empty, or short.

    Returns the measured duration in seconds.
    """
    if not path.exists():
        raise VerificationFailed("The finished file is not where yt-dlp said it would be.")
    size = path.stat().st_size
    if size < MIN_PLAUSIBLE_BYTES:
        raise VerificationFailed(f"The finished file is only {size} bytes.")

    info = _probe(path)
    streams = info.get("streams") or []
    kinds = {stream.get("codec_type") for stream in streams}
    if expect_video and "video" not in kinds:
        raise VerificationFailed("The file has no video stream.")
    if "audio" not in kinds:
        raise VerificationFailed("The file has no audio stream.")

    raw_duration = (info.get("format") or {}).get("duration")
    measured = float(raw_duration) if raw_duration else None

    if measured is not None and expected_duration:
        shortfall = expected_duration - measured
        if shortfall > max(tolerance, expected_duration * 0.02):
            raise VerificationFailed(
                f"The file is {shortfall:.0f}s shorter than expected "
                f"({measured:.0f}s of {expected_duration:.0f}s) — it looks truncated."
            )
    return measured
