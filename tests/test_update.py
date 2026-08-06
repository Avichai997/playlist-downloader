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


def test_check_for_update_finds_newer_via_api(monkeypatch):
    monkeypatch.setattr(
        update,
        "_from_api",
        lambda current, timeout: update.UpdateInfo(version="0.2.0", url="https://example/dmg"),
    )

    info = update.check_for_update("0.1.1")
    assert info is not None
    assert info.version == "0.2.0"
    assert info.url == "https://example/dmg"


def test_check_for_update_falls_back_to_release_redirect(monkeypatch):
    class FakeResponse:
        url = "https://github.com/Avichai997/playlist-downloader/releases/tag/v0.2.0"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fail_api(current, timeout):
        raise OSError("rate limited")

    monkeypatch.setattr(update, "_from_api", fail_api)
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(update, "_platform_suffix", lambda: ".dmg")

    info = update.check_for_update("0.1.1")
    assert info is not None
    assert info.version == "0.2.0"
    assert info.url.endswith("PlaylistDownloader-macOS-arm64.dmg")
