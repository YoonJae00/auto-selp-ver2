from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir, user_config_dir, user_cache_dir

APP_NAME = "auto-selp-crawler"


def data_dir() -> Path:
    path = Path(user_data_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = Path(user_config_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = Path(user_cache_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "crawler.db"


def adapters_dir() -> Path:
    path = data_dir() / "adapters"
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir() -> Path:
    path = data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def assets_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets"
