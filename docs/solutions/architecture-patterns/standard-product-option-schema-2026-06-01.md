---
title: Standard Product Option Schema Across Uploads And Marketplace Drafts
module: wholesale-and-marketplace-options
date: 2026-06-01
category: docs/solutions/architecture-patterns
problem_type: architecture_pattern
component: service_object
severity: medium
applies_when:
  - "Supplier spreadsheets encode product options with different separators, row shapes, or image columns"
  - "Marketplace drafts need option-level images, SKU codes, prices, stock, and status"
  - "Legacy option parsing must stay compatible while a richer standard option schema is introduced"
tags:
  - "wholesale-upload"
  - "standard-options"
  - "marketplace-drafts"
  - "smartstore"
  - "coupang"
  - "option-images"
related_components:
  - "services/processor/utils/wholesale_upload.py"
  - "services/processor/models.py"
  - "services/processor/main.py"
  - "services/processor/schemas.py"
  - "services/marketplace/adapters"
  - "frontend/src/app/(ai-mall)/upload/page.tsx"
  - "frontend/src/app/(ai-mall)/products/page.tsx"
---

# Standard Product Option Schema Across Uploads And Marketplace Drafts

## Context

Wholesale suppliers do not share one product ledger format. One supplier may provide comma-separated options, another may use colon-separated text, and another may use one row per option. Option images, option prices, and option status can also live in different columns.

The stable boundary should be Auto-Selp's internal product schema, not the supplier file. This implementation introduced a compatibility-phase `standard_options` JSON shape while preserving the legacy `option_variants` field.

Related prior docs:

- `docs/solutions/architecture-patterns/wholesale-management-smart-upsert.md`
- `docs/solutions/database-issues/wholesale-option-price-overflow-2026-05-21.md`
- `docs/solutions/ui-bugs/wholesale-excel-upload-preview-2026-05-31.md`

## Guidance

Normalize supplier options into a complete option record before persisting or generating marketplace drafts. A valid standard option row includes product linkage, option group/value fields, option SKU, supply price, derived price delta, stock/status fields, image fields, display order, and raw metadata.

The parser now emits `standard_options` alongside legacy `option_variants`:

```python
"standard_options": standard_options
```

Invalid option sets must not partially persist. If legacy option parsing rejects the option set due to count mismatch or invalid prices, suppress `standard_options` too:

```python
standard_options = (
    []
    if option_result["warnings"]
    else build_standard_options(...)
)
```

This prevents marketplace adapters from consuming richer-looking but incomplete option data.

Marketplace adapters should prefer `standard_options` when present, while keeping the legacy `options` path as a fallback:

```python
standard_options = self._extract_standard_options(source_snapshot)
options = standard_options or self._extract_options(source_snapshot)
```

For SmartStore, map standard options into `optionCombinationGroupNames` and `optionCombinations`. For Coupang, map each standard option to one `items[]` entry, including option-level images, attributes, external SKU, and stock where present.

## Why This Matters

If the upload parser and marketplace adapters do not share the same option contract, data can look available in product management but silently disappear at draft generation time. The biggest failure mode is partial option data: a parser warning may clear legacy `option_variants`, but a separately parsed `standard_options` list can still leak malformed option rows downstream.

Keeping the same accept/reject boundary for both option shapes makes the compatibility phase safe. It also lets product management and marketplace generation start using option images and structured option groups before a dedicated `product_options` SQL table exists.

## Implementation Pitfalls Found During Review

The first standard option implementation had three important gaps:

1. The standard option row was initially incomplete. It needed supplier identity, option type, all group/value slots, sale price, stock quantity, option status, extra images, display position, and raw option text so adapters could consume one stable shape instead of inferring missing fields later.

2. Price parsing must stay identical to legacy parsing. A case like `대(8P),소(32P)` with prices `740,740` can confuse delimiter-aware parsing, so `standard_options` uses the same simple split fallback as `option_variants` when token counts otherwise differ.

3. A legacy option warning must suppress `standard_options`. Count mismatches and invalid option prices mean the option set is not trustworthy. Persisting standard options in that state creates malformed marketplace draft input even though legacy options were correctly cleared.

## When to Apply

Use this pattern when adding any new supplier import format, crawler output, or marketplace option export:

- Parse supplier-specific option text into the standard option shape.
- Preserve raw source text in `raw_option_text` and `raw_option_metadata`.
- Keep `option_supply_price` as the source of truth.
- Derive `option_price_delta` from product base supply price.
- Suppress both legacy and standard option outputs when option validation fails.
- Add adapter tests that prove `standard_options` reaches marketplace payloads.

## Examples

Regression tests should cover valid repeated unformatted option prices:

```python
parsed = parse_wholesale_row(row, mapping)
standard_options = parsed["product_data"]["standard_options"]

assert [option["option_supply_price"] for option in standard_options] == [740, 740]
assert [option["option_price_delta"] for option in standard_options] == [0, 0]
```

They should also cover invalid option sets:

```python
assert parsed["product_data"]["option_variants"] == []
assert parsed["product_data"]["standard_options"] == []
assert parsed["warnings"][0]["field"] == "option_variants"
```

Marketplace adapter tests should prove the new standard schema is not merely exposed in snapshots but actually consumed:

```python
option_info = result.generated_payload["originProduct"]["detailAttribute"]["optionInfo"]

assert option_info["optionCombinationGroupNames"] == ["색상", "사이즈"]
assert option_info["optionCombinations"][0]["sellerManagerCode"] == "P-100-1"
```

For Coupang:

```python
first_item = result.generated_payload["items"][0]

assert first_item["itemName"] == "블랙 / L"
assert first_item["externalVendorSku"] == "P-100-1"
assert first_item["images"][0]["vendorPath"] == "https://img.example/black-l.jpg"
```

## Prevention Checklist

- Do not expose upload mapper fields that the backend parser ignores.
- Do not let `standard_options` parse prices differently from `option_variants`.
- Do not persist partial standard option rows when legacy parsing emits warnings.
- Do not stop at processor snapshots; add marketplace adapter tests for any new snapshot contract.
- Add regression tests for every review-discovered mismatch between `option_variants` and `standard_options`, especially parser warning cases and repeated unformatted option prices.
- Keep legacy `options`/`option_variants` fallback until all downstream consumers are migrated.
