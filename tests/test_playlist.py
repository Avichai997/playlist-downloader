from playlist_downloader.core import playlist as playlist_module


def test_fetch_all_entries_paginates_when_first_page_is_short(monkeypatch):
    calls: list[str | None] = []

    def fake_fetch(url: str, *, playlist_items: str | None = None):
        calls.append(playlist_items)
        if playlist_items is None:
            return {
                "_type": "playlist",
                "id": "PL1",
                "title": "Course",
                "playlist_count": 5,
                "entries": [
                    {"id": f"v{i}", "title": f"Video {i}", "duration": 60, "playlist_index": i}
                    for i in range(1, 3)
                ],
            }
        assert playlist_items == "3:5"
        return {
            "_type": "playlist",
            "entries": [
                {"id": f"v{i}", "title": f"Video {i}", "duration": 60, "playlist_index": i}
                for i in range(3, 6)
            ],
        }

    monkeypatch.setattr(playlist_module, "_fetch_flat_json", fake_fetch)

    info = {
        "_type": "playlist",
        "id": "PL1",
        "playlist_count": 5,
        "entries": [
            {"id": f"v{i}", "title": f"Video {i}", "duration": 60, "playlist_index": i}
            for i in range(1, 3)
        ],
    }
    entries = playlist_module._fetch_all_entries("https://example.invalid?list=PL1", info)
    assert [entry.video_id for entry in entries] == ["v1", "v2", "v3", "v4", "v5"]
    assert calls == ["3:5"]
