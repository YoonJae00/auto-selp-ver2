from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.workers.adapter import AutoAdapterRequest, AutoAdapterWorker, _classify_status


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    return QApplication.instance() or QApplication([])


async def _async_true(*a, **k):
    return True


async def _async_false(*a, **k):
    return False


class _FakePage:
    def __init__(self, state):
        self._state = state
        self.context = SimpleNamespace(storage_state=self._storage_state)

    async def _storage_state(self):
        return self._state


class _FakeEngine:
    def __init__(self, page):
        self._page = page

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def new_page(self):
        return self._page


def _wire_fakes(monkeypatch, probe_side_effect):
    """Patch the browser/login/probe surface so _orchestrate runs headless-free."""
    state = {"cookies": ["session"]}
    page = _FakePage(state)
    monkeypatch.setattr("app.crawlers.engine.create_engine", lambda **kw: _FakeEngine(page))
    monkeypatch.setattr("app.analyzer.login_helper._safe_goto", _async_true)
    monkeypatch.setattr("app.analyzer.login_helper._check_logout_indicators", _async_true)
    monkeypatch.setattr("app.analyzer.login_helper._has_visible_password_input", _async_false)
    monkeypatch.setattr("app.analyzer.site_probe.probe_site", probe_side_effect)

    async def fake_run(*a, **k):
        return SimpleNamespace(
            yaml_text="adapter: {}", mapping_hints=[], unresolved_fields=[], log=[], status_pair=None,
            dispositions={},
        )
    monkeypatch.setattr("app.analyzer.auto_adapter.run_auto_adapter", fake_run)
    return state


def _request() -> AutoAdapterRequest:
    return AutoAdapterRequest(
        main_url="https://x", supplier_name="몰",
        login_url="https://x/login", username="buyer", password="secret",
    )


async def _drive(worker, confirm_after_wait) -> object:
    worker._loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(worker._orchestrate())
    for _ in range(200):
        await asyncio.sleep(0.005)
        if worker._manual_login_event is not None:
            break
    else:  # pragma: no cover - the wait should always be reached
        task.cancel()
        raise AssertionError("worker never reached the manual-login wait")
    confirm_after_wait(worker)
    return await task


def test_manual_login_escape_resumes_and_reprobes(monkeypatch):
    calls: list[dict] = []
    ok_probe = SimpleNamespace(
        storage_state={"cookies": ["session"]}, detail_html="<html>",
        sample_products=[{"url": "https://x/p/1"}], needs_login=True,
    )

    async def fake_probe(*args, **kwargs):
        calls.append(kwargs)
        if kwargs.get("storage_state"):
            return ok_probe
        raise RuntimeError("자동 로그인 실패")

    _wire_fakes(monkeypatch, fake_probe)
    worker = AutoAdapterWorker(_request())
    login_seen = []
    worker.login_required.connect(lambda: login_seen.append(True))

    result = asyncio.run(_drive(worker, lambda w: w.confirmManualLogin()))

    assert login_seen == [True]                       # user was prompted exactly once
    assert len(calls) == 2                            # first (creds) failed, second (state) succeeded
    assert calls[0].get("storage_state") is None
    assert calls[1].get("storage_state") == {"cookies": ["session"]}
    assert calls[1].get("username") is None           # re-probe carries no credentials
    assert result["yaml"] == "adapter: {}"


def test_cancel_manual_login_aborts_with_error(monkeypatch):
    async def fake_probe(*args, **kwargs):
        raise RuntimeError("자동 로그인 실패")

    _wire_fakes(monkeypatch, fake_probe)
    worker = AutoAdapterWorker(_request())

    with pytest.raises(RuntimeError, match="취소"):
        asyncio.run(_drive(worker, lambda w: w.cancelManualLogin()))


