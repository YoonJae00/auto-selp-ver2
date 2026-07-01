from __future__ import annotations

import os

import pytest

from app.analyzer.element_picker import PickedElement, choose_best_selector, resolve_login_selectors, sanitize_attrs, sanitize_html_preview, sanitize_value, suggest_defaults_for_field


def test_sanitize_value_strips_control_backticks_and_truncates() -> None:
    raw = "```hello`\x00\n" + "a" * 500
    cleaned = sanitize_value(raw, 20)
    assert "`" not in cleaned
    assert "\x00" not in cleaned
    assert len(cleaned) == 20


def test_sanitize_attrs_allowlist_and_truncates() -> None:
    attrs = sanitize_attrs({"href": "/p/1", "onclick": "evil()", "value": "ok", "src": "x" * 500})
    assert attrs["href"] == "/p/1"
    assert attrs["value"] == "ok"
    assert "onclick" not in attrs
    assert len(attrs["src"]) == 300


def test_sensitive_input_values_are_not_returned() -> None:
    assert "value" not in sanitize_attrs({"type": "hidden", "name": "csrf_token", "value": "abc123"})
    assert "value" not in sanitize_attrs({"type": "password", "id": "login_password", "value": "secret"})
    assert sanitize_attrs({"type": "text", "name": "quantity", "value": "10"})["value"] == "10"


def test_html_preview_is_aggressively_sanitized() -> None:
    html = '<div><script>x</script><input type="hidden" name="token" value="abc"><b>상품</b></div>'
    cleaned = sanitize_html_preview(html)
    assert "<input" not in cleaned
    assert "<script" not in cleaned
    assert "abc" not in cleaned
    assert "상품" in cleaned


def test_choose_best_selector_prefers_unique_then_small_count() -> None:
    assert choose_best_selector([".many", "#one"], {".many": 12, "#one": 1}) == "#one"
    assert choose_best_selector([".few", ".many"], {".few": 3, ".many": 12}) == ".few"


def test_suggest_defaults_for_field() -> None:
    picked = PickedElement(
        url="https://example.com",
        selector="img.main",
        text="상품",
        html_preview="<b>상품</b>",
        attribute_values={"src": "/a.jpg", "href": "/p/1"},
    )
    assert suggest_defaults_for_field("adapter.product.main_image_url", picked)["attribute"] == "src"
    assert suggest_defaults_for_field("adapter.product.extra_image_urls", picked)["multiple"] is True
    assert suggest_defaults_for_field("adapter.listing.product_link", picked)["attribute"] == "href"
    assert suggest_defaults_for_field("adapter.product.detail_content", picked)["multiple"] is True
    assert suggest_defaults_for_field("adapter.product.detail_content", picked)["attribute"] == "src"
    assert suggest_defaults_for_field("adapter.product.detail_content", picked)["html"] is False
    assert suggest_defaults_for_field("adapter.product.supply_price", picked)["transform"] == "extract_number"
    assert suggest_defaults_for_field("adapter.options.groups.0.values_selector", picked)["observed_value"] == "상품"


def test_all_products_url_default_returns_href() -> None:
    picked = PickedElement(
        url="https://example.com",
        selector="a.all-products",
        text="전체상품",
        attribute_values={"href": "https://example.com/all"},
    )
    result = suggest_defaults_for_field("adapter.categories.all_products.url", picked)
    assert result["attribute"] == "href"
    assert result["observed_value"] == "https://example.com/all"
    assert result["selector"] == "https://example.com/all"


def test_detail_observed_value_does_not_use_html_preview() -> None:
    picked = PickedElement(url="https://example.com", selector=".detail", text="", html_preview="hidden html")
    assert suggest_defaults_for_field("adapter.product.detail_content", picked)["observed_value"] == ""


def test_adapter_builder_mapping_table_has_5_columns() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.tabs.adapter_builder_tab import AdapterBuilderTab
    except Exception as exc:  # pragma: no cover - dependency may be absent outside venv
        pytest.skip(f"PySide6 unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    tab = AdapterBuilderTab()
    assert hasattr(tab, "mapping_table")
    assert tab.mapping_table.columnCount() == 5
    headers = [tab.mapping_table.horizontalHeaderItem(i).text() for i in range(5)]
    assert "수정" in headers

    # Probe card has field dropdown + picker button
    assert hasattr(tab, "probe_field_combo")
    assert tab.probe_field_combo.count() > 5
    assert hasattr(tab, "probe_pick_btn")
    assert tab.probe_pick_btn.text() == "브라우저에서 선택"
    # All-products button exists
    assert hasattr(tab, "all_products_pick_btn")
    assert tab.all_products_pick_btn.text() == "브라우저에서 선택"
    tab.deleteLater()


def test_adapter_builder_picker_creates_hint_and_updates_modified_label() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.tabs.adapter_builder_tab import AdapterBuilderTab
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PySide6 unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    tab = AdapterBuilderTab()
    assert len(tab._mapping_hints) == 0
    assert "없음" in tab.modified_fields_label.text()

    picked = PickedElement(
        url="https://example.com/p/1",
        selector=".product-name",
        text="좋은상품",
        attribute_values={},
    )
    tab._on_picker_finished(picked, "adapter.product.raw_product_name")
    assert len(tab._mapping_hints) == 1
    assert tab._mapping_hints[0].field_path == "adapter.product.raw_product_name"
    assert tab._mapping_hints[0].locked is True
    assert "상품명" in tab.modified_fields_label.text()
    tab.deleteLater()


def test_adapter_builder_clear_hints_resets_modified_label() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.tabs.adapter_builder_tab import AdapterBuilderTab
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PySide6 unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    tab = AdapterBuilderTab()
    picked = PickedElement(url="https://example.com/p/1", selector=".name", text="상품", attribute_values={})
    tab._on_picker_finished(picked, "adapter.product.raw_product_name")
    assert len(tab._mapping_hints) == 1

    tab._clear_mapping_hints()
    assert len(tab._mapping_hints) == 0
    assert "없음" in tab.modified_fields_label.text()
    assert not tab.reset_modified_btn.isEnabled()
    tab.deleteLater()


def test_resolve_login_selectors_prefers_config_over_heuristics() -> None:
    # Provide explicit selectors
    cfg = {
        "id_selector": "input[name='memberId']",
        "password_selector": "input[name='userpw']",
        "submit_selector": "img[src*='login_btn']",
        "success_indicator": ".logout",
    }
    resolved = resolve_login_selectors(cfg)
    assert resolved["id_candidates"] == ["input[name='memberId']"]
    assert resolved["password_candidates"] == ["input[name='userpw']"]
    assert resolved["submit_candidates"] == ["img[src*='login_btn']"]
    assert resolved["success_indicator"] == ".logout"


def test_resolve_login_selectors_uses_heuristics_when_no_config() -> None:
    resolved = resolve_login_selectors(None)
    assert "input[name='id']" in resolved["id_candidates"]
    assert "input[type='password']" in resolved["password_candidates"]
    assert "input[type='image'][src*='login']" in resolved["submit_candidates"]
