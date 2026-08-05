"""Building and running yt-dlp commands.

yt-dlp runs as a subprocess rather than as a library: a crash cannot take the
app down with it, killing a download for pause is clean, downloads run in true
parallel without the GIL, and the binary can update itself.

Machine-readable output is requested explicitly (``--progress-template`` and
``--print``) with sentinel prefixes, as the yt-dlp docs recommend, so normal
stdout is never parsed.
"""
from __future__ import annotations

import collections
import json
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from . import resources
from .errors import ExtractionError
from .settings import Settings

PROGRESS_SENTINEL = "PDLPROG"
FILEPATH_SENTINEL = "PDLFILE"

_PROGRESS_FIELDS = (
    "status",
    "downloaded_bytes",
    "total_bytes",
    "total_bytes_estimate",
    "speed",
    "eta",
    "fragment_index",
    "fragment_count",
)
_PROGRESS_TEMPLATE = (
    "download:"
    + PROGRESS_SENTINEL
    + " "
    + "|".join(f"%(progress.{name})s" for name in _PROGRESS_FIELDS)
)
_FILEPATH_TEMPLATE = f"after_move:{FILEPATH_SENTINEL} %(filepath)s"

HEIGHT_LADDER = (4320, 2160, 1440, 1080, 720, 480, 360, 240, 144)

_RATE_LIMIT_MARKERS = ("http error 429", "too many requests", "rate limit")
_BOT_CHECK_MARKERS = ("confirm you", "not a bot", "sign in to confirm")


@dataclass(frozen=True)
class Strategy:
    """One rung of the retry ladder."""

    name: str
    args: tuple[str, ...] = ()
    height_steps_down: int = 0
    needs_cookies: bool = False


RETRY_LADDER: tuple[Strategy, ...] = (
    Strategy("default"),
    Strategy(
        "android client",
        ("--extractor-args", "youtube:player_client=android,web_safari"),
    ),
    Strategy(
        "ios client",
        ("--extractor-args", "youtube:player_client=ios,mweb"),
    ),
    Strategy("browser cookies", needs_cookies=True),
    Strategy("one quality lower", height_steps_down=1),
    Strategy("two qualities lower", height_steps_down=2),
)


@dataclass(frozen=True)
class Progress:
    status: str
    downloaded_bytes: float | None
    total_bytes: float | None
    speed: float | None
    eta: float | None
    fragment_index: float | None
    fragment_count: float | None

    @property
    def percent(self) -> float | None:
        if not self.total_bytes or self.downloaded_bytes is None:
            return None
        return min(100.0, self.downloaded_bytes / self.total_bytes * 100.0)


@dataclass(frozen=True)
class DownloadResult:
    returncode: int
    filepath: Path | None
    error: str
    log: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def rate_limited(self) -> bool:
        haystack = f"{self.error}\n{self.log}".lower()
        return any(marker in haystack for marker in _RATE_LIMIT_MARKERS)

    @property
    def bot_checked(self) -> bool:
        haystack = f"{self.error}\n{self.log}".lower()
        return any(marker in haystack for marker in _BOT_CHECK_MARKERS)


def base_argv() -> list[str]:
    argv = [str(resources.ytdlp_path()), "--ignore-config", "--no-colors"]
    ffmpeg = resources.ffmpeg_location()
    if ffmpeg:
        argv += ["--ffmpeg-location", str(ffmpeg)]
    return argv


def _last_error_line(stderr: str) -> str:
    errors = [line.strip() for line in stderr.splitlines() if line.strip().startswith("ERROR:")]
    if errors:
        return errors[-1].removeprefix("ERROR:").strip()
    tail = [line.strip() for line in stderr.splitlines() if line.strip()]
    return tail[-1] if tail else ""


