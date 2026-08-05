"""Application-level operations, shared by the HTTP API and the headless CLI."""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from . import db as db_module
from . import formats, naming, playlist as playlist_module
from . import resources, settings as settings_module
from . import update as app_update
from . import ytdlp
from .audio import catalog_dict, preview_clip
from .db import Database
from .errors import PlaylistDownloaderError
from .events import EventBus
from .library import Library
from .scheduler import Scheduler
from .settings import Settings

WATCH_TICK_SECONDS = 300


class Service:
    def __init__(self, database: Database | None = None) -> None:
        self.settings: Settings = settings_module.load()
        self.db = database or Database()
        self.library = Library(self.db)
        self.events = EventBus()
        self.scheduler = Scheduler(self.db, self.settings, self.events)
        self._watch_thread: threading.Thread | None = None
        self._stop_watching = threading.Event()

    # ---------- lifecycle ----------

    def start(self) -> None:
        self.scheduler.start()
        if self.settings.update_ytdlp_on_launch:
            threading.Thread(target=self._update_ytdlp, daemon=True).start()
        threading.Thread(target=self._check_app_update, daemon=True).start()
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()

    def shutdown(self) -> None:
        self._stop_watching.set()
        self.scheduler.shutdown()

    def _update_ytdlp(self) -> None:
        try:
            message = ytdlp.self_update()
        except Exception as exc:  # noqa: BLE001 - never block startup on the updater
            self.events.publish("ytdlp_update", ok=False, message=str(exc))
            return
        self.events.publish("ytdlp_update", ok=True, message=message, version=ytdlp.version())

    def _check_app_update(self) -> None:
        info = app_update.check_for_update()
        if info:
            self.events.publish("app_update", version=info.version, url=info.url)

    def check_app_update(self) -> dict | None:
        info = app_update.check_for_update()
        if info is None:
            return None
        return {"version": info.version, "url": info.url}

    # ---------- playlists ----------

    def analyze(
        self,
        url: str,
        *,
        sample_size: int = formats.DEFAULT_SAMPLE_SIZE,
        container: str | None = None,
        output_dir: str | None = None,
    ) -> dict:
        self.events.publish("analyze_stage", stage="reading playlist")
        snapshot = playlist_module.fetch(url)

        active_container = container or self.settings.container
        if container and container != self.settings.container:
            self.update_settings({"container": container})

        if output_dir:
            target = Path(output_dir)
        else:
            target = Path(self.settings.output_root) / naming.sanitize(snapshot.title)

        self.db.upsert_playlist(
            snapshot, output_dir=str(target), max_height=self.settings.max_height
        )
        fresh = self.db.sync_videos(snapshot.playlist_id, snapshot.entries)

        self.events.publish("analyze_stage", stage="checking available qualities")

        def report(done: int, total: int) -> None:
            self.events.publish("analyze_progress", done=done, total=total)

        qualities = formats.analyze(
            snapshot.entries,
            container=active_container,
            sample_size=sample_size,
            on_progress=report,
        )

        result = {
            "playlist": {
                "id": snapshot.playlist_id,
                "url": snapshot.url,
                "title": snapshot.title,
                "uploader": snapshot.uploader,
                "count": len(snapshot.entries),
                "newCount": len(fresh),
                "totalDuration": snapshot.total_duration,
                "outputDir": str(target),
            },
            "qualities": [quality.to_dict() for quality in qualities],
            "container": active_container,
            "disk": self.disk_report(target),
            "stats": self.db.stats(snapshot.playlist_id),
        }
        self.events.publish("analyze_done", **result)
        return result

    def set_playlist_output(self, playlist_id: str, output_dir: str) -> dict:
        record = self.db.get_playlist(playlist_id)
        if record is None:
            raise KeyError(playlist_id)
        path = Path(output_dir).expanduser()
        if not path.is_absolute():
            path = path.resolve()
        self.db.update_playlist(playlist_id, output_dir=str(path))
        return {"outputDir": str(path), "disk": self.disk_report(path)}

    def refresh_qualities(self, playlist_id: str, *, container: str | None = None) -> dict:
        record = self.db.get_playlist(playlist_id)
        if record is None:
            raise KeyError(playlist_id)
        active = container or self.settings.container
        if container and container != self.settings.container:
            self.update_settings({"container": container})

        snapshot = playlist_module.fetch(record["url"])
        qualities = formats.analyze(
            snapshot.entries,
            container=active,
            sample_size=formats.DEFAULT_SAMPLE_SIZE,
        )
        return {
            "qualities": [quality.to_dict() for quality in qualities],
            "container": active,
            "disk": self.disk_report(record["output_dir"]),
        }

    def sync(self, playlist_id: str) -> dict:
        record = self.db.get_playlist(playlist_id)
        if record is None:
            raise KeyError(playlist_id)
        snapshot = playlist_module.fetch(record["url"])
        self.db.upsert_playlist(
            snapshot, output_dir=record["output_dir"], max_height=record["max_height"]
        )
        fresh = self.db.sync_videos(playlist_id, snapshot.entries)
        queued = self.db.enqueue(playlist_id, fresh)
        self.events.publish(
            "synced", playlistId=playlist_id, found=len(fresh), queued=queued
        )
        return {"found": len(fresh), "queued": queued, "total": len(snapshot.entries)}

    def enqueue_range(
        self,
        playlist_id: str,
        *,
        height: int | None = None,
        container: str | None = None,
        output_dir: str | None = None,
        start_from: int | None = None,
        end_at: int | None = None,
        redownload: bool = False,
    ) -> dict:
        record = self.db.get_playlist(playlist_id)
        if record is None:
            raise KeyError(playlist_id)

        if container and container != self.settings.container:
            self.update_settings({"container": container})
        if output_dir:
            self.set_playlist_output(playlist_id, output_dir)
        if height:
            self.db.update_playlist(playlist_id, max_height=height)

        video_ids = self.db.video_ids_in_range(playlist_id, start_from, end_at)
        requeue = (
            (db_module.FAILED, db_module.SKIPPED, db_module.PAUSED, db_module.DONE)
            if redownload
            else (db_module.FAILED, db_module.SKIPPED, db_module.PAUSED)
        )
        queued = self.db.enqueue(playlist_id, video_ids, requeue_states=requeue)
        stats = self.db.stats(playlist_id)
        self.events.publish("queued", playlistId=playlist_id, queued=queued, stats=stats)
        return {"selected": len(video_ids), "queued": queued, "stats": stats}

    # ---------- settings and system ----------

    def update_settings(self, changes: dict) -> Settings:
        merged = {**self.settings.to_dict(), **changes}
        self.settings = Settings.from_dict(merged)
        settings_module.save(self.settings)
        self.scheduler.update_settings(self.settings)
        self.events.publish("settings", settings=self.settings.to_dict())
        return self.settings

    def disk_report(self, path: Path | str) -> dict:
        target = Path(path)
        while not target.exists() and target.parent != target:
            target = target.parent
        try:
            usage = shutil.disk_usage(target)
        except OSError:
            return {"free": 0, "total": 0}
        return {"free": usage.free, "total": usage.total}

    # ---------- library / queue management ----------

    def remove_from_queue(
        self, playlist_id: str, *, job_ids: list[int] | None = None, states: list[str] | None = None
    ) -> dict:
        count = self.library.remove_from_queue(
            playlist_id, job_ids=job_ids, states=tuple(states) if states else None
        )
        self.events.publish("stats", stats=self.db.stats(playlist_id), paused=self.scheduler.paused)
        return {"removed": count, "stats": self.db.stats(playlist_id)}

    def delete_files(
        self,
        playlist_id: str,
        *,
        job_ids: list[int] | None = None,
        states: list[str] | None = None,
        all_done: bool = False,
    ) -> dict:
        result = self.library.delete_files(
            playlist_id,
            job_ids=job_ids,
            states=tuple(states) if states else None,
            all_done=all_done,
        )
        result["stats"] = self.db.stats(playlist_id)
        return result

    def restart_jobs(
        self,
        playlist_id: str,
        *,
        job_ids: list[int] | None = None,
        failed_only: bool = False,
        all_except_running: bool = False,
    ) -> dict:
        count = self.library.restart_jobs(
            playlist_id,
            job_ids=job_ids,
            failed_only=failed_only,
            all_except_running=all_except_running,
        )
        return {"restarted": count, "stats": self.db.stats(playlist_id)}

    def clear_queue(self, playlist_id: str, *, delete_files: bool = False) -> dict:
        result = self.library.clear_queue(playlist_id, delete_files=delete_files)
        result["stats"] = self.db.stats(playlist_id)
        return result

    # ---------- audio ----------

    def audio_presets(self) -> list[dict]:
        return catalog_dict()

    def preview_audio(self, *, job_id: int | None = None, video_id: str | None = None) -> bytes:
        """Return a short AAC clip with the current enhancement settings applied."""
        import subprocess
        import tempfile

        source_path: Path | None = None
        temp_dir: Path | None = None

        if job_id:
            job = self.db.get_job(job_id)
            if job and job.get("filepath"):
                source_path = Path(job["filepath"])
        elif video_id:
            temp_dir = Path(tempfile.mkdtemp(prefix="pldl-preview-"))
            url = f"https://www.youtube.com/watch?v={video_id}"
            argv = ytdlp.base_argv() + [
                "--no-playlist",
                "--format",
                "bestaudio/best",
                "--extract-audio",
                "--audio-format",
                "m4a",
                "--download-sections",
                "*0:45",
                "-o",
                str(temp_dir / "sample.%(ext)s"),
                url,
            ]
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=120,
                **resources.popen_kwargs(),
            )
            if proc.returncode != 0:
                raise PlaylistDownloaderError(
                    proc.stderr.strip().splitlines()[-1] if proc.stderr else "Could not fetch preview sample."
                )
            matches = list(temp_dir.glob("sample.*"))
            source_path = matches[0] if matches else None

        if source_path is None or not source_path.exists():
            raise PlaylistDownloaderError(
                "Nothing to preview yet — pick a video from the list or download one first."
            )

        try:
            return preview_clip(source_path, self.settings, start_sec=0, duration_sec=20)
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ---------- watch mode ----------

    def _watch_loop(self) -> None:
        last_run = 0.0
        while not self._stop_watching.wait(WATCH_TICK_SECONDS):
            hours = self.settings.watch_interval_hours
            if hours <= 0:
                continue
            if time.monotonic() - last_run < hours * 3600:
                continue
            last_run = time.monotonic()
            for record in self.db.list_playlists():
                try:
                    self.sync(record["id"])
                except Exception as exc:  # noqa: BLE001 - a bad playlist must not stop the rest
                    self.events.publish(
                        "watch_error", playlistId=record["id"], message=str(exc)
                    )
