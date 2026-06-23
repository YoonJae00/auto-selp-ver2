from __future__ import annotations

from pathlib import Path

import yaml

from app.analyzer.adapter_schema import Adapter
from app.paths import adapters_dir


def adapter_path(supplier_slug: str) -> Path:
    return adapters_dir() / f"{supplier_slug}.yaml"


def save_adapter(supplier_slug: str, yaml_text: str) -> Path:
    path = adapter_path(supplier_slug)
    if path.exists():
        backup = path.with_suffix(".yaml.bak")
        path.rename(backup)
    path.write_text(yaml_text, encoding="utf-8")
    return path


def load_adapter(supplier_slug: str) -> Adapter:
    path = adapter_path(supplier_slug)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Adapter.model_validate(raw)


def load_adapter_from_text(yaml_text: str) -> Adapter:
    raw = yaml.safe_load(yaml_text)
    return Adapter.model_validate(raw)


def list_adapters() -> list[str]:
    return sorted(p.stem for p in adapters_dir().glob("*.yaml"))


def adapter_exists(supplier_slug: str) -> bool:
    return adapter_path(supplier_slug).exists()
