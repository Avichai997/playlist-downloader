"""Application-level operations, shared by the HTTP API and the headless CLI."""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from . import db as db_module
from . import formats, naming, playlist as playlist_module
from . import settings as settings_module
from . import ytdlp
from .db import Database
from .events import EventBus
from .scheduler import Scheduler
from .settings import Settings

WATCH_TICK_SECONDS = 300


class Service:
    def __init__(self, database: Database | None = None) -> None:
        self.settings: Settings = settings_module.load()
        self.db = database or Database()
        self.events = EventBus()
        self.scheduler = Scheduler(self.db, self.settings, self.events)
        self._watch_thread: threading.Thread | None = None
        self._stop_watching = threading.Event()

    # ---------- lifecycle ----------

    def start(self) -> None:
        self.scheduler.start()
        if self.settings.update_ytdlp_on_launch:
            threading.Thread(target=self._update_ytdlp, daemon=True).start()
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

    # ---------- playlists ----------

    def analyze(self, url: str, *, sample_size: int = formats.DEFAULT_SAMPLE_SIZE) -> dict:
        self.events.publish("analyze_stage", stage="reading playlist")
        snapshot = playlist_module.fetch(url)

        output_dir = Path(self.settings.output_root) / naming.sanitize(snapshot.title)
        self.db.upsert_playlist(
            snapshot, output_dir=str(output_dir), max_height=self.settings.max_height
        )
        fresh = self.db.sync_videos(snapshot.playlist_id, snapshot.entries)

        self.events.publish("analyze_stage", stage="checking available qualities")

        def report(done: int, total: int) -> None:
            self.events.publish("analyze_progress", done=done, total=total)

        qualities = formats.analyze(
            snapshot.entries,
            container=self.settings.container,
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
                "outputDir": str(output_dir),
            },
            "qualities": [quality.to_dict() for quality in qualities],
            "disk": self.disk_report(output_dir),
            "stats": self.db.stats(snapshot.playlist_id),
        }
        self.events.publish("analyze_done", **result)
        return result

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
        start_from: int | None = None,
        end_at: int | None = None,
        redownload: bool = False,
    ) -> dict:
        record = self.db.get_playlist(playlist_id)
        if record is None:
            raise KeyError(playlist_id)

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
