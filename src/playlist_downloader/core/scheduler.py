"""The download engine: a pool of workers pulling jobs out of SQLite.

Every worker owns one yt-dlp subprocess at a time. Pausing terminates that
subprocess and leaves the partial fragments on disk; resuming re-runs the same
command with --continue, so nothing already fetched is fetched twice. That works
identically on Windows, which has no way to suspend a process.

A failing video walks up a ladder of strategies rather than being given up on,
and a file that finishes is only called done once ffprobe agrees it is complete.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from . import db as db_module
from . import audio, naming, verify, ytdlp
from .db import Database
from .errors import VerificationFailed
from .events import EventBus
from .settings import MAX_PARALLEL_VIDEOS, Settings

IDLE_SLEEP = 0.4
RATE_LIMIT_WINDOW = 120.0
RATE_LIMIT_THRESHOLD = 3
BACKOFF_RECOVERY = 600.0


def _parse_window(raw: str) -> tuple[int, int] | None:
    """Parse "01:00-08:00" into minutes-since-midnight bounds."""
    try:
        start_text, end_text = raw.split("-")
        start_hour, start_minute = (int(part) for part in start_text.strip().split(":"))
        end_hour, end_minute = (int(part) for part in end_text.strip().split(":"))
    except (ValueError, AttributeError):
        return None
    return start_hour * 60 + start_minute, end_hour * 60 + end_minute


class Scheduler:
    def __init__(self, database: Database, settings: Settings, events: EventBus) -> None:
        self._db = database
        self._settings = settings
        self._events = events

        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._paused = threading.Event()

        self._processes: dict[int, ytdlp.DownloadProcess] = {}
        self._pause_requests: set[int] = set()
        self._skip_requests: set[int] = set()
        self._control_lock = threading.Lock()

        self._rate_limit_hits: deque[float] = deque(maxlen=16)
        self._throttled_until = 0.0
        self._throttle_floor = MAX_PARALLEL_VIDEOS

    # ---------- lifecycle ----------

    def start(self) -> None:
        self._db.recover_running()
        for index in range(MAX_PARALLEL_VIDEOS):
            thread = threading.Thread(
                target=self._worker_loop, args=(index,), name=f"downloader-{index}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def shutdown(self) -> None:
        self._stop.set()
        with self._control_lock:
            processes = list(self._processes.values())
        for process in processes:
            process.stop()
        for thread in self._threads:
            thread.join(timeout=5)

    def update_settings(self, settings: Settings) -> None:
        self._settings = settings

    # ---------- controls ----------

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def pause_all(self) -> None:
        self._paused.set()
        with self._control_lock:
            running = list(self._processes.items())
            self._pause_requests.update(job_id for job_id, _ in running)
        for _, process in running:
            process.stop()
        self._publish_stats()

    def resume_all(self) -> None:
        self._paused.clear()
        self._db.bulk_set_state([db_module.PAUSED], db_module.QUEUED)
        self._publish_stats()

    def pause_job(self, job_id: int) -> None:
        with self._control_lock:
            process = self._processes.get(job_id)
            if process:
                self._pause_requests.add(job_id)
        if process:
            process.stop()
        else:
            self._db.set_state(job_id, db_module.PAUSED)
            self._publish_job(job_id)

    def resume_job(self, job_id: int) -> None:
        self._db.set_state(job_id, db_module.QUEUED, error=None)
        self._publish_job(job_id)

    def skip_job(self, job_id: int) -> None:
        with self._control_lock:
            process = self._processes.get(job_id)
            if process:
                self._skip_requests.add(job_id)
        if process:
            process.stop()
        else:
            self._db.set_state(job_id, db_module.SKIPPED)
            self._publish_job(job_id)

    def retry_job(self, job_id: int) -> None:
        self._db.set_state(job_id, db_module.QUEUED, strategy=0, error=None)
        self._publish_job(job_id)

    def retry_failed(self, playlist_id: str | None = None) -> int:
        count = self._db.bulk_set_state(
            [db_module.FAILED, db_module.SKIPPED], db_module.QUEUED, playlist_id
        )
        self._publish_stats()
        return count

    def prioritise(self, job_id: int, priority: int = 100) -> None:
        self._db.update_job(job_id, priority=priority)
        self._publish_job(job_id)

    # ---------- worker ----------

    def _effective_concurrency(self) -> int:
        limit = max(1, min(MAX_PARALLEL_VIDEOS, self._settings.parallel_videos))
        if time.monotonic() < self._throttled_until:
            return max(1, min(limit, self._throttle_floor))
        return limit

    def _within_night_window(self) -> bool:
        window = _parse_window(self._settings.night_window)
        if not window:
            return True
        start, end = window
        now = datetime.now()
        minutes = now.hour * 60 + now.minute
        if start == end:
            return True
        if start < end:
            return start <= minutes < end
        return minutes >= start or minutes < end

    def _worker_loop(self, index: int) -> None:
        while not self._stop.is_set():
            if (
                self._paused.is_set()
                or index >= self._effective_concurrency()
                or not self._within_night_window()
            ):
                self._stop.wait(IDLE_SLEEP * 3)
                continue

            job = self._db.claim_next()
            if job is None:
                self._stop.wait(IDLE_SLEEP)
                continue

            self._publish_stats()
            try:
                self._run_job(job)
            except Exception as exc:  # noqa: BLE001 - a worker must never die
                self._db.set_state(job["id"], db_module.FAILED, error=str(exc))
                self._events.publish("job_failed", jobId=job["id"], error=str(exc))
            self._publish_stats()

    def _output_dir(self, job: dict) -> Path:
        directory = Path(job["output_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _template(self, job: dict) -> str:
        width = naming.pad_width(job["total_count"] or 1, self._settings.pad_width or None)
        return naming.output_template(job["number"], width, self._settings.numbering)

    def _find_existing(self, output_dir: Path, job: dict) -> Path | None:
        """yt-dlp skips a file it already has, and then prints no final path."""
        width = naming.pad_width(job["total_count"] or 1, self._settings.pad_width or None)
        prefix = naming.number_prefix(job["number"], width, self._settings.numbering)
        if not prefix:
            return None
        matches = sorted(
            candidate
            for candidate in output_dir.glob(f"{prefix}*")
            if candidate.is_file() and not candidate.name.endswith(".part")
        )
        return matches[0] if matches else None

    def _run_job(self, job: dict) -> None:
        job_id = job["id"]
        output_dir = self._output_dir(job)
        template = self._template(job)
        video_url = f"https://www.youtube.com/watch?v={job['video_id']}"
        base_height = job["max_height"] or self._settings.max_height

        self._events.publish(
            "job_started",
            jobId=job_id,
            number=job["number"],
            title=job["title"],
            videoId=job["video_id"],
        )

        ladder = ytdlp.RETRY_LADDER
        for index in range(int(job["strategy"] or 0), len(ladder)):
            strategy = ladder[index]
            if strategy.needs_cookies and not self._settings.cookies_browser:
                continue

            self._db.update_job(job_id, strategy=index)
            height = ytdlp.lower_height(base_height, strategy.height_steps_down)
            argv = ytdlp.build_download_argv(
                video_url=video_url,
                output_dir=output_dir,
                template=template,
                settings=self._settings,
                max_height=height,
                strategy=strategy,
            )

            process = ytdlp.DownloadProcess(argv)
            with self._control_lock:
                if job_id in self._skip_requests or job_id in self._pause_requests:
                    self._clear_requests(job_id)
                    self._db.set_state(job_id, db_module.PAUSED)
                    return
                self._processes[job_id] = process

            def on_progress(progress: ytdlp.Progress, _job_id: int = job_id) -> None:
                self._events.publish(
                    "job_progress",
                    jobId=_job_id,
                    status=progress.status,
                    percent=progress.percent,
                    downloadedBytes=progress.downloaded_bytes,
                    totalBytes=progress.total_bytes,
                    speed=progress.speed,
                    eta=progress.eta,
                )

            result = process.run(on_progress)

            with self._control_lock:
                self._processes.pop(job_id, None)
                paused = job_id in self._pause_requests
                skipped = job_id in self._skip_requests
                self._clear_requests(job_id)

            if skipped:
                self._db.set_state(job_id, db_module.SKIPPED, error="Skipped.")
                self._publish_job(job_id)
                return
            if paused or (self._paused.is_set() and not result.ok):
                self._db.set_state(job_id, db_module.PAUSED, error=None)
                self._publish_job(job_id)
                return

            if result.rate_limited:
                self._note_rate_limit()

            if result.ok:
                path = result.filepath or self._find_existing(output_dir, job)
                problem = self._accept(job_id, job, path)
                if problem is None:
                    return
                self._db.record_attempt(job_id, strategy.name, False, problem, result.log)
            else:
                self._db.record_attempt(job_id, strategy.name, False, result.error, result.log)

        last = self._db.attempts_for(job_id)
        reason = last[-1]["error"] if last else "Every strategy failed."
        self._db.set_state(job_id, db_module.FAILED, error=reason)
        self._events.publish("job_failed", jobId=job_id, error=reason)
        self._publish_job(job_id)

    def _accept(self, job_id: int, job: dict, path: Path | None) -> str | None:
        """Finish a job. Returns a problem description, or None on success."""
        if path is None or not path.exists():
            return "yt-dlp reported success but no output file was found."

        if self._settings.verify_downloads:
            try:
                verify.verify(
                    path,
                    expected_duration=job["duration"],
                    expect_video=not self._settings.audio_only,
                )
            except VerificationFailed as exc:
                path.unlink(missing_ok=True)
                return str(exc)

        if self._settings.audio_enhance and audio.build_audio_filter(self._settings):
            try:
                audio.enhance_in_place(path, self._settings)
            except Exception as exc:  # noqa: BLE001
                return f"Audio enhancement failed: {exc}"

        size = path.stat().st_size
        self._db.set_state(
            job_id,
            db_module.DONE,
            filepath=str(path),
            filesize=size,
            verified=int(self._settings.verify_downloads),
            error=None,
        )
        self._db.record_attempt(job_id, "completed", True)
        self._events.publish(
            "job_done", jobId=job_id, filepath=str(path), filesize=size, title=job["title"]
        )
        return None

    def _clear_requests(self, job_id: int) -> None:
        self._pause_requests.discard(job_id)
        self._skip_requests.discard(job_id)

    def _note_rate_limit(self) -> None:
        now = time.monotonic()
        self._rate_limit_hits.append(now)
        recent = [hit for hit in self._rate_limit_hits if now - hit < RATE_LIMIT_WINDOW]
        if len(recent) < RATE_LIMIT_THRESHOLD:
            return
        current = self._effective_concurrency()
        self._throttle_floor = max(1, current - 1)
        self._throttled_until = now + BACKOFF_RECOVERY
        self._events.publish(
            "throttled",
            concurrency=self._throttle_floor,
            message=(
                "YouTube is rate limiting, so downloads were slowed to "
                f"{self._throttle_floor} at a time. This lifts automatically."
            ),
        )

    # ---------- notifications ----------

    def _publish_job(self, job_id: int) -> None:
        job = self._db.get_job(job_id)
        if job:
            self._events.publish("job_state", job=job)

    def _publish_stats(self) -> None:
        self._events.publish(
            "stats",
            stats=self._db.stats(),
            paused=self.paused,
            concurrency=self._effective_concurrency(),
        )
