from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.paths import adapters_dir, data_dir, db_path, exports_dir


def test_data_dir_creates_directory(tmp_path: Path) -> None:
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        result = data_dir()
        assert Path(result) == tmp_path
        assert result.exists()


def test_db_path_under_data_dir(tmp_path: Path) -> None:
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        assert db_path() == tmp_path / "crawler.db"


def test_adapters_dir_creates_subdirectory(tmp_path: Path) -> None:
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        result = adapters_dir()
        assert result == tmp_path / "adapters"
        assert result.exists()


def test_exports_dir_creates_subdirectory(tmp_path: Path) -> None:
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        result = exports_dir()
        assert result == tmp_path / "exports"
        assert result.exists()
