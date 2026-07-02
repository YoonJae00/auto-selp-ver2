from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.analyzer.element_picker import INSTRUCTION_OVERLAY_SCRIPT, MAPPING_PREVIEW_SCRIPT, PICKER_INSTALL_SCRIPT
from app.analyzer.picker_session import PickerSession


def test_overlay_script_targets_body_and_sets_cancel_handler():
    """INSTRUCTION_OVERLAY_SCRIPT builds a fixed banner with a cancel button."""
    src = INSTRUCTION_OVERLAY_SCRIPT
    assert "__picker-overlay" in src
    assert "position:fixed" in src
    assert "top:0" in src
    assert "z-index:2147483647" in src
    assert "__pickerCancelled" in src
    assert "__pickerCancelPicker" in src
    assert "취소" in src


def test_picker_install_script_has_cancel_check_and_tooltip():
    """PICKER_INSTALL_SCRIPT checks the cancel flag and renders a hover tooltip."""
    src = PICKER_INSTALL_SCRIPT
    assert "__pickerCancelled" in src
    assert "__picker-tip" in src
    assert "클릭해서 지정" in src
    assert "__picker-confirm" in src
    assert "이 요소가 맞나요?" in src
    assert "finish(null)" in src
    assert "finish(picked)" in src


def test_picker_install_script_registers_listeners_once_and_never_tears_down():
    """Listeners are installed once (idempotent) and stay attached forever, gated by
    window.__pickerArmed instead of add/remove — this is what lets us pre-register
    them via add_init_script and win the capture-phase race against page scripts
    that register their own window/document click blockers on load."""
    src = PICKER_INSTALL_SCRIPT
    assert "if (window.__pickerInstalled) return;" in src
    assert "document.addEventListener('mousedown', click, true);" in src
    assert "window.addEventListener('click', click, true);" in src
    assert "window.addEventListener('mousedown', click, true);" in src
    assert "removeEventListener" not in src
    assert "if (!window.__pickerArmed) return;" in src


def test_picker_install_script_avoids_pollutable_globals():
    """Old malls (e.g. itopic/MakeShop) ship a broken Array.from polyfill that returns []
    for iterables, which silently made every element yield zero selector candidates
    (`if (!cand.length) return`) so clicks did nothing. The selector-building code must
    not rely on Array.from / Set — it uses pollution-proof _toArr/_uniq helpers instead."""
    src = PICKER_INSTALL_SCRIPT
    assert "function _toArr(" in src
    assert "function _uniq(" in src
    # No page-overridable Array.from / Set in the picker logic (comments excluded).
    code = "\n".join(line for line in src.splitlines() if "//" not in line)
    assert "Array.from" not in code
    assert "new Set(" not in code


def test_mapping_preview_script_avoids_page_pollutable_for_each():
    src = MAPPING_PREVIEW_SCRIPT
    code = "\n".join(line for line in src.splitlines() if "//" not in line)
    assert ".forEach" not in code
    assert "for (let i = 0;" in code
    assert "continue;" in code


def test_picker_confirm_clicks_are_not_captured_before_button_handlers():
    """Confirm buttons must receive clicks before the page-click blocker runs."""
    src = PICKER_INSTALL_SCRIPT
    click_start = src.index("function click(e)")
    ui_guard = src.index("if (isPickerUi(el)) return;", click_start)
    prevent_default = src.index("e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();", ui_guard)
    assert ui_guard < prevent_default
    assert "no.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); removeConfirm(); };" in src
    assert "yes.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); finish(picked); };" in src


def test_overlay_cancel_resolves_without_second_click():
    """The top overlay cancel button calls the picker cancel resolver directly."""
    assert "typeof window.__pickerCancelPicker === 'function'" in INSTRUCTION_OVERLAY_SCRIPT
    assert "window.__pickerCancelPicker();" in INSTRUCTION_OVERLAY_SCRIPT


def test_confirm_no_only_dismisses_box_and_keeps_picker_armed():
    """Browser-side No must only remove the confirm box (not cancel the session),
    so the user can immediately pick a different element without relaunching the browser."""
    src = PICKER_INSTALL_SCRIPT
    assert "no.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); removeConfirm(); };" in src
    # No must NOT tear the session down.
    assert "no.onclick = (ev) => { ev.preventDefault(); ev.stopPropagation(); cancelPicker(); };" not in src


