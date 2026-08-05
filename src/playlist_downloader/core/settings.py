"""User settings, persisted as JSON in the app data directory."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import naming, resources

MAX_PARALLEL_VIDEOS = 8


def _default_output_root() -> str:
    downloads = Path.home() / "Downloads"
    return str(downloads if downloads.is_dir() else Path.home())


@dataclass
class Settings:
    output_root: str = field(default_factory=_default_output_root)

    container: str = "mkv"
    max_height: int = 1080
    audio_only: bool = False
    audio_format: str = "m4a"

    parallel_videos: int = 4
    fragments_per_video: int = 16
    rate_limit: str = ""
    night_window: str = ""

    numbering: str = naming.PADDED
    pad_width: int = 0
    windows_safe_filenames: bool = True

    subtitles: bool = True
    sub_langs: list[str] = field(default_factory=lambda: ["en", "he"])
    auto_subs: bool = True
    keep_sub_files: bool = False

    embed_thumbnail: bool = True
    embed_metadata: bool = True
    embed_chapters: bool = True
    sponsorblock: str = "off"

    cookies_browser: str = ""
    verify_downloads: bool = True
    update_ytdlp_on_launch: bool = True
    watch_interval_hours: int = 0

    def clamped(self) -> Settings:
        self.parallel_videos = max(1, min(MAX_PARALLEL_VIDEOS, self.parallel_videos))
        self.fragments_per_video = max(1, min(64, self.fragments_per_video))
        self.max_height = max(144, min(4320, self.max_height))
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known}).clamped()


def settings_path() -> Path:
    return resources.app_data_dir() / "settings.json"


def load() -> Settings:
    path = settings_path()
    if not path.exists():
        return Settings()
    try:
        return Settings.from_dict(json.loads(path.read_text("utf-8")))
    except (OSError, ValueError, TypeError):
        return Settings()


def save(settings: Settings) -> None:
    path = settings_path()
    path.write_text(json.dumps(settings.clamped().to_dict(), indent=2), "utf-8")
