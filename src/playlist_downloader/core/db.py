"""SQLite state: the video library and the job queue.

Keying videos by YouTube id rather than by playlist position is what makes a
later re-sync reliable. Positions shift whenever the owner inserts or removes a
video; ids do not, and the number assigned to a video on first download is kept
forever so filenames never change under you.

The queue lives here too, so closing the app mid-download loses nothing.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from . import resources
from .playlist import Entry, Snapshot

QUEUED = "queued"
RUNNING = "running"
PAUSED = "paused"
DONE = "done"
FAILED = "failed"
SKIPPED = "skipped"

ACTIVE_STATES = (QUEUED, RUNNING, PAUSED)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS playlists (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    uploader    TEXT NOT NULL DEFAULT '',
    output_dir  TEXT NOT NULL DEFAULT '',
    max_height  INTEGER NOT NULL DEFAULT 1080,
    total_count INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    synced_at   TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    playlist_id TEXT NOT NULL,
    video_id    TEXT NOT NULL,
    number      INTEGER NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    duration    REAL,
    position    INTEGER,
    first_seen  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (playlist_id, video_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id TEXT NOT NULL,
    video_id    TEXT NOT NULL,
    state       TEXT NOT NULL DEFAULT 'queued',
    priority    INTEGER NOT NULL DEFAULT 0,
    strategy    INTEGER NOT NULL DEFAULT 0,
    attempts    INTEGER NOT NULL DEFAULT 0,
    filepath    TEXT,
    filesize    INTEGER,
    verified    INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    started_at  TEXT,
    finished_at TEXT,
    UNIQUE (playlist_id, video_id)
);

CREATE INDEX IF NOT EXISTS jobs_by_state ON jobs (state);

CREATE TABLE IF NOT EXISTS attempts (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id   INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    ok       INTEGER NOT NULL,
    error    TEXT,
    log      TEXT,
    at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS attempts_by_job ON attempts (job_id);
"""

_JOB_COLUMNS = """
    j.id, j.playlist_id, j.video_id, j.state, j.priority, j.strategy,
    j.attempts, j.filepath, j.filesize, j.verified, j.error,
    j.started_at, j.finished_at,
    v.number, v.title, v.duration, v.position,
    p.output_dir, p.max_height, p.total_count
"""


