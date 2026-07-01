from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from app.paths import cache_dir

_LOCK = threading.Lock()
_CACHE: dict[str, dict] = {}


def _session_dir() -> Path:
    d = cache_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    try:
        import os
        os.chmod(str(d), 0o700)
    except Exception:
        pass
    return d


def _path_for(key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", key)[:120]
    return _session_dir() / f"{safe}.json"


def save_session_state(supplier_key: str, state: dict) -> None:
    """저장: 메모리 캐시 + JSON 파일 (0600 권한, atomic write)."""
    with _LOCK:
        _CACHE[supplier_key] = state
    try:
        import os, tempfile
        path = _path_for(supplier_key)
        # atomic write: 임시 파일 → rename
        fd, tmp_path = tempfile.mkstemp(dir=str(_session_dir()), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(state, ensure_ascii=False))
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    except Exception:
        pass


def load_session_state(supplier_key: str) -> dict | None:
    """로드: 메모리 우선, 없으면 파일. 없으면 None."""
    with _LOCK:
        if supplier_key in _CACHE:
            return _CACHE[supplier_key]
    try:
        p = _path_for(supplier_key)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            with _LOCK:
                _CACHE[supplier_key] = data
            return data
    except Exception:
        pass
    return None


def clear_session_state(supplier_key: str) -> None:
    with _LOCK:
        _CACHE.pop(supplier_key, None)
    try:
        p = _path_for(supplier_key)
        if p.exists():
            p.unlink()
    except Exception:
        pass
