from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.config import load_config
from app.diagnostics import log_exception
from app.paths import cache_dir


logger = logging.getLogger(__name__)


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
        storage_state: dict | None = None,
    ) -> None:
        config = load_config()
        self.requested_channel = channel or config.browser_channel
        self.headless = headless
        self.user_agent = user_agent
        self.navigation_timeout_ms = navigation_timeout_ms
        self.use_temp_profile = use_temp_profile
        self.storage_state = storage_state
        self._playwright = None
        self._browser: BrowserContext | None = None
        self._temp_dir: Path | None = None

    async def start(self) -> None:
        if self._browser is not None:
            return
        logger.info(
            "starting browser channel=%s headless=%s temp_profile=%s",
            self.requested_channel,
            self.headless,
            self.use_temp_profile,
        )
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
        except Exception as exc:
            logger.warning("browser channel failed, falling back to chromium: %s", exc)
            if self.requested_channel != "chromium":
                launch_kwargs.pop("channel", None)
                try:
                    self._browser = await self._playwright.chromium.launch_persistent_context(
                        **launch_kwargs
                    )
                except Exception as fallback_exc:
                    logger.warning("persistent chromium failed, falling back to normal launch: %s", fallback_exc)
                    launch_kwargs.pop("user_data_dir", None)
                    try:
                        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
                    except Exception as launch_exc:
                        log_exception(logger, "browser launch failed", launch_exc)
                        raise
            else:
                log_exception(logger, "browser launch failed", exc)
                raise

        self._browser.set_default_navigation_timeout(self.navigation_timeout_ms)
        self._browser.set_default_timeout(self.navigation_timeout_ms)

        if self.storage_state:
            try:
                await self._browser.add_cookies(
                    self.storage_state.get("cookies", [])
                )
                origins = self.storage_state.get("origins", [])
                if origins:
                    import json as _json
                    script_parts = []
                    for origin in origins:
                        ls = origin.get("localStorage", [])
                        if ls:
                            # Playwright localStorage entry: {"name": "...", "value": "..."}
                            entries = []
                            for item in ls:
                                if isinstance(item, dict) and "name" in item and "value" in item:
                                    entries.append({"name": item["name"], "value": item["value"]})
                            if entries:
                                script_parts.append(
                                    f"if(location.origin==={_json.dumps(origin.get('origin',''))}){{"
                                    f"try{{var ls=window.localStorage;"
                                    f"var d={_json.dumps(entries)};"
                                    f"d.forEach(function(e){{ls.setItem(e.name,e.value);}});"
                                    f"}}catch(e){{}}}}"
                                )
                    if script_parts:
                        await self._browser.add_init_script(
                            "(() => {" + "".join(script_parts) + "})()"
                        )
            except Exception as exc:
                logger.warning("storage state restore failed: %s", exc)
        logger.info("browser started channel=%s", self.requested_channel)

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
        logger.info("closing browser")
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.warning("browser context close failed: %s", exc)
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("playwright stop failed: %s", exc)
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
    storage_state: dict | None = None,
) -> AsyncIterator[PlaywrightEngine]:
    engine = PlaywrightEngine(
        channel=channel,
        headless=headless,
        storage_state=storage_state,
    )
    try:
        await asyncio.wait_for(engine.start(), timeout=30)
        yield engine
    finally:
        await engine.close()
