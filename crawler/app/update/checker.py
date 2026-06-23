from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass
class ReleaseInfo:
    tag: str
    name: str
    url: str


def get_latest_release(repo: str = "anomalyco/auto-selp-ver2") -> ReleaseInfo | None:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Auto-Selp-Crawler"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return ReleaseInfo(
                tag=data.get("tag_name", ""),
                name=data.get("name", ""),
                url=data.get("html_url", ""),
            )
    except Exception:
        return None


def parse_version(tag: str) -> tuple[int, ...]:
    cleaned = tag.lstrip("v").strip()
    parts: list[int] = []
    for part in cleaned.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer(current: str, latest: str) -> bool:
    current_parts = parse_version(current)
    latest_parts = parse_version(latest)
    return latest_parts > current_parts