def test_no_credentials_reraises_without_prompt(monkeypatch):
    async def fake_probe(*args, **kwargs):
        raise RuntimeError("사이트 분석 실패")

    _wire_fakes(monkeypatch, fake_probe)
    req = AutoAdapterRequest(main_url="https://x", supplier_name="몰")  # no login info
    worker = AutoAdapterWorker(req)
    prompted = []
    worker.login_required.connect(lambda: prompted.append(True))

    with pytest.raises(RuntimeError, match="사이트 분석 실패"):
        asyncio.run(worker._orchestrate())
    assert prompted == []


# ── _classify_status: '품절' 텍스트 오탐 방지 ───────────────────────────────
def test_classify_status_maxq_zero_is_sold_out():
    assert _classify_status({"maxq_value": "0", "has_buy_button": True, "explicit_soldout": []}) == "sold_out"


def test_classify_status_explicit_without_buy_button_is_sold_out():
    snap = {"maxq_value": "", "explicit_soldout": [{"text": "품절"}], "has_buy_button": False}
    assert _classify_status(snap) == "sold_out"


def test_classify_status_explicit_with_buy_button_is_unknown():
    # itopic 오탐 케이스: 페이지 어딘가 '품절' 텍스트 + 구매 버튼 + maxq=2147483647
    snap = {"maxq_value": "2147483647", "explicit_soldout": [{"text": "품절"}], "has_buy_button": True}
    assert _classify_status(snap) == "unknown"


def test_classify_status_buy_button_only_is_available():
    snap = {"maxq_value": "2147483647", "explicit_soldout": [], "has_buy_button": True}
    assert _classify_status(snap) == "available"


# ── soldout_url 직접 입력: 자동 탐색 건너뛰고 고정 쌍 사용 ────────────────────
def _wire_status_pair(monkeypatch, snapshots: dict[str, dict]):
    """create_engine + SoldoutCompareWorker._snapshot 를 패치하고 스냅샷 호출 URL을 기록."""
    from app.workers import adapter as adapter_mod

    page = _FakePage({"cookies": []})
    page.close = _async_true  # _dep_find_status_pair 가 page.close() 호출
    monkeypatch.setattr("app.crawlers.engine.create_engine", lambda **kw: _FakeEngine(page))
    calls: list[str] = []

    async def _fake_snapshot(self, page_, url, reduce_html):
        calls.append(url)
        return snapshots.get(url, {"maxq_value": "", "explicit_soldout": [], "has_buy_button": True})

    monkeypatch.setattr(adapter_mod.SoldoutCompareWorker, "_snapshot", _fake_snapshot)
    return calls


def test_soldout_url_fixes_pair_and_skips_auto_scan(monkeypatch):
    calls = _wire_status_pair(monkeypatch, {
        "http://s/soldout": {"maxq_value": "0", "explicit_soldout": [], "has_buy_button": False},
    })
    worker = AutoAdapterWorker(AutoAdapterRequest(
        main_url="http://s", supplier_name="s",
        detail_url="http://s/detail", soldout_url="http://s/soldout",
    ))
    pair = asyncio.run(worker._dep_find_status_pair(["http://s/a", "http://s/b"]))
    assert pair == ("http://s/detail", "http://s/soldout")
    # 자동 스캔 없이 품절 URL 한 번만 스냅샷 (검증용).
    assert calls == ["http://s/soldout"]


def test_no_soldout_url_runs_auto_scan(monkeypatch):
    calls = _wire_status_pair(monkeypatch, {
        "http://s/a": {"maxq_value": "", "explicit_soldout": [], "has_buy_button": True},
        "http://s/b": {"maxq_value": "0", "explicit_soldout": [], "has_buy_button": False},
    })
    worker = AutoAdapterWorker(AutoAdapterRequest(main_url="http://s", supplier_name="s"))
    pair = asyncio.run(worker._dep_find_status_pair(["http://s/a", "http://s/b"]))
    assert pair == ("http://s/a", "http://s/b")
    assert calls == ["http://s/a", "http://s/b"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
