import pytest

from playlist_downloader.core import db as db_module
from playlist_downloader.core.db import Database
from playlist_downloader.core.playlist import Entry, Snapshot


def _snapshot(*ids: str) -> Snapshot:
    return Snapshot(
        playlist_id="PL1",
        url="https://example.invalid/list",
        title="Course",
        uploader="Someone",
        entries=tuple(
            Entry(video_id=vid, title=f"Video {vid}", duration=60.0, position=i)
            for i, vid in enumerate(ids, start=1)
        ),
    )


@pytest.fixture
def database(tmp_path):
    return Database(tmp_path / "library.sqlite3")


def _store(database: Database, snapshot: Snapshot) -> list[str]:
    database.upsert_playlist(snapshot, output_dir="/tmp/out", max_height=1080)
    return database.sync_videos(snapshot.playlist_id, snapshot.entries)


def test_numbers_are_assigned_in_playlist_order(database):
    _store(database, _snapshot("a", "b", "c"))
    jobs = database.video_ids_in_range("PL1")
    assert jobs == ["a", "b", "c"]


def test_verify_missing_files_requeues_done_jobs_without_files(database, tmp_path):
    _store(database, _snapshot("a", "b"))
    database.enqueue("PL1", ["a", "b"])
    missing = tmp_path / "gone.mkv"
    present = tmp_path / "kept.mkv"
    present.write_bytes(b"x" * 100)

    jobs = {job["video_id"]: job for job in database.list_jobs("PL1") if job["id"]}
    database.set_state(jobs["a"]["id"], db_module.DONE, filepath=str(missing), filesize=10)
    database.set_state(jobs["b"]["id"], db_module.DONE, filepath=str(present), filesize=100)

    from playlist_downloader.core.library import Library

    result = Library(database).verify_missing_files("PL1")
    assert result["requeued"] == 1
    states = {row["video_id"]: row["state"] for row in database.list_jobs("PL1") if row["id"]}
    assert states["a"] == db_module.QUEUED
    assert states["b"] == db_module.DONE


def test_resync_keeps_existing_numbers_and_appends_new_ones(database):
    _store(database, _snapshot("a", "b", "c"))

    # The owner inserted a video at the front and appended one at the end.
    fresh = _store(database, _snapshot("new-front", "a", "b", "c", "new-end"))

    assert sorted(fresh) == ["new-end", "new-front"]
    database.enqueue("PL1", fresh)
    numbers = {
        job["video_id"]: job["number"] for job in database.list_jobs("PL1")
    }
    # 'a' keeps number 1 even though it is now second in the playlist.
    assert numbers["new-front"] == 4
    assert numbers["new-end"] == 5


def test_only_new_videos_are_queued_on_resync(database):
    _store(database, _snapshot("a", "b"))
    database.enqueue("PL1", ["a", "b"])
    for job in database.list_jobs("PL1"):
        database.set_state(job["id"], db_module.DONE, filesize=100)

    fresh = _store(database, _snapshot("a", "b", "c"))
    database.enqueue("PL1", fresh)

    stats = database.stats("PL1")
    assert stats[db_module.DONE] == 2
    assert stats[db_module.QUEUED] == 1


def test_finished_videos_are_left_alone_unless_redownload_asked(database):
    _store(database, _snapshot("a"))
    database.enqueue("PL1", ["a"])
    job = database.list_jobs("PL1")[0]
    database.set_state(job["id"], db_module.DONE, filesize=10)

    database.enqueue("PL1", ["a"])
    assert database.stats("PL1")[db_module.DONE] == 1

    database.enqueue("PL1", ["a"], requeue_states=(db_module.DONE,))
    assert database.stats("PL1")[db_module.QUEUED] == 1


def test_claim_next_hands_out_each_job_once(database):
    _store(database, _snapshot("a", "b"))
    database.enqueue("PL1", ["a", "b"])

    first = database.claim_next()
    second = database.claim_next()
    third = database.claim_next()

    assert {first["video_id"], second["video_id"]} == {"a", "b"}
    assert third is None
    assert database.stats("PL1")[db_module.RUNNING] == 2


def test_running_jobs_are_requeued_after_a_crash(database):
    _store(database, _snapshot("a"))
    database.enqueue("PL1", ["a"])
    database.claim_next()

    assert database.recover_running() == 1
    assert database.stats("PL1")[db_module.QUEUED] == 1


def test_range_selection_uses_assigned_numbers(database):
    _store(database, _snapshot(*(f"v{i}" for i in range(1, 11))))
    assert database.video_ids_in_range("PL1", 8, None) == ["v8", "v9", "v10"]
    assert database.video_ids_in_range("PL1", 3, 4) == ["v3", "v4"]
