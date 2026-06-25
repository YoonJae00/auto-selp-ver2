from __future__ import annotations

import asyncio
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.config import load_config
from app.paths import cache_dir


@dataclass
class BrowserChannel:
    name: str
    fallback: str | None = None


CHANNEL_CHAIN: list[BrowserChannel] = [
    BrowserChannel("msedge", fallback="chrome"),
    BrowserChannel("chrome", fallback="chromium"),
    BrowserChannel("chromium"),
]


class PlaywrightEngine:
    def __init__(
        self,
        channel: str | None = None,
        headless: bool = True,
        user_agent: str | None = None,
        navigation_timeout_ms: int = 20_000,
        use_temp_profile: bool = True,
    ) -> None:
        config = load_config()
        self.requested_channel = channel or config.browser_channel
        self.headless = headless
        self.user_agent = user_agent
        self.navigation_timeout_ms = navigation_timeout_ms
        self.use_temp_profile = use_temp_profile
        self._playwright = None
        self._browser: BrowserContext | None = None
        self._temp_dir: Path | None = None

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()

        if self.use_temp_profile:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="crawler_pw_"))
            profile_dir = self._temp_dir
        else:
            profile_dir = cache_dir() / "browser_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs: dict = {
            "headless": self.headless,
            "user_data_dir": str(profile_dir),
        }
        if self.requested_channel and self.requested_channel != "chromium":
            launch_kwargs["channel"] = self.requested_channel

        try:
            self._browser = await self._playwright.chromium.launch_persistent_context(
                **launch_kwargs
            )
        except Exception:
            if self.requested_channel != "chromium":
                launch_kwargs.pop("channel", None)
                try:
                    self._browser = await self._playwright.chromium.launch_persistent_context(
                        **launch_kwargs
                    )
                except Exception:
                    launch_kwargs.pop("user_data_dir", None)
                    self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            else:
                raise

        self._browser.set_default_navigation_timeout(self.navigation_timeout_ms)
        self._browser.set_default_timeout(self.navigation_timeout_ms)

    async def new_page(self) -> Page:
        if self._browser is None:
            await self.start()
        assert self._browser is not None
        page = await self._browser.new_page()
        if self.user_agent:
            try:
                await page.set_extra_http_headers({"User-Agent": self.user_agent})
            except Exception:
                pass
        return page

    async def close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if self._temp_dir and self._temp_dir.exists():
            try:
                import shutil
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_dir = None


@asynccontextmanager
async def create_engine(
    channel: str | None = None,
    headless: bool = True,
) -> AsyncIterator[PlaywrightEngine]:
    engine = PlaywrightEngine(channel=channel, headless=headless)
    try:
        await asyncio.wait_for(engine.start(), timeout=30)
        yield engine
    finally:
        await engine.close()
