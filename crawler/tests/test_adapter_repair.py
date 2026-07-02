from __future__ import annotations

from app.analyzer.adapter_generator import _apply_repaired_fields
from app.crawlers.registry import load_adapter_from_text

BASE_YAML = """
adapter:
  name: Test
  base_url: https://example.com
  product:
    raw_product_name:
      selector: .name
    supply_price:
      selector: .wrong-price
"""


def test_repair_replaces_only_returned_fields():
    # LLM found a better price selector and a new name-code selector; name is untouched.
    repaired = {
        "supply_price": {"selector": ".price", "attribute": "", "transform": "extract_number"},
        "supplier_product_code": {"selector": "#code"},
    }
    out = _apply_repaired_fields(BASE_YAML, repaired)
    product = load_adapter_from_text(out).adapter.product
    assert product.supply_price.selector == ".price"
    assert product.supply_price.transform == "extract_number"
    assert product.supplier_product_code.selector == "#code"
    # Untouched field preserved.
    assert product.raw_product_name.selector == ".name"


def test_repair_ignores_empty_and_unknown_fields():
    out = _apply_repaired_fields(BASE_YAML, {
        "supply_price": {"selector": ""},        # empty → skip, keep original
        "bogus_field": {"selector": ".x"},       # not repairable → skip
    })
    assert out == BASE_YAML  # nothing changed


def test_repair_returns_original_on_no_valid_dict():
    assert _apply_repaired_fields(BASE_YAML, {}) == BASE_YAML


if __name__ == "__main__":
    test_repair_replaces_only_returned_fields()
    test_repair_ignores_empty_and_unknown_fields()
    test_repair_returns_original_on_no_valid_dict()
    print("ok")
