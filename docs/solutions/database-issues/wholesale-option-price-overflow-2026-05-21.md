---
title: Wholesale Option Price Parsing Overflow During DB Import
date: 2026-05-21
category: database-issues
module: wholesale-product-import
problem_type: database_issue
component: database
symptoms:
  - "DB-only wholesale upload returned a generic Failed to fetch message in the browser"
  - "Processor logs showed asyncpg.exceptions.DataError: value out of int32 range"
  - "Repeated option prices such as 740,740 were parsed into oversized integer values"
root_cause: logic_error
resolution_type: code_fix
severity: high
related_components:
  - service_object
  - frontend_stimulus
  - background_job
tags:
  - wholesale-import
  - price-parsing
  - options
  - asyncpg
  - db-import
---

# Wholesale Option Price Parsing Overflow During DB Import

## Problem
After separating wholesale upload from product processing, the upload flow successfully parsed the Excel file but failed when saving imported products to PostgreSQL. The browser surfaced a generic `Failed to fetch`/failed save experience, while the backend returned a 500 during `/api/processor/process-db`.

## Symptoms
- The `/upload` page could read the Excel file and show mapping state, but the DB save step failed.
- Gateway logs showed `POST /api/processor/upload` returning 200, followed by `POST /api/processor/process-db` returning 500.
- Processor logs showed `asyncpg.exceptions.DataError: invalid input for query argument ... value out of int32 range`.
- The bad value came from price fields like `740,740`, which represented two option prices but were merged into a huge integer.

## What Didn't Work
- Restarting Docker or rebuilding the frontend did not address the failure because the frontend request path was already reaching the backend.
- Looking only at the browser error was misleading: `Failed to fetch` hid the real failure in the processor logs.
- Treating every comma followed by three digits as a thousands separator was too broad for wholesale supplier spreadsheets, where comma-separated option prices can also be unformatted repeated prices.

## Solution
Fix the supplier price parser so option context controls comma handling:

1. If option names exist and simple comma-split price tokens match the option count, prefer those tokens over thousands-separator inference.
2. Keep formatted single prices like `2,640원` working.
3. Refuse oversized parsed integers before they reach PostgreSQL `INTEGER` columns.
4. Add regression tests for repeated unformatted option prices.

Key parser behavior:

```python
def parse_int_price(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None

    if re.search(r"\d[^/]*\/[^/]*\d", text):
        return None

    normalized = re.sub(r"[^0-9.]", "", text)
    if not normalized:
        return None

    try:
        parsed = int(float(normalized))
    except ValueError:
        return None
    if parsed > 2_147_483_647:
        return None
    return parsed
```

```python
def parse_option_variants(option_values_raw: Any, price_wholesale_raw: Any) -> dict[str, Any]:
    option_names = split_csv_text(option_values_raw)
    price_tokens = split_option_price_text(price_wholesale_raw) if option_names else []
    simple_price_tokens = split_csv_text(price_wholesale_raw) if option_names else []
    if (
        option_names
        and len(price_tokens) != len(option_names)
        and len(simple_price_tokens) == len(option_names)
    ):
        price_tokens = simple_price_tokens

    parsed_prices = [parse_int_price(token) for token in price_tokens]
    representative_price = parsed_prices[0] if parsed_prices else parse_int_price(price_wholesale_raw)
```

Regression coverage:

```python
def test_parse_option_variants_pairs_repeated_unformatted_prices():
    result = parse_option_variants("대(8P),소(32P)", "740,740")
    assert result["price_wholesale"] == 740
    assert result["option_variants"] == [
        {"name": "대(8P)", "price_wholesale": 740, "position": 1},
        {"name": "소(32P)", "price_wholesale": 740, "position": 2},
    ]
    assert result["warnings"] == []
```

## Why This Works
The ambiguity only exists because commas can mean two different things in supplier sheets:

- `2,640원` means a single formatted price.
- `740,740` can mean two option prices when there are two option names.

The parser now uses the surrounding option data as disambiguating context. When option count and simple comma-split price count match, the supplier intended multiple option prices. When there is no option context, the previous single formatted price behavior remains intact. The integer upper bound guard prevents malformed price strings from causing database write failures.

## Prevention
- Always inspect gateway and processor logs for upload failures; browser `Failed to fetch` can mask a backend 500.
- Add parser tests for every supplier price shape seen in real spreadsheets, especially repeated prices and option-count mismatches.
- Keep raw supplier price text (`price_wholesale_raw`) alongside parsed prices so bad parsing can be diagnosed without re-uploading the file.
- For DB import pipelines, validate values against storage constraints before committing large batches.

## Related Issues
- `docs/solutions/architecture-patterns/wholesale-management-smart-upsert.md` documents the broader wholesale import and smart upsert architecture.
- This fix is narrower: it protects the DB import path from malformed or ambiguous supplier option price strings.
