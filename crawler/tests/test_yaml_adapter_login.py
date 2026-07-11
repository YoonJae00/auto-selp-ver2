from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.crawlers.yaml_adapter as ya
from app.crawlers.yaml_adapter import YAMLAdapter

AUTO_ID = "input[type='text'], input[type='email'], input[name*='id'], input[name*='user'], input[name*='member']"
AUTO_PW = "input[type='password']"


class _El:
    async def fill(self, _v): ...
    async def click(self): ...
    async def press(self, _k): ...


class _Page:
    """present에 든 선택자만 요소가 존재하는 최소 가짜 페이지."""
    def __init__(self, present: set[str]) -> None:
        self.present = present

    async def goto(self, *a, **k): ...
    async def wait_for_timeout(self, *a): ...
    async def query_selector(self, selector):
        return _El() if selector in self.present else None


def _adapter(supplier_slug="key"):
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.supplier_name = "t"
    adapter.supplier_slug = supplier_slug
    adapter._login_failure_reason = ""
    adapter.adapter = SimpleNamespace(adapter=SimpleNamespace(login=SimpleNamespace(
        required=True, login_url="http://x/login",
        fields=SimpleNamespace(id="#login_id", password="#login_password"),
        submit="#login_btn", success_indicator="#ok", failure_indicator=None,
    )))
    return adapter


def test_login_reports_missing_credentials(monkeypatch):
    monkeypatch.setattr(ya, "load_supplier_credentials", lambda _k: None)
    adapter = _adapter()
    ok = asyncio.run(adapter._perform_login(_Page({"#login_id", "#login_password", "#login_btn", "#ok"})))
    assert ok is False
    assert "로그인 아이디/비밀번호가 없습니다" in adapter._login_failure_reason


def test_login_uses_configured_selectors_when_present(monkeypatch):
    monkeypatch.setattr(ya, "load_supplier_credentials", lambda _k: ("u", "p"))
    adapter = _adapter()
    ok = asyncio.run(adapter._perform_login(_Page({"#login_id", "#login_password", "#login_btn", "#ok"})))
    assert ok is True


def test_login_falls_back_to_autodetect_when_configured_selectors_wrong(monkeypatch):
    # mockmall 실제 케이스: 저장된 #login_id/#login_password가 페이지에 없고,
    # 실제 입력란은 자동 감지 선택자로만 잡힌다 → 폴백으로 로그인 성공해야 한다.
    monkeypatch.setattr(ya, "load_supplier_credentials", lambda _k: ("u", "p"))
    adapter = _adapter()
    present = {AUTO_ID, AUTO_PW, "button[type='submit']", "#ok"}
    ok = asyncio.run(adapter._perform_login(_Page(present)))
    assert ok is True
    assert adapter._login_failure_reason == ""


def test_login_reports_success_indicator_not_found(monkeypatch):
    monkeypatch.setattr(ya, "load_supplier_credentials", lambda _k: ("u", "p"))
    adapter = _adapter()
    # 입력·제출은 되지만 성공 지표(#ok)가 없음
    ok = asyncio.run(adapter._perform_login(_Page({"#login_id", "#login_password", "#login_btn"})))
    assert ok is False
    assert "성공을 확인하지 못했습니다" in adapter._login_failure_reason


def test_login_reports_inputs_not_found(monkeypatch):
    monkeypatch.setattr(ya, "load_supplier_credentials", lambda _k: ("u", "p"))
    adapter = _adapter()
    ok = asyncio.run(adapter._perform_login(_Page(set())))  # 아무 요소도 없음
    assert ok is False
    assert "로그인 입력란" in adapter._login_failure_reason
