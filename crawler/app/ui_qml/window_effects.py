from __future__ import annotations

import logging
import os
import sys
from enum import Enum
from typing import Callable, Mapping, Sequence


logger = logging.getLogger(__name__)

Version = Sequence[int]
NativeApply = Callable[[object], None]

MOTION_OVERRIDE_ENV = "AUTO_SELP_QML_MOTION_ENABLED"


class Backdrop(Enum):
    MICA = "mica"
    ACRYLIC = "acrylic"
    VIBRANCY = "vibrancy"
    COLOR = "color"


def choose_backdrop(platform: str, version: Version, native_available: bool) -> Backdrop:
    normalized_version = tuple(version)
    if platform == "win32" and native_available and normalized_version >= (10, 0, 22000):
        return Backdrop.MICA
    if platform == "win32" and native_available:
        return Backdrop.ACRYLIC
    if platform == "darwin" and native_available:
        return Backdrop.VIBRANCY
    return Backdrop.COLOR


def apply_backdrop_policy(
    window: object,
    *,
    platform: str | None = None,
    version: Version | None = None,
    native_available: bool | None = None,
    native_apply: NativeApply | None = None,
) -> Backdrop:
    target_platform = platform or sys.platform
    target_version = tuple(version or _platform_version(target_platform))
    has_native = _native_backdrop_available(target_platform) if native_available is None else native_available
    policy = choose_backdrop(target_platform, target_version, has_native)
    if policy is Backdrop.COLOR:
        return Backdrop.COLOR

    try:
        (native_apply or _apply_native_backdrop)(window)
    except Exception:
        logger.warning("native backdrop unavailable; using color fallback")
        return Backdrop.COLOR
    return policy


def motion_enabled_from_environment(environ: Mapping[str, str] | None = None) -> bool | None:
    source = os.environ if environ is None else environ
    raw = source.get(MOTION_OVERRIDE_ENV)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if value in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return None


def detect_motion_enabled(application: object | None = None, environ: Mapping[str, str] | None = None) -> bool:
    override = motion_enabled_from_environment(environ)
    if override is not None:
        return override

    try:
        style_hints = getattr(application, "styleHints", lambda: None)() if application is not None else None
        accessibility = getattr(style_hints, "accessibility", lambda: None)() if style_hints is not None else None
    except RuntimeError:
        return True
    for attr in ("reducedMotion", "reduceMotion", "prefersReducedMotion"):
        hint = getattr(accessibility, attr, None)
        try:
            if callable(hint):
                return not bool(hint())
            if hint is not None:
                return not bool(hint)
        except RuntimeError:
            return True
    return True


def _platform_version(platform: str) -> tuple[int, ...]:
    if platform == "win32" and hasattr(sys, "getwindowsversion"):
        win_version = sys.getwindowsversion()
        return (win_version.major, win_version.minor, win_version.build)
    if platform == "darwin":
        return tuple(int(part) for part in os.uname().release.split(".")[:3] if part.isdigit())
    return ()


def _native_backdrop_available(_platform: str) -> bool:
    return False


def _apply_native_backdrop(_window: object) -> None:
    raise RuntimeError("native bridge unavailable")
