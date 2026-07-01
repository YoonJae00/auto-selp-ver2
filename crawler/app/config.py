from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.paths import config_dir


@dataclass
class AppConfig:
    llm_provider: str = "gemini"
    browser_channel: str = "msedge"
    global_delay_seconds: int = 0
    check_updates_on_start: bool = True
    app_version: str = "0.1.0"
    auto_fallback_enabled: bool = True
    picker_ai_validation: bool = False


def _config_file() -> Path:
    return config_dir() / "settings.json"


def load_config() -> AppConfig:
    path = _config_file()
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppConfig()
    allowed = {field for field in AppConfig.__dataclass_fields__}
    filtered = {key: value for key, value in data.items() if key in allowed}
    config = AppConfig(**filtered)
    # Fix legacy integer browser_channel (from older versions that saved index instead of string)
    if isinstance(config.browser_channel, int):
        channels = ["msedge", "chrome", "chromium"]
        config.browser_channel = channels[config.browser_channel] if 0 <= config.browser_channel < len(channels) else "msedge"
    return config


def save_config(config: AppConfig) -> None:
    path = _config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