def test_pick_injects_overlay_then_runs_picker():
    """pick() injects the overlay, installs+arms the picker listeners, then polls
    for a result — the listeners themselves are installed once via add_init_script
    (see PickerSession.open), so _evaluate_picker only needs to (re-)install
    defensively, arm, and poll."""
    session = PickerSession()
    calls = []
    picked_payload = {
        "url": "https://example.com/p/1",
        "selectorCandidates": ["a.link"],
        "matchCounts": {"a.link": 1},
        "text": "상품",
        "htmlPreview": "",
        "attributeValues": {"href": "/p/1"},
        "tagName": "a",
        "elementId": "",
        "classes": ["link"],
    }
    state = {"armed": False}

    def fake_evaluate(script, *args):
        calls.append((script, args))
        if script is INSTRUCTION_OVERLAY_SCRIPT:
            return None
        if script is PICKER_INSTALL_SCRIPT:
            return None
        if "__pickerArm()" in script:
            state["armed"] = True
            return None
        if "window.__pickerDone ?" in script:
            return {"done": True, "result": picked_payload} if state["armed"] else {"done": False}
        return None  # cancel/cleanup scripts

    fake_page = MagicMock()
    fake_page.evaluate.side_effect = fake_evaluate
    fake_page.frames = [fake_page]
    fake_page.wait_for_timeout.return_value = None

    session._ensure_page = lambda: fake_page
    session._current_url = "https://example.com"

    result = session.pick("https://example.com", "전체상품 링크", "사이트의 '전체상품' 메뉴를 클릭하세요.")

    scripts = [c[0] for c in calls]
    assert INSTRUCTION_OVERLAY_SCRIPT in scripts
    assert PICKER_INSTALL_SCRIPT in scripts
    arm_index = next(i for i, s in enumerate(scripts) if "__pickerArm()" in s)
    # Overlay must be injected before the picker is armed.
    assert scripts.index(INSTRUCTION_OVERLAY_SCRIPT) < arm_index
    # Result is a PickedElement with the expected fields.
    assert result.selector == "a.link"
    assert result.attribute_values["href"] == "/p/1"


def test_pick_raises_on_cancel():
    """When the picker resolves with a null result (cancel clicked), pick() raises RuntimeError."""
    session = PickerSession()

    def fake_evaluate(script, *args):
        if "window.__pickerDone ?" in script:
            return {"done": True, "result": None}
        return None

    fake_page = MagicMock()
    fake_page.evaluate.side_effect = fake_evaluate
    fake_page.frames = [fake_page]
    fake_page.wait_for_timeout.return_value = None

    session._ensure_page = lambda: fake_page
    session._current_url = "https://example.com"

    with pytest.raises(RuntimeError, match="cancelled"):
        session.pick("https://example.com", "전체상품 링크", "hint")


def test_pick_skips_overlay_when_no_label_or_hint():
    """If both field_label and field_hint are empty, overlay injection is skipped."""
    session = PickerSession()
    calls = []
    picked_payload = {
        "url": "https://example.com/p/1",
        "selectorCandidates": ["a"],
        "matchCounts": {"a": 1},
        "text": "",
        "htmlPreview": "",
        "attributeValues": {},
        "tagName": "a",
        "elementId": "",
        "classes": [],
    }

    def fake_evaluate(script, *args):
        calls.append((script, args))
        if "window.__pickerDone ?" in script:
            return {"done": True, "result": picked_payload}
        return None

    fake_page = MagicMock()
    fake_page.evaluate.side_effect = fake_evaluate
    fake_page.frames = [fake_page]
    fake_page.wait_for_timeout.return_value = None

    session._ensure_page = lambda: fake_page
    session._current_url = "https://example.com"

    session.pick("https://example.com", "", "")

    # Overlay script must not have been called.
    assert INSTRUCTION_OVERLAY_SCRIPT not in [c[0] for c in calls]


