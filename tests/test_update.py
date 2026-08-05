from playlist_downloader.core import update


def test_ver_tuple():
    assert update._ver_tuple("v1.2.3") == (1, 2, 3)
    assert update._ver_tuple("0.1.1") == (0, 1, 1)
    assert update._ver_tuple("v0.1.10") > update._ver_tuple("v0.1.9")


def test_check_for_update_skips_current_or_older(monkeypatch):
    import io
    import json

    payload = {"tag_name": "v0.1.1", "assets": []}

    class FakeResponse:
        def __enter__(self):
            return io.BytesIO(json.dumps(payload).encode())

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    assert update.check_for_update("0.1.1") is None


def test_check_for_update_finds_newer(monkeypatch):
    import io
    import json

    payload = {
        "tag_name": "v0.2.0",
        "assets": [
            {"name": "PlaylistDownloader-macOS-arm64.dmg", "browser_download_url": "https://example/dmg"},
        ],
    }

    class FakeResponse:
        def __enter__(self):
            return io.BytesIO(json.dumps(payload).encode())

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(update, "_platform_suffix", lambda: ".dmg")

    info = update.check_for_update("0.1.1")
    assert info is not None
    assert info.version == "0.2.0"
    assert info.url == "https://example/dmg"
