from __future__ import annotations

import pytest

from app.analyzer.login_helper import _login_via_form_heuristics, _login_via_selectors
from app.analyzer.site_probe import probe_site


class Element:
    def __init__(self, visible: bool = True) -> None:
        self.visible = visible
        self.filled = ""
        self.clicked = False

    async def is_visible(self) -> bool:
        return self.visible

    async def evaluate(self, _script: str):
        return object()

    async def fill(self, value: str) -> None:
        self.filled = value

    async def click(self) -> None:
        self.clicked = True

    async def press(self, _key: str) -> None:
        pass

    def owner_frame(self):
        return None


class LoginPage:
    main_frame = object()

    def __init__(self, *, password_visible: bool = True, success_selector: str = "") -> None:
        self.password = Element(password_visible)
        self.user = Element()
        self.submit = Element()
        self.success_selector = success_selector
        self.frames = []

    async def query_selector(self, selector: str):
        if selector == self.success_selector:
            return Element()
        if selector == "input[type='password']":
            return self.password
        if "input[type='text']" in selector or "input[type='email']" in selector:
            return self.user
        if "submit" in selector or "login" in selector or "check()" in selector:
            return self.submit
        return None

    async def wait_for_selector(self, selector: str, **_kwargs):
        return await self.query_selector(selector)

    async def wait_for_timeout(self, _ms: int) -> None:
        pass


@pytest.mark.asyncio
async def test_form_login_fails_when_password_field_remains_visible() -> None:
    page = LoginPage(password_visible=True)

    assert await _login_via_form_heuristics(page, "bad-user", "bad-password", lambda _msg: None) is False


@pytest.mark.asyncio
async def test_selector_login_requires_configured_success_indicator() -> None:
    page = LoginPage(password_visible=False)
    config = {
        "id_selector": "input[type='text']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit']",
        "success_indicator": ".logout",
    }

    assert await _login_via_selectors(page, "user", "password", config, lambda _msg: None) is False


@pytest.mark.asyncio
async def test_selector_login_succeeds_with_configured_success_indicator() -> None:
    page = LoginPage(password_visible=False, success_selector=".logout")
    config = {
        "id_selector": "input[type='text']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit']",
        "success_indicator": ".logout",
    }

    assert await _login_via_selectors(page, "user", "password", config, lambda _msg: None) is True


@pytest.mark.asyncio
async def test_probe_raises_on_login_failure(monkeypatch) -> None:
    async def failed_login(*_args, **_kwargs) -> bool:
        return False

    class Page:
        url = "https://shop.example/login"

        def on(self, *_args):
            pass

    class Engine:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def new_page(self):
            return Page()

    monkeypatch.setattr("app.crawlers.engine.create_engine", lambda **_kwargs: Engine())
    monkeypatch.setattr("app.analyzer.site_probe.perform_login", failed_login)

    with pytest.raises(RuntimeError, match="로그인에 실패"):
        await probe_site(
            "https://shop.example",
            login_url="https://shop.example/login",
            username="bad",
            password="bad",
        )
