"""Runtime configuration and validation."""

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when runtime configuration is incomplete or invalid."""


def get_env(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    return value.strip().strip('"').strip("'") if value else ""


def _positive_int(key: str, default: int) -> int:
    raw = get_env(key, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{key} must be greater than zero")
    return value


@dataclass(frozen=True)
class MediaSettings:
    image_backend: str
    seedream_api_url: str
    seedream_api_key: str
    seedream_model: str
    image_size: str
    video_backend: str
    seedance_create_url: str
    seedance_query_url: str
    seedance_api_key: str
    seedance_model: str
    video_duration: int
    video_resolution: str
    video_ratio: str
    poll_interval: int
    max_wait: int
    output_dir: Path
    task_db_path: Path

    @classmethod
    def from_env(cls) -> "MediaSettings":
        output_dir = Path(get_env("MEDIA_OUTPUT_DIR", "output"))
        return cls(
            image_backend=get_env("IMAGE_BACKEND", "").lower(),
            seedream_api_url=get_env(
                "SEEDREAM_API_URL",
                "https://ark.cn-beijing.volces.com/api/v3/images/generations",
            ),
            seedream_api_key=get_env("SEEDREAM_API_KEY"),
            seedream_model=get_env("SEEDREAM_MODEL"),
            image_size=get_env("IMAGE_SIZE", "landscape_16_9"),
            video_backend=get_env("VIDEO_BACKEND", "").lower(),
            seedance_create_url=get_env(
                "SEEDANCE_CREATE_URL",
                "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
            ),
            seedance_query_url=get_env(
                "SEEDANCE_QUERY_URL",
                "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
            ),
            seedance_api_key=get_env("SEEDANCE_API_KEY"),
            seedance_model=get_env("SEEDANCE_MODEL"),
            video_duration=_positive_int("VIDEO_DURATION", 5),
            video_resolution=get_env("VIDEO_RESOLUTION", "720p"),
            video_ratio=get_env("VIDEO_RATIO", "16:9"),
            poll_interval=_positive_int("VIDEO_POLL_INTERVAL", 5),
            max_wait=_positive_int("VIDEO_MAX_WAIT", 600),
            output_dir=output_dir,
            task_db_path=Path(get_env("TASK_DB_PATH", str(output_dir / "tasks.db"))),
        )

    def validate(self) -> None:
        allowed = {"", "mock", "api"}
        if self.image_backend not in allowed:
            raise ConfigurationError("IMAGE_BACKEND must be empty, mock, or api")
        if self.video_backend not in allowed:
            raise ConfigurationError("VIDEO_BACKEND must be empty, mock, or api")
        if self.image_backend == "api":
            self._require("SEEDREAM_API_KEY", self.seedream_api_key)
            self._require("SEEDREAM_MODEL", self.seedream_model)
            self._require("SEEDREAM_API_URL", self.seedream_api_url)
        if self.video_backend == "api":
            self._require("SEEDANCE_API_KEY", self.seedance_api_key)
            self._require("SEEDANCE_MODEL", self.seedance_model)
            self._require("SEEDANCE_CREATE_URL", self.seedance_create_url)
            self._require("SEEDANCE_QUERY_URL", self.seedance_query_url)
        if self.video_duration not in {5, 10}:
            raise ConfigurationError("VIDEO_DURATION must be 5 or 10")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        probe = self.output_dir / ".write_probe"
        try:
            probe.touch(exist_ok=True)
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise ConfigurationError(f"MEDIA_OUTPUT_DIR is not writable: {self.output_dir}") from exc
        self.task_db_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _require(key: str, value: str) -> None:
        if not value or "xxxx" in value.lower() or "replace" in value.lower():
            raise ConfigurationError(f"{key} is required when its backend is api")

