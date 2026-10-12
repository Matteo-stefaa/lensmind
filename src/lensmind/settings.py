"""Configuration from LENSMIND_* environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGES = ("it", "en")
DIAL_MODES = ("M", "A", "AUTO")


def _default_photos_dir() -> Path:
    return Path("~/lensmind-photos").expanduser()


@dataclass(frozen=True)
class Settings:
    mock: bool = False
    mock_dial: str = "M"
    host: str = "0.0.0.0"
    port: int = 8000
    language: str = "it"
    photos_dir: Path = field(default_factory=_default_photos_dir)
    liveview_idle_seconds: float = 5.0
    anthropic_api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    max_turns: int = 6

    @property
    def assistant_ready(self) -> bool:
        """The assistant runs only with both an API key and a model identifier."""
        return bool(self.anthropic_api_key and self.model)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        language = env.get("LENSMIND_LANGUAGE", "it").lower()
        if language not in LANGUAGES:
            raise ValueError(f"LENSMIND_LANGUAGE must be one of {LANGUAGES}, not {language!r}")
        dial = env.get("LENSMIND_MOCK_DIAL", "M").upper()
        if dial not in DIAL_MODES:
            raise ValueError(f"LENSMIND_MOCK_DIAL must be one of {DIAL_MODES}, not {dial!r}")
        max_turns = int(env.get("LENSMIND_MAX_TURNS", "6"))
        if max_turns < 1:
            raise ValueError(f"LENSMIND_MAX_TURNS must be at least 1, not {max_turns}")
        photos_dir = env.get("LENSMIND_PHOTOS_DIR")
        return cls(
            mock=env.get("LENSMIND_MOCK", "0").strip().lower() in {"1", "true", "yes", "on"},
            mock_dial=dial,
            host=env.get("LENSMIND_HOST", "0.0.0.0"),
            port=int(env.get("LENSMIND_PORT", "8000")),
            language=language,
            photos_dir=Path(photos_dir).expanduser() if photos_dir else _default_photos_dir(),
            liveview_idle_seconds=float(env.get("LENSMIND_LIVEVIEW_IDLE_SECONDS", "5")),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", "").strip() or None,
            model=env.get("LENSMIND_MODEL", "").strip() or None,
            max_turns=max_turns,
        )
