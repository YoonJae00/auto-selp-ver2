from __future__ import annotations

import os

import pytest

from app.analyzer.validation_summary import build_validation_summary, get_save_gate_decision


def _entry(value: str, url: str = "https://example.com/p/1") -> dict:
    return {"url": url, "value": value, "ok": bool(value), "error": None}


def _raw(values: dict[str, list[str]]) -> dict[str, list[dict]]:
    return {field: [_entry(value, f"https://example.com/p/{idx}") for idx, value in enumerate(vals, 1)] for field, vals in values.items()}


def test_summary_passes_all_key_fields() -> None:
    summary = build_validation_summary(_raw({
        "raw_product_name": ["상품A", "상품B"],
        "supply_price": ["1,000", "2000"],
        "main_image_url": ["/a.jpg", "https://x/b.jpg"],
        "supplier_product_code": ["A1", "B2"],
    }))
    assert summary.can_save_cleanly
    assert summary.failed_key_fields == []


def test_product_code_is_required_even_when_supplier_product_id_exists() -> None:
    summary = build_validation_summary(_raw({
        "raw_product_name": ["상품A"],
        "supply_price": ["1000"],
        "main_image_url": ["/a.jpg"],
        "supplier_product_code": [""],
        "supplier_product_id": ["ID1"],
    }))
    assert "supplier_product_code" in summary.failed_key_fields


def test_two_of_three_passes_one_of_three_fails() -> None:
    passing = build_validation_summary(_raw({
        "raw_product_name": ["상품A", "상품B", ""],
        "supply_price": ["1000", "2000", "3000"],
        "main_image_url": ["/a.jpg", "/b.jpg", "/c.jpg"],
        "supplier_product_code": ["A", "B", "C"],
    }))
    failing = build_validation_summary(_raw({
        "raw_product_name": ["상품A", "", ""],
        "supply_price": ["1000", "2000", "3000"],
        "main_image_url": ["/a.jpg", "/b.jpg", "/c.jpg"],
        "supplier_product_code": ["A", "B", "C"],
    }))
    assert "raw_product_name" not in passing.failed_key_fields
    assert "raw_product_name" in failing.failed_key_fields


def test_no_raw_validation_save_warning_decision() -> None:
    decision = get_save_gate_decision(build_validation_summary(None), is_stale=False)
    assert decision.should_warn
    assert decision.reason == "missing"
    assert decision.allow_continue


def test_stale_validation_save_warning_decision() -> None:
    summary = build_validation_summary(_raw({
        "raw_product_name": ["상품A"], "supply_price": ["1000"], "main_image_url": ["/a.jpg"], "supplier_product_code": ["A"]
    }))
    decision = get_save_gate_decision(summary, is_stale=True)
    assert decision.should_warn
    assert decision.reason == "stale"


def test_failed_key_fields_warn_but_allow_continue() -> None:
    summary = build_validation_summary(_raw({
        "raw_product_name": [""], "supply_price": ["1000"], "main_image_url": ["/a.jpg"], "supplier_product_code": ["A"]
    }))
    decision = get_save_gate_decision(summary, is_stale=False)
    assert decision.should_warn
    assert decision.reason == "failed"
    assert decision.allow_continue
    assert decision.failed_fields == ["raw_product_name"]


def test_adapter_builder_validation_ui_smoke() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.tabs.adapter_builder_tab import AdapterBuilderTab
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PySide6 unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    tab = AdapterBuilderTab()
    assert hasattr(tab, "validation_status_label")
    tab._last_validation_summary = build_validation_summary(_raw({
        "raw_product_name": ["상품A"], "supply_price": ["1000"], "main_image_url": ["/a.jpg"], "supplier_product_code": ["A"]
    }))
    tab._render_validation_summary()
    assert "저장 가능" in tab.validation_status_label.text()
    tab.deleteLater()


def test_adapter_builder_records_tested_yaml_hash_not_current_editor() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.tabs.adapter_builder_tab import AdapterBuilderTab
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PySide6 unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    tab = AdapterBuilderTab()
    tested_yaml = "adapter:\n  name: old\n"
    current_yaml = "adapter:\n  name: new\n"
    tested_hash = tab._yaml_hash(tested_yaml)
    tab.yaml_edit.setPlainText(current_yaml)

    results = {
        "__raw_results__": _raw({
            "raw_product_name": ["상품A"],
            "supply_price": ["1000"],
            "main_image_url": ["/a.jpg"],
            "supplier_product_code": ["A"],
        })
    }
    tab._on_test_finished(results, tested_yaml_hash=tested_hash)

    assert tab._last_validation_yaml_hash == tested_hash
    assert tab._validation_stale is True
    tab.deleteLater()
