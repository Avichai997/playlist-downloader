"""Remove downloads, reset the queue, and restart jobs."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import db as db_module
from .db import Database


def _unlink(path: str | None) -> bool:
    if not path:
        return False
    target = Path(path)
    if not target.exists():
        return False
    target.unlink()
    for suffix in (".part", ".ytdl", ".temp"):
        sibling = target.with_suffix(target.suffix + suffix)
        sibling.unlink(missing_ok=True)
    return True


class Library:
    def __init__(self, database: Database) -> None:
        self._db = database

    def remove_from_queue(
        self,
        playlist_id: str,
        *,
        job_ids: list[int] | None = None,
        states: tuple[str, ...] | None = None,
    ) -> int:
        """Mark jobs as skipped — does not delete files on disk."""
        jobs = self._target_jobs(playlist_id, job_ids, states)
        count = 0
        for job in jobs:
            if job["state"] in (db_module.RUNNING,):
                continue
            self._db.set_state(job["id"], db_module.SKIPPED, error="Removed from queue.")
            count += 1
        return count

    def delete_files(
        self,
        playlist_id: str,
        *,
        job_ids: list[int] | None = None,
        states: tuple[str, ...] | None = None,
        all_done: bool = False,
    ) -> dict:
        """Delete files from disk and reset jobs to queued."""
        if all_done:
            states = (db_module.DONE,)
        jobs = self._target_jobs(playlist_id, job_ids, states)
        deleted = 0
        reset = 0
        for job in jobs:
            if job["state"] == db_module.RUNNING:
                continue
            if _unlink(job.get("filepath")):
                deleted += 1
            self._db.set_state(
                job["id"],
                db_module.QUEUED,
                filepath=None,
                filesize=None,
                verified=0,
                error=None,
                strategy=0,
            )
            reset += 1
        return {"deleted": deleted, "reset": reset}

    def restart_jobs(
        self,
        playlist_id: str,
        *,
        job_ids: list[int] | None = None,
        failed_only: bool = False,
        all_except_running: bool = False,
    ) -> int:
        if all_except_running:
            states = (db_module.DONE, db_module.FAILED, db_module.SKIPPED, db_module.PAUSED, db_module.QUEUED)
        elif failed_only:
            states = (db_module.FAILED,)
        else:
            states = None
        jobs = self._target_jobs(playlist_id, job_ids, states)
        count = 0
        for job in jobs:
            if job["state"] == db_module.RUNNING:
                continue
            self._db.set_state(job["id"], db_module.QUEUED, error=None, strategy=0)
            count += 1
        return count

    def clear_queue(
        self,
        playlist_id: str,
        *,
        delete_files: bool = False,
        remove_partials: bool = True,
    ) -> dict:
        record = self._db.get_playlist(playlist_id)
        if record is None:
            raise KeyError(playlist_id)
        output_dir = Path(record["output_dir"])
        deleted_files = 0
        if delete_files:
            result = self.delete_files(playlist_id, states=(db_module.DONE, db_module.FAILED, db_module.PAUSED, db_module.SKIPPED, db_module.QUEUED))
            deleted_files = result["deleted"]
        else:
            self.remove_from_queue(
                playlist_id,
                states=(db_module.QUEUED, db_module.PAUSED, db_module.FAILED, db_module.SKIPPED),
            )

        partials = 0
        if remove_partials and output_dir.exists():
            incomplete = output_dir / ".incomplete"
            if incomplete.is_dir():
                shutil.rmtree(incomplete, ignore_errors=True)
                partials = 1
            for part in output_dir.glob("*.part"):
                part.unlink(missing_ok=True)
                partials += 1

        return {"deletedFiles": deleted_files, "partialsRemoved": partials}

    def verify_missing_files(self, playlist_id: str) -> dict:
        """Re-queue finished jobs whose files are no longer on disk."""
        jobs = self._db.list_jobs(playlist_id, states=(db_module.DONE,))
        requeued = 0
        for job in jobs:
            job_id = job.get("id")
            if not job_id:
                continue
            path = job.get("filepath")
            if path and Path(path).is_file():
                continue
            self._db.set_state(
                job_id,
                db_module.QUEUED,
                filepath=None,
                filesize=None,
                verified=0,
                error="File no longer on disk.",
            )
            requeued += 1
        return {"requeued": requeued}

    def reset_playlist(
        self,
        playlist_id: str,
        *,
        delete_files: bool = False,
        refetch: bool = True,
    ) -> dict:
        """Clear all download state and optionally wipe files so you can start fresh."""
        from . import playlist as playlist_module

        record = self._db.get_playlist(playlist_id)
        if record is None:
            raise KeyError(playlist_id)

        deleted_files = 0
        if delete_files:
            for job in self._db.list_jobs(playlist_id):
                if not job.get("id"):
                    continue
                if _unlink(job.get("filepath")):
                    deleted_files += 1
            output_dir = Path(record["output_dir"])
            if output_dir.exists():
                incomplete = output_dir / ".incomplete"
                if incomplete.is_dir():
                    shutil.rmtree(incomplete, ignore_errors=True)
                for part in output_dir.glob("*.part"):
                    part.unlink(missing_ok=True)

        cleared = self._db.delete_all_jobs(playlist_id)
        video_count = self._db.stats(playlist_id)["total"]
        playlist_info: dict | None = None

        if refetch:
            snapshot = playlist_module.fetch(record["url"])
            self._db.upsert_playlist(
                snapshot,
                output_dir=record["output_dir"],
                max_height=record["max_height"],
            )
            self._db.sync_videos(playlist_id, snapshot.entries)
            video_count = len(snapshot.entries)
            playlist_info = {
                "id": playlist_id,
                "url": snapshot.url,
                "title": snapshot.title,
                "uploader": snapshot.uploader,
                "count": video_count,
                "newCount": 0,
                "totalDuration": snapshot.total_duration,
                "outputDir": record["output_dir"],
            }

        return {
            "jobsCleared": cleared,
            "deletedFiles": deleted_files,
            "videoCount": video_count,
            "stats": self._db.stats(playlist_id),
            "playlist": playlist_info,
        }

    def _target_jobs(
        self,
        playlist_id: str,
        job_ids: list[int] | None,
        states: tuple[str, ...] | None,
    ) -> list[dict]:
        if job_ids:
            return [job for jid in job_ids if (job := self._db.get_job(jid)) is not None]
        return self._db.list_jobs(playlist_id, states=list(states) if states else None)