def default_path() -> Path:
    return resources.app_data_dir() / "library.sqlite3"


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        with self._write_lock:
            self._connection().executescript(_SCHEMA)
            self._connection().commit()

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    # ---------- playlists ----------

    def upsert_playlist(self, snapshot: Snapshot, *, output_dir: str, max_height: int) -> None:
        with self._write_lock:
            self._connection().execute(
                """
                INSERT INTO playlists (id, url, title, uploader, output_dir, max_height,
                                       total_count, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    url = excluded.url,
                    title = excluded.title,
                    uploader = excluded.uploader,
                    output_dir = excluded.output_dir,
                    max_height = excluded.max_height,
                    total_count = excluded.total_count,
                    synced_at = datetime('now')
                """,
                (
                    snapshot.playlist_id,
                    snapshot.url,
                    snapshot.title,
                    snapshot.uploader,
                    output_dir,
                    max_height,
                    len(snapshot.entries),
                ),
            )

    def update_playlist(self, playlist_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._write_lock:
            self._connection().execute(
                f"UPDATE playlists SET {assignments} WHERE id = ?",
                (*fields.values(), playlist_id),
            )

    def get_playlist(self, playlist_id: str) -> dict | None:
        row = self._connection().execute(
            "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_playlists(self) -> list[dict]:
        rows = self._connection().execute(
            "SELECT * FROM playlists ORDER BY synced_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    # ---------- videos ----------

    def sync_videos(self, playlist_id: str, entries: Sequence[Entry]) -> list[str]:
        """Record the snapshot; return the ids that were not in the library yet.

        Videos already known keep the number they were first given. New ones
        continue the sequence in playlist order.
        """
        conn = self._connection()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                known = {
                    row["video_id"]
                    for row in conn.execute(
                        "SELECT video_id FROM videos WHERE playlist_id = ?", (playlist_id,)
                    )
                }
                next_number = (
                    conn.execute(
                        "SELECT COALESCE(MAX(number), 0) AS n FROM videos WHERE playlist_id = ?",
                        (playlist_id,),
                    ).fetchone()["n"]
                    + 1
                )

                fresh: list[str] = []
                for entry in entries:
                    if entry.video_id in known:
                        conn.execute(
                            """
                            UPDATE videos
                               SET title = ?, duration = ?, position = ?,
                                   last_seen = datetime('now')
                             WHERE playlist_id = ? AND video_id = ?
                            """,
                            (
                                entry.title,
                                entry.duration,
                                entry.position,
                                playlist_id,
                                entry.video_id,
                            ),
                        )
                        continue
                    conn.execute(
                        """
                        INSERT INTO videos
                            (playlist_id, video_id, number, title, duration, position)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            playlist_id,
                            entry.video_id,
                            next_number,
                            entry.title,
                            entry.duration,
                            entry.position,
                        ),
                    )
                    fresh.append(entry.video_id)
                    next_number += 1
                conn.execute("COMMIT")
                return fresh
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def highest_number(self, playlist_id: str) -> int:
        row = self._connection().execute(
            "SELECT COALESCE(MAX(number), 0) AS n FROM videos WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()
        return int(row["n"])

    # ---------- jobs ----------

    def video_ids_in_range(
        self, playlist_id: str, start: int | None = None, end: int | None = None
    ) -> list[str]:
        clauses = ["playlist_id = ?"]
        params: list[Any] = [playlist_id]
        if start is not None:
            clauses.append("number >= ?")
            params.append(start)
        if end is not None:
            clauses.append("number <= ?")
            params.append(end)
        rows = self._connection().execute(
            f"SELECT video_id FROM videos WHERE {' AND '.join(clauses)} ORDER BY number",
            params,
        ).fetchall()
        return [row["video_id"] for row in rows]

    def enqueue(
        self,
        playlist_id: str,
        video_ids: Iterable[str],
        *,
        requeue_states: Sequence[str] = (FAILED, SKIPPED, PAUSED),
    ) -> int:
        """Queue videos. Already-finished ones are left alone unless asked for."""
        ids = list(video_ids)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in requeue_states)
        statement = f"""
            INSERT INTO jobs (playlist_id, video_id, state)
            VALUES (?, ?, 'queued')
            ON CONFLICT(playlist_id, video_id) DO UPDATE SET
                state = CASE WHEN jobs.state IN ({placeholders})
                             THEN 'queued' ELSE jobs.state END,
                error = CASE WHEN jobs.state IN ({placeholders})
                             THEN NULL ELSE jobs.error END,
                strategy = CASE WHEN jobs.state IN ({placeholders})
                                THEN 0 ELSE jobs.strategy END
        """
        conn = self._connection()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                affected = 0
                for video_id in ids:
                    cursor = conn.execute(
                        statement,
                        (playlist_id, video_id, *requeue_states, *requeue_states, *requeue_states),
                    )
                    affected += cursor.rowcount or 0
                conn.execute("COMMIT")
                return affected
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def claim_next(self) -> dict | None:
        """Atomically move one queued job to running and return it."""
        conn = self._connection()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT j.id FROM jobs j
                      JOIN videos v ON v.playlist_id = j.playlist_id
                                   AND v.video_id = j.video_id
                     WHERE j.state = 'queued'
                     ORDER BY j.priority DESC, v.number ASC
                     LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return None
                conn.execute(
                    """
                    UPDATE jobs
                       SET state = 'running', started_at = datetime('now'), error = NULL
                     WHERE id = ?
                    """,
                    (row["id"],),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return self.get_job(row["id"])

    def get_job(self, job_id: int) -> dict | None:
        row = self._connection().execute(
            f"""
            SELECT {_JOB_COLUMNS} FROM jobs j
              JOIN videos v ON v.playlist_id = j.playlist_id AND v.video_id = j.video_id
              JOIN playlists p ON p.id = j.playlist_id
             WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_job(self, job_id: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._write_lock:
            self._connection().execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                (*fields.values(), job_id),
            )

    def set_state(self, job_id: int, state: str, **fields: Any) -> None:
        assignments = ["state = ?"]
        params: list[Any] = [state]
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            params.append(value)
        if state in (DONE, FAILED, SKIPPED):
            assignments.append("finished_at = datetime('now')")
        params.append(job_id)
        with self._write_lock:
            self._connection().execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", params
            )

    def bulk_set_state(self, from_states: Sequence[str], to_state: str, playlist_id: str | None = None) -> int:
        placeholders = ",".join("?" for _ in from_states)
        params: list[Any] = [to_state, *from_states]
        clause = ""
        if playlist_id:
            clause = " AND playlist_id = ?"
            params.append(playlist_id)
        with self._write_lock:
            cursor = self._connection().execute(
                f"UPDATE jobs SET state = ? WHERE state IN ({placeholders}){clause}",
                params,
            )
        return cursor.rowcount or 0

    def record_attempt(
        self, job_id: int, strategy: str, ok: bool, error: str = "", log: str = ""
    ) -> None:
        with self._write_lock:
            conn = self._connection()
            conn.execute(
                "INSERT INTO attempts (job_id, strategy, ok, error, log) VALUES (?, ?, ?, ?, ?)",
                (job_id, strategy, int(ok), error, log[-4000:]),
            )
            conn.execute("UPDATE jobs SET attempts = attempts + 1 WHERE id = ?", (job_id,))

    def attempts_for(self, job_id: int) -> list[dict]:
        rows = self._connection().execute(
            "SELECT strategy, ok, error, at FROM attempts WHERE job_id = ? ORDER BY id",
            (job_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_jobs(
        self,
        playlist_id: str | None = None,
        *,
        states: Sequence[str] | None = None,
        search: str = "",
        limit: int = 2000,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if playlist_id:
            clauses.append("j.playlist_id = ?")
            params.append(playlist_id)
        if states:
            clauses.append(f"j.state IN ({','.join('?' for _ in states)})")
            params.extend(states)
        if search:
            clauses.append("v.title LIKE ?")
            params.append(f"%{search}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])

        rows = self._connection().execute(
            f"""
            SELECT {_JOB_COLUMNS} FROM jobs j
              JOIN videos v ON v.playlist_id = j.playlist_id AND v.video_id = j.video_id
              JOIN playlists p ON p.id = j.playlist_id
            {where}
             ORDER BY v.number ASC
             LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self, playlist_id: str | None = None) -> dict[str, int]:
        clause = "WHERE playlist_id = ?" if playlist_id else ""
        params = (playlist_id,) if playlist_id else ()
        rows = self._connection().execute(
            f"SELECT state, COUNT(*) AS n FROM jobs {clause} GROUP BY state", params
        ).fetchall()
        counts = {state: 0 for state in (QUEUED, RUNNING, PAUSED, DONE, FAILED, SKIPPED)}
        for row in rows:
            counts[row["state"]] = row["n"]
        counts["total"] = sum(counts.values())
        return counts

    def downloaded_bytes(self, playlist_id: str | None = None) -> int:
        clause = "AND playlist_id = ?" if playlist_id else ""
        params = (playlist_id,) if playlist_id else ()
        row = self._connection().execute(
            f"SELECT COALESCE(SUM(filesize), 0) AS n FROM jobs WHERE state = 'done' {clause}",
            params,
        ).fetchone()
        return int(row["n"])

    def recover_running(self) -> int:
        """Anything left 'running' by a crash or a force-quit is queued again."""
        return self.bulk_set_state([RUNNING], QUEUED)