def test_pick_can_receive_result_from_child_frame():
    """Product detail fields can live inside iframes; install+arm the picker there too."""
    session = PickerSession()
    payload = {
        "url": "https://example.com/frame",
        "selectorCandidates": ["span.name"],
        "matchCounts": {"span.name": 1},
        "text": "상품명",
        "htmlPreview": "",
        "attributeValues": {},
        "tagName": "span",
        "elementId": "",
        "classes": ["name"],
    }

    class FakeFrame:
        def __init__(self, result=None):
            self.result = result
            self.armed = False
            self.cleaned = False

        def evaluate(self, script):
            if "__pickerArm()" in script:
                self.armed = True
                return None
            if "window.__pickerDone ?" in script:
                return {"done": self.armed and self.result is not None, "result": self.result}
            if "__pickerCancelPicker" in script:
                self.cleaned = True
                return None
            return None  # install script

    main = FakeFrame()
    child = FakeFrame(payload)
    fake_page = MagicMock()
    fake_page.frames = [main, child]
    fake_page.wait_for_timeout.return_value = None

    raw = session._evaluate_picker(fake_page, 1000)

    assert raw == payload
    assert main.armed is True
    assert child.armed is True
    assert main.cleaned is True
    assert child.cleaned is True


def test_session_is_not_open_when_context_pages_are_closed():
    session = PickerSession()
    page = MagicMock()
    page.is_closed.return_value = False
    closed_page = MagicMock()
    closed_page.is_closed.return_value = True
    browser = MagicMock()
    browser.pages = [closed_page]
    session._page = page
    session._browser = browser

    assert session.is_open is False


def test_preview_mapping_extracts_sample_values(monkeypatch):
    import app.analyzer.picker_session as picker_session

    class FakeElement:
        def __init__(self, text="", html="", attrs=None):
            self.text = text
            self.html = html
            self.attrs = attrs or {}

        def inner_text(self):
            return self.text

        def inner_html(self):
            return self.html

        def get_attribute(self, name):
            return self.attrs.get(name)

    class FakePage:
        url = "https://shop.example/p/1?goodsno=12345&cate=001"

        def __init__(self):
            self.elements = {
                ".name": [FakeElement("상품명")],
                ".main": [FakeElement(attrs={"src": "https://img.example/main.jpg"})],
                ".lazy": [FakeElement(attrs={"data-src": "https://img.example/lazy.jpg"})],
                ".thumb": [FakeElement("A"), FakeElement("B")],
            }
            self.overlay_fields = None

        def query_selector(self, selector):
            items = self.elements.get(selector, [])
            return items[0] if items else None

        def query_selector_all(self, selector):
            return list(self.elements.get(selector, []))

        def evaluate(self, script, fields):
            self.overlay_fields = fields

    monkeypatch.setattr(picker_session, "_safe_goto", lambda page, url: True)
    session = PickerSession()
    page = FakePage()
    session._ensure_page = lambda: page

    result = session.preview_mapping("https://shop.example/p/1", [
        {"key": "name", "label": "상품명", "selector": ".name", "transform": "strip"},
        {"key": "image", "label": "대표 이미지", "selector": ".main", "attribute": "src"},
        {"key": "lazy", "label": "지연 이미지", "selector": ".lazy", "attribute": "src", "fallback_attribute": "data-src"},
        {"key": "multi", "label": "여러 값", "selector": ".thumb", "multiple": True},
        {"key": "param", "label": "상품코드", "fallback_from": "url", "url_param": "goodsno"},
        {"key": "pattern", "label": "카테고리", "fallback_from": "url", "url_pattern": r"cate=(\d+)"},
    ])

    assert result["values"] == {
        "name": "상품명",
        "image": "https://img.example/main.jpg",
        "lazy": "https://img.example/lazy.jpg",
        "multi": "2개 · A, B",
        "param": "12345",
        "pattern": "001",
    }
    assert set(result["found"]) == set(result["values"])
    assert result["missing"] == []
    assert page.overlay_fields is not None


def test_picker_install_script_cancels_on_overlay_click_and_ignores_non_elements():
    """PICKER_INSTALL_SCRIPT must cancel when the overlay is clicked and ignore non-element targets."""
    src = PICKER_INSTALL_SCRIPT
    # Cancel path: clicking the instruction overlay (incl. cancel button) cancels the pick.
    assert "__picker-overlay" in src
    assert "cancelPicker();" in src
    # Non-element targets (document, nodeType !== 1) are ignored, keeping the picker alive.
    assert "nodeType !== 1" in src
    # Empty-candidate clicks are ignored rather than resolving with an empty selector.
    assert "if (!cand.length) return" in src