def run_json(args: Sequence[str], *, timeout: float = 600) -> dict:
    argv = base_argv() + ["--no-warnings", *args]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **resources.popen_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError("yt-dlp timed out while reading metadata.") from exc

    if proc.returncode != 0:
        raise ExtractionError(_last_error_line(proc.stderr) or f"yt-dlp exited {proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ExtractionError("yt-dlp returned output that could not be read.") from exc


def version() -> str:
    proc = subprocess.run(
        [str(resources.ytdlp_path()), "--version"],
        capture_output=True,
        text=True,
        **resources.popen_kwargs(),
    )
    return proc.stdout.strip()


def self_update(channel: str = "stable") -> str:
    """Update the writable yt-dlp copy. A stale binary is the top failure cause."""
    proc = subprocess.run(
        [str(resources.ytdlp_path()), "--update-to", channel],
        capture_output=True,
        text=True,
        timeout=180,
        **resources.popen_kwargs(),
    )
    return (proc.stdout or proc.stderr).strip()


def lower_height(height: int, steps: int) -> int:
    if steps <= 0:
        return height
    ladder = [h for h in HEIGHT_LADDER if h <= height]
    if not ladder:
        return height
    return ladder[min(steps, len(ladder) - 1)]


def format_selector(*, max_height: int, container: str, audio_only: bool) -> str:
    if audio_only:
        return "bestaudio/best"
    if container == "mp4":
        return (
            f"bv*[height<={max_height}][vcodec^=avc1]+ba[acodec^=mp4a]/"
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"
        )
    if container == "webm":
        return (
            f"bv*[height<={max_height}][vcodec^=vp9]+ba[acodec^=opus]/"
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv*+ba/b"
        )
    return f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv*+ba/b"


def build_download_argv(
    *,
    video_url: str,
    output_dir: Path,
    template: str,
    settings: Settings,
    max_height: int,
    strategy: Strategy = RETRY_LADDER[0],
) -> list[str]:
    argv = base_argv()
    argv += [
        "--no-playlist",
        "--newline",
        "--progress",
        "--progress-delta",
        "0.5",
        "--progress-template",
        _PROGRESS_TEMPLATE,
        "--print",
        _FILEPATH_TEMPLATE,
        "--paths",
        f"home:{output_dir}",
        "--paths",
        f"temp:{output_dir / '.incomplete'}",
        "--output",
        template,
        "--trim-filenames",
        "180",
        "--continue",
        "--no-overwrites",
        "--concurrent-fragments",
        str(settings.fragments_per_video),
        "--retries",
        "infinite",
        "--fragment-retries",
        "infinite",
        "--extractor-retries",
        "5",
        "--retry-sleep",
        "exp=1:120",
        "--throttled-rate",
        "100K",
    ]

    if settings.windows_safe_filenames:
        argv.append("--windows-filenames")

    if settings.audio_only:
        argv += [
            "--format",
            format_selector(max_height=max_height, container="", audio_only=True),
            "--extract-audio",
            "--audio-format",
            settings.audio_format,
            "--audio-quality",
            "0",
        ]
    else:
        argv += [
            "--format",
            format_selector(
                max_height=max_height, container=settings.container, audio_only=False
            ),
            "--merge-output-format",
            settings.container,
        ]

    if settings.subtitles and settings.sub_langs:
        argv += ["--sub-langs", ",".join(f"{lang}.*" for lang in settings.sub_langs)]
        if settings.auto_subs:
            argv.append("--write-auto-subs")
        argv += ["--embed-subs", "--convert-subs", "srt"]
        if settings.keep_sub_files:
            argv.append("--write-subs")

    if settings.embed_thumbnail:
        argv.append("--embed-thumbnail")
    if settings.embed_metadata:
        argv.append("--embed-metadata")
    if settings.embed_chapters:
        argv.append("--embed-chapters")

    if settings.sponsorblock == "remove":
        argv += ["--sponsorblock-remove", "sponsor"]
    elif settings.sponsorblock == "mark":
        argv += ["--sponsorblock-mark", "all"]

    if settings.rate_limit:
        argv += ["--limit-rate", settings.rate_limit]

    use_cookies = settings.cookies_browser and (
        strategy.needs_cookies or strategy is RETRY_LADDER[0]
    )
    if use_cookies:
        argv += ["--cookies-from-browser", settings.cookies_browser]

    argv += list(strategy.args)
    argv.append(video_url)
    return argv


def _to_number(raw: str) -> float | None:
    if raw in ("NA", "None", "", "null"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_progress(payload: str) -> Progress | None:
    parts = payload.split("|")
    if len(parts) != len(_PROGRESS_FIELDS):
        return None
    values = dict(zip(_PROGRESS_FIELDS, parts))
    total = _to_number(values["total_bytes"]) or _to_number(values["total_bytes_estimate"])
    return Progress(
        status=values["status"],
        downloaded_bytes=_to_number(values["downloaded_bytes"]),
        total_bytes=total,
        speed=_to_number(values["speed"]),
        eta=_to_number(values["eta"]),
        fragment_index=_to_number(values["fragment_index"]),
        fragment_count=_to_number(values["fragment_count"]),
    )


class DownloadProcess:
    """A single running yt-dlp, streaming progress and stoppable at any time."""

    def __init__(self, argv: Sequence[str]) -> None:
        self._argv = list(argv)
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._stopped = False

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    @property
    def stopped(self) -> bool:
        with self._lock:
            return self._stopped

    def run(self, on_progress: Callable[[Progress], None] | None = None) -> DownloadResult:
        with self._lock:
            if self._stopped:
                return DownloadResult(1, None, "Cancelled before starting.", "")
            self._proc = subprocess.Popen(
                self._argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **resources.popen_kwargs(),
            )
            proc = self._proc

        stderr_tail: collections.deque[str] = collections.deque(maxlen=200)

        def drain_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_tail.append(line.rstrip())

        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stderr_thread.start()

        filepath: Path | None = None
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            if line.startswith(PROGRESS_SENTINEL):
                progress = _parse_progress(line[len(PROGRESS_SENTINEL) :].strip())
                if progress and on_progress:
                    on_progress(progress)
            elif line.startswith(FILEPATH_SENTINEL):
                candidate = line[len(FILEPATH_SENTINEL) :].strip()
                if candidate:
                    filepath = Path(candidate)
            elif line:
                stderr_tail.append(line)

        returncode = proc.wait()
        stderr_thread.join(timeout=5)
        log = "\n".join(stderr_tail)

        if self.stopped:
            return DownloadResult(returncode or 1, filepath, "Paused.", log)
        error = "" if returncode == 0 else (_last_error_line(log) or f"yt-dlp exited {returncode}")
        return DownloadResult(returncode, filepath, error, log)
