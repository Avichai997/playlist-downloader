"""Live checks against YouTube. Metadata only — nothing is downloaded.

Skipped unless PLDL_LIVE_TESTS=1, so the offline suite stays fast and CI does
not depend on the network.
"""
import os

import pytest

from playlist_downloader.core import formats, playlist, resources, ytdlp

pytestmark = pytest.mark.skipif(
    os.environ.get("PLDL_LIVE_TESTS") != "1",
    reason="set PLDL_LIVE_TESTS=1 to run live metadata checks",
)

# Blender Foundation's "Big Buck Bunny", released under Creative Commons.
SAMPLE_VIDEO = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def test_engines_are_bundled_and_runnable():
    assert resources.ytdlp_path().exists()
    assert resources.ffmpeg_location() is not None
    assert resources.ffprobe_path() is not None
    assert ytdlp.version()


def test_single_video_reads_as_a_one_entry_snapshot():
    snapshot = playlist.fetch(SAMPLE_VIDEO)
    assert len(snapshot.entries) == 1
    assert snapshot.entries[0].duration
    assert snapshot.total_duration > 0


def test_analysis_reports_qualities_with_sizes():
    snapshot = playlist.fetch(SAMPLE_VIDEO)
    qualities = formats.analyze(snapshot.entries, container="mkv", sample_size=1)

    assert qualities, "no qualities were found"
    assert qualities == sorted(qualities, key=lambda q: q.height, reverse=True)
    for quality in qualities:
        assert quality.estimated_total_bytes > 0
        assert quality.bytes_per_second > 0
    heights = {quality.height for quality in qualities}
    assert heights & {360, 480, 720, 1080}


def test_format_selector_caps_height():
    selector = ytdlp.format_selector(max_height=720, container="mkv", audio_only=False)
    assert "height<=720" in selector
    assert ytdlp.lower_height(1080, 1) == 720
    assert ytdlp.lower_height(1080, 2) == 480
