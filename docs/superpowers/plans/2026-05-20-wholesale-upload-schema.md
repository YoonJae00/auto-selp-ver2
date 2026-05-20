# Wholesale Upload Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the wholesale upload mapper with the approved supplier-oriented schema and parse option/price/image fields into normalized product data.

**Architecture:** Keep the existing `/process-db` and `WholesaleSite.column_mapping` flow, but move supplier row parsing into a focused utility module so parsing can be tested independently. Extend `Product` with supplier ID, raw option/price values, parsed option variants, and supplier registration date while preserving full Excel rows in `raw_metadata`.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL JSON columns, Pandas Excel parsing, Pytest, Next.js React/TypeScript.

---

## File Structure

- Create `services/processor/utils/wholesale_upload.py`: pure parsing helpers for mapped values, integers, options/prices, image slot aggregation, required row warnings, and normalized row payloads.
- Create `services/processor/tests/test_wholesale_upload.py`: focused unit tests for the parser without Celery or FastAPI.
- Modify `services/processor/models.py`: add first-class product columns for supplier ID, raw option/price values, parsed option variants, and supplier registration date.
- Modify `services/processor/schemas.py`: expose the new fields through `ProductResponse`.
- Modify `services/processor/init_prompts.py`: add `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements for existing databases.
- Modify `services/processor/tests/test_wholesale.py`: update test fixture migrations and smart-upsert assertions for the new fields.
- Modify `services/processor/main.py`: replace inline wholesale extraction in `/process-db` with the parser utility and keep smart-upsert behavior.
- Modify `frontend/src/app/(ai-mall)/upload/page.tsx`: replace current 10 `SYSTEM_FIELDS` with the 16 approved mapping targets and fallbacks.

---

### Task 1: Add Wholesale Upload Parser Tests

**Files:**
- Create: `services/processor/tests/test_wholesale_upload.py`
- Create later in Task 2: `services/processor/utils/wholesale_upload.py`

- [ ] **Step 1: Write failing parser tests**

Create `services/processor/tests/test_wholesale_upload.py`:

```python
import pandas as pd

from utils.wholesale_upload import (
    REQUIRED_WHOLESALE_FIELDS,
    build_images_list,
    parse_int_price,
    parse_option_variants,
    parse_wholesale_row,
    validate_required_mappings,
)


def test_validate_required_mappings_reports_missing_required_fields():
    columns = ["상태", "상품코드", "상품명", "가격", "원산지", "목록이미지1", "상세이미지"]
    mapping = {
        "wholesale_status": "상태",
        "product_code": "상품코드",
        "original_name": "상품명",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }

    missing = validate_required_mappings(mapping, columns)

    assert REQUIRED_WHOLESALE_FIELDS[1] == "wholesale_product_id"
    assert missing == ["wholesale_product_id"]


def test_validate_required_mappings_reports_missing_excel_headers():
    columns = ["상태", "제품번호", "상품코드", "상품명", "가격", "원산지", "상세이미지"]
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
    }

    missing = validate_required_mappings(mapping, columns)

    assert missing == ["image_list_1"]


def test_parse_int_price_handles_numeric_formatting():
    assert parse_int_price("2,640원") == 2640
    assert parse_int_price(" 2820.0 ") == 2820
    assert parse_int_price("") is None
    assert parse_int_price(None) is None


def test_parse_option_variants_pairs_options_with_prices_and_uses_first_price():
    result = parse_option_variants("L자형,V자형", "2640,2820")

    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == [
        {"name": "L자형", "price_wholesale": 2640, "position": 1},
        {"name": "V자형", "price_wholesale": 2820, "position": 2},
    ]
    assert result["warnings"] == []


def test_parse_option_variants_keeps_single_price_without_options():
    result = parse_option_variants(None, "3900")

    assert result["price_wholesale"] == 3900
    assert result["option_variants"] == []
    assert result["warnings"] == []


def test_parse_option_variants_warns_on_count_mismatch():
    result = parse_option_variants("L자형,V자형", "2640")

    assert result["price_wholesale"] == 2640
    assert result["option_variants"] == []
    assert result["warnings"] == [
        {
            "field": "option_variants",
            "message": "Option count and price count differ.",
            "option_count": 2,
            "price_count": 1,
        }
    ]


def test_build_images_list_uses_ordered_slots_and_drops_blanks():
    values = {
        "image_list_1": "https://img.example/1.jpg",
        "image_list_2": "",
        "image_list_3": "https://img.example/3.jpg",
        "image_list_4": None,
        "image_list_5": float("nan"),
    }

    assert build_images_list(values) == [
        "https://img.example/1.jpg",
        "https://img.example/3.jpg",
    ]


def test_parse_wholesale_row_normalizes_supplier_schema():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션값": "L자형,V자형",
            "가격": "2640,2820",
            "소비자가": "5,000",
            "판매준수가": "3,500",
            "원산지": "해외|아시아|중국",
            "목록이미지1": "https://img.example/1.jpg",
            "목록이미지2": "https://img.example/2.jpg",
            "상세이미지": "<img src='detail.jpg'>",
            "등록일": "2026-05-20",
        }
    )
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "option_values_raw": "옵션값",
        "price_wholesale_raw": "가격",
        "price_retail": "소비자가",
        "price_min_selling": "판매준수가",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_list_2": "목록이미지2",
        "image_detail": "상세이미지",
        "wholesale_registered_at": "등록일",
    }

    parsed = parse_wholesale_row(row, mapping)

    assert parsed["product_data"]["wholesale_status"] == "정상"
    assert parsed["product_data"]["wholesale_product_id"] == "12345"
    assert parsed["product_data"]["product_code"] == "ABC-001"
    assert parsed["product_data"]["original_name"] == "테스트 상품"
    assert parsed["product_data"]["price_wholesale_raw"] == "2640,2820"
    assert parsed["product_data"]["price_wholesale"] == 2640
    assert parsed["product_data"]["price_retail"] == 5000
    assert parsed["product_data"]["price_min_selling"] == 3500
    assert parsed["product_data"]["origin"] == "해외|아시아|중국"
    assert parsed["product_data"]["images_list"] == [
        "https://img.example/1.jpg",
        "https://img.example/2.jpg",
    ]
    assert parsed["product_data"]["image_detail"] == "<img src='detail.jpg'>"
    assert parsed["product_data"]["wholesale_registered_at"] == "2026-05-20"
    assert parsed["product_data"]["option_variants"][1] == {
        "name": "V자형",
        "price_wholesale": 2820,
        "position": 2,
    }
    assert parsed["warnings"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest services/processor/tests/test_wholesale_upload.py -v
```

Expected: FAIL during import with `ModuleNotFoundError` or `ImportError` because `utils.wholesale_upload` does not exist yet.

- [ ] **Step 3: Commit failing tests**

```bash
git add services/processor/tests/test_wholesale_upload.py
git commit -m "test(processor): define wholesale upload parser behavior"
```

---

### Task 2: Implement Wholesale Upload Parser

**Files:**
- Create: `services/processor/utils/wholesale_upload.py`
- Test: `services/processor/tests/test_wholesale_upload.py`

- [ ] **Step 1: Write parser utility**

Create `services/processor/utils/wholesale_upload.py`:

```python
import math
import re
from datetime import datetime
from typing import Any

import pandas as pd


REQUIRED_WHOLESALE_FIELDS = [
    "wholesale_status",
    "wholesale_product_id",
    "product_code",
    "original_name",
    "price_wholesale_raw",
    "origin",
    "image_list_1",
    "image_detail",
]

IMAGE_FIELD_KEYS = [
    "image_list_1",
    "image_list_2",
    "image_list_3",
    "image_list_4",
    "image_list_5",
]


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def clean_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return str(value).strip()


def validate_required_mappings(mapping: dict[str, str], columns: list[str]) -> list[str]:
    missing: list[str] = []
    for field_name in REQUIRED_WHOLESALE_FIELDS:
        header = mapping.get(field_name)
        if not header or header not in columns:
            missing.append(field_name)
    return missing


def get_mapped_value(row: pd.Series, mapping: dict[str, str], field_name: str, fallbacks: list[str] | None = None) -> Any:
    header = mapping.get(field_name)
    if not header and fallbacks:
        for fallback in fallbacks:
            if fallback in row.index:
                header = fallback
                break
    if header and header in row.index:
        value = row[header]
        if is_blank(value):
            return None
        return value
    return None


def parse_int_price(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = re.sub(r"[^0-9.]", "", text)
    if not normalized:
        return None
    try:
        return int(float(normalized))
    except ValueError:
        return None


def split_csv_text(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [token.strip() for token in text.split(",") if token.strip()]


def parse_option_variants(option_values_raw: Any, price_wholesale_raw: Any) -> dict[str, Any]:
    option_names = split_csv_text(option_values_raw)
    price_tokens = split_csv_text(price_wholesale_raw)
    warnings: list[dict[str, Any]] = []
    parsed_prices = [parse_int_price(token) for token in price_tokens]
    valid_prices = [price for price in parsed_prices if price is not None]
    representative_price = valid_prices[0] if valid_prices else None

    if option_names and len(option_names) != len(price_tokens):
        warnings.append({
            "field": "option_variants",
            "message": "Option count and price count differ.",
            "option_count": len(option_names),
            "price_count": len(price_tokens),
        })
        return {
            "price_wholesale": representative_price,
            "option_variants": [],
            "warnings": warnings,
        }

    if any(price is None for price in parsed_prices):
        warnings.append({
            "field": "price_wholesale_raw",
            "message": "One or more option prices could not be parsed.",
            "raw_value": clean_text(price_wholesale_raw) or "",
        })
        return {
            "price_wholesale": representative_price,
            "option_variants": [],
            "warnings": warnings,
        }

    option_variants = [
        {
            "name": option_name,
            "price_wholesale": parsed_prices[index],
            "position": index + 1,
        }
        for index, option_name in enumerate(option_names)
    ]

    return {
        "price_wholesale": representative_price,
        "option_variants": option_variants,
        "warnings": warnings,
    }


def build_images_list(values: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for key in IMAGE_FIELD_KEYS:
        image_value = clean_text(values.get(key))
        if image_value:
            images.append(image_value)
    return images


def json_safe_row(row: pd.Series) -> dict[str, Any]:
    raw_row_data = row.to_dict()
    for key, value in list(raw_row_data.items()):
        if is_blank(value):
            raw_row_data[key] = ""
        elif isinstance(value, (datetime, pd.Timestamp)):
            raw_row_data[key] = value.isoformat()
    return raw_row_data


def parse_wholesale_row(row: pd.Series, mapping: dict[str, str]) -> dict[str, Any]:
    mapped_values = {
        "wholesale_status": get_mapped_value(row, mapping, "wholesale_status", ["상태", "품절상태", "품절여부", "판매상태"]),
        "wholesale_product_id": get_mapped_value(row, mapping, "wholesale_product_id", ["제품번호", "제품ID", "상품ID"]),
        "product_code": get_mapped_value(row, mapping, "product_code", ["상품코드", "도매코드", "자체상품코드", "코드"]),
        "original_name": get_mapped_value(row, mapping, "original_name", ["상품명", "원본상품명", "제품명"]),
        "option_values_raw": get_mapped_value(row, mapping, "option_values_raw", ["옵션값", "옵션", "선택사항", "옵션명"]),
        "price_wholesale_raw": get_mapped_value(row, mapping, "price_wholesale_raw", ["가격", "공급가", "도매가", "도매가격"]),
        "price_retail": get_mapped_value(row, mapping, "price_retail", ["소비자가", "소매가", "소매가격"]),
        "price_min_selling": get_mapped_value(row, mapping, "price_min_selling", ["판매준수가", "최소판매가", "최저가"]),
        "origin": get_mapped_value(row, mapping, "origin", ["원산지", "제조국", "제조국가"]),
        "image_list_1": get_mapped_value(row, mapping, "image_list_1", ["목록이미지1", "대표이미지", "이미지", "상품이미지"]),
        "image_list_2": get_mapped_value(row, mapping, "image_list_2", ["목록이미지2"]),
        "image_list_3": get_mapped_value(row, mapping, "image_list_3", ["목록이미지3"]),
        "image_list_4": get_mapped_value(row, mapping, "image_list_4", ["목록이미지4"]),
        "image_list_5": get_mapped_value(row, mapping, "image_list_5", ["목록이미지5"]),
        "image_detail": get_mapped_value(row, mapping, "image_detail", ["상세이미지", "상세설명이미지"]),
        "wholesale_registered_at": get_mapped_value(row, mapping, "wholesale_registered_at", ["등록일", "상품등록일"]),
    }
    option_result = parse_option_variants(
        mapped_values["option_values_raw"],
        mapped_values["price_wholesale_raw"],
    )
    warnings = list(option_result["warnings"])

    for required_field in REQUIRED_WHOLESALE_FIELDS:
        if is_blank(mapped_values.get(required_field)):
            warnings.append({
                "field": required_field,
                "message": "Required value is blank.",
            })

    product_data = {
        "wholesale_status": clean_text(mapped_values["wholesale_status"]),
        "wholesale_product_id": clean_text(mapped_values["wholesale_product_id"]),
        "product_code": clean_text(mapped_values["product_code"]),
        "original_name": clean_text(mapped_values["original_name"]) or "",
        "option_values_raw": clean_text(mapped_values["option_values_raw"]),
        "price_wholesale_raw": clean_text(mapped_values["price_wholesale_raw"]),
        "price_wholesale": option_result["price_wholesale"],
        "option_variants": option_result["option_variants"],
        "price_retail": parse_int_price(mapped_values["price_retail"]),
        "price_min_selling": parse_int_price(mapped_values["price_min_selling"]),
        "origin": clean_text(mapped_values["origin"]),
        "images_list": build_images_list(mapped_values),
        "image_detail": clean_text(mapped_values["image_detail"]),
        "wholesale_registered_at": clean_text(mapped_values["wholesale_registered_at"]),
        "raw_metadata": json_safe_row(row),
    }

    return {
        "product_data": product_data,
        "warnings": warnings,
    }
```

- [ ] **Step 2: Run parser tests**

Run:

```bash
pytest services/processor/tests/test_wholesale_upload.py -v
```

Expected: PASS for all tests.

- [ ] **Step 3: Commit parser utility**

```bash
git add services/processor/utils/wholesale_upload.py services/processor/tests/test_wholesale_upload.py
git commit -m "feat(processor): parse wholesale upload rows"
```

---

### Task 3: Extend Product Model And API Schema

**Files:**
- Modify: `services/processor/models.py`
- Modify: `services/processor/schemas.py`
- Modify: `services/processor/init_prompts.py`
- Modify: `services/processor/tests/test_wholesale.py`

- [ ] **Step 1: Add model columns**

In `services/processor/models.py`, add these fields inside `class Product`, near the existing wholesale columns:

```python
    wholesale_product_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    option_values_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_wholesale_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_variants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    wholesale_registered_at: Mapped[str | None] = mapped_column(String, nullable=True)
```

Keep the existing `options` column for backwards compatibility. Do not remove it in this task.

- [ ] **Step 2: Expose fields in response schema**

In `services/processor/schemas.py`, add these fields to `ProductResponse` near the current wholesale fields:

```python
    wholesale_product_id: Optional[str] = None
    option_values_raw: Optional[str] = None
    price_wholesale_raw: Optional[str] = None
    option_variants: Optional[List] = None
    wholesale_registered_at: Optional[str] = None
```

- [ ] **Step 3: Add startup migrations**

In `services/processor/init_prompts.py`, add these `ALTER TABLE` statements with the existing product column migrations:

```python
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_product_id VARCHAR"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS option_values_raw TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_wholesale_raw TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS option_variants JSON"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_registered_at VARCHAR"))
```

- [ ] **Step 4: Add test fixture migrations**

In `services/processor/tests/test_wholesale.py`, add the same `ALTER TABLE` statements in the `test_db` fixture after the existing `product_code` migration:

```python
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_product_id VARCHAR"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS option_values_raw TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_wholesale_raw TEXT"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS option_variants JSON"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_registered_at VARCHAR"))
```

- [ ] **Step 5: Run model-related tests**

Run:

```bash
pytest services/processor/tests/test_wholesale.py services/processor/tests/test_wholesale_upload.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit schema changes**

```bash
git add services/processor/models.py services/processor/schemas.py services/processor/init_prompts.py services/processor/tests/test_wholesale.py
git commit -m "feat(processor): extend product supplier schema"
```

---

### Task 4: Wire Parser Into `/process-db`

**Files:**
- Modify: `services/processor/main.py`
- Modify: `services/processor/tests/test_wholesale.py`

- [ ] **Step 1: Import parser helpers**

In `services/processor/main.py`, add:

```python
from utils.wholesale_upload import parse_wholesale_row, validate_required_mappings
```

- [ ] **Step 2: Replace only required mapping validation**

Inside `start_db_processing`, replace the existing `orig_col` validation block:

```python
    orig_col = col_mapping.get("original_name")
    if not orig_col or orig_col not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column '{orig_col}' not found in excel.")
```

with:

```python
    missing_required = validate_required_mappings(col_mapping, list(df.columns))
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Required mapped columns missing in excel: {', '.join(missing_required)}",
        )
```

- [ ] **Step 3: Replace inline row extraction with parser output**

Inside the `for index, row in df.iterrows():` loop, replace the current block from:

```python
        original_name = str(row[orig_col])
        raw_row_data = row.to_dict()
```

through the end of the `wholesale_status` extraction with:

```python
        parsed_row = parse_wholesale_row(row, col_mapping)
        product_data = parsed_row["product_data"]
        row_warnings = parsed_row["warnings"]

        original_name = product_data["original_name"]
        product_code = product_data["product_code"]
        price_wholesale = product_data["price_wholesale"]
        wholesale_status = product_data["wholesale_status"]
        product_warnings = {"warnings": row_warnings} if row_warnings else None
```

- [ ] **Step 4: Update existing product assignment**

In the `if existing_product:` block, set all parsed fields:

```python
            existing_product.original_name = original_name
            existing_product.import_id = import_id
            existing_product.wholesale_site_id = request.wholesale_site_id
            existing_product.wholesale_product_id = product_data["wholesale_product_id"]
            existing_product.price_wholesale = product_data["price_wholesale"]
            existing_product.price_wholesale_raw = product_data["price_wholesale_raw"]
            existing_product.price_retail = product_data["price_retail"]
            existing_product.price_min_selling = product_data["price_min_selling"]
            existing_product.origin = product_data["origin"]
            existing_product.options = product_data["option_values_raw"]
            existing_product.option_values_raw = product_data["option_values_raw"]
            existing_product.option_variants = product_data["option_variants"]
            existing_product.images_list = product_data["images_list"]
            existing_product.image_detail = product_data["image_detail"]
            existing_product.wholesale_status = product_data["wholesale_status"]
            existing_product.wholesale_registered_at = product_data["wholesale_registered_at"]
            existing_product.status = "pending"
            existing_product.warnings = product_warnings
            existing_product.raw_metadata = product_data["raw_metadata"]
```

- [ ] **Step 5: Update new product creation**

In the `else:` block, create `Product` with the same parsed fields:

```python
            product = Product(
                user_id=current_user["id"],
                import_id=import_id,
                wholesale_site_id=request.wholesale_site_id,
                wholesale_product_id=product_data["wholesale_product_id"],
                product_code=product_code,
                price_wholesale=product_data["price_wholesale"],
                price_wholesale_raw=product_data["price_wholesale_raw"],
                price_retail=product_data["price_retail"],
                price_min_selling=product_data["price_min_selling"],
                origin=product_data["origin"],
                options=product_data["option_values_raw"],
                option_values_raw=product_data["option_values_raw"],
                option_variants=product_data["option_variants"],
                images_list=product_data["images_list"],
                image_detail=product_data["image_detail"],
                wholesale_status=product_data["wholesale_status"],
                wholesale_registered_at=product_data["wholesale_registered_at"],
                original_name=original_name,
                status="pending",
                warnings=product_warnings,
                raw_metadata=product_data["raw_metadata"],
            )
```

- [ ] **Step 6: Update smart-upsert test to assert new fields**

In `services/processor/tests/test_wholesale.py`, extend the existing product setup:

```python
            wholesale_product_id="OLD-123",
            option_values_raw="기본형",
            price_wholesale_raw="10000",
            option_variants=[{"name": "기본형", "price_wholesale": 10000, "position": 1}],
            wholesale_registered_at="2026-05-01",
```

After simulating upload changes, assign:

```python
        existing_product.wholesale_product_id = "NEW-123"
        existing_product.option_values_raw = "L자형,V자형"
        existing_product.price_wholesale_raw = "12000,13000"
        existing_product.option_variants = [
            {"name": "L자형", "price_wholesale": 12000, "position": 1},
            {"name": "V자형", "price_wholesale": 13000, "position": 2},
        ]
        existing_product.wholesale_registered_at = "2026-05-20"
```

Add final assertions after the mapping assertions:

```python
        product_res = await session.execute(select(Product).where(Product.id == product_id))
        updated_product = product_res.scalar_one()
        assert updated_product.wholesale_product_id == "NEW-123"
        assert updated_product.price_wholesale_raw == "12000,13000"
        assert updated_product.option_variants[0]["price_wholesale"] == 12000
        assert updated_product.wholesale_registered_at == "2026-05-20"
```

- [ ] **Step 7: Run backend wholesale tests**

Run:

```bash
pytest services/processor/tests/test_wholesale.py services/processor/tests/test_wholesale_upload.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit process-db wiring**

```bash
git add services/processor/main.py services/processor/tests/test_wholesale.py
git commit -m "feat(processor): ingest supplier upload schema"
```

---

### Task 5: Update Upload Mapper UI

**Files:**
- Modify: `frontend/src/app/(ai-mall)/upload/page.tsx`

- [ ] **Step 1: Replace `SYSTEM_FIELDS`**

Replace the current `SYSTEM_FIELDS` constant with:

```tsx
const SYSTEM_FIELDS = [
  { key: 'wholesale_status', label: '상태 (필수)', required: true, defaultFallbacks: ['상태', '품절상태', '품절여부', '판매상태'] },
  { key: 'wholesale_product_id', label: '제품번호 (필수)', required: true, defaultFallbacks: ['제품번호', '제품ID', '상품ID'] },
  { key: 'product_code', label: '상품코드 (필수)', required: true, defaultFallbacks: ['상품코드', '도매코드', '자체상품코드', '코드'] },
  { key: 'original_name', label: '상품명 (필수)', required: true, defaultFallbacks: ['상품명', '원본상품명', '제품명'] },
  { key: 'option_values_raw', label: '옵션값', required: false, defaultFallbacks: ['옵션값', '옵션', '선택사항', '옵션명'] },
  { key: 'price_wholesale_raw', label: '가격 (필수)', required: true, defaultFallbacks: ['가격', '공급가', '도매가', '공급가격', '도매가격'] },
  { key: 'price_retail', label: '소비자가', required: false, defaultFallbacks: ['소비자가', '소매가', '소매가격'] },
  { key: 'price_min_selling', label: '판매준수가', required: false, defaultFallbacks: ['판매준수가', '최소판매가', '최저가'] },
  { key: 'origin', label: '원산지 (필수)', required: true, defaultFallbacks: ['원산지', '제조국', '제조국가'] },
  { key: 'image_list_1', label: '목록이미지1 (필수)', required: true, defaultFallbacks: ['목록이미지1', '대표이미지', '이미지', '상품이미지'] },
  { key: 'image_list_2', label: '목록이미지2', required: false, defaultFallbacks: ['목록이미지2'] },
  { key: 'image_list_3', label: '목록이미지3', required: false, defaultFallbacks: ['목록이미지3'] },
  { key: 'image_list_4', label: '목록이미지4', required: false, defaultFallbacks: ['목록이미지4'] },
  { key: 'image_list_5', label: '목록이미지5', required: false, defaultFallbacks: ['목록이미지5'] },
  { key: 'image_detail', label: '상세이미지 (필수)', required: true, defaultFallbacks: ['상세이미지', '상세설명이미지'] },
  { key: 'wholesale_registered_at', label: '등록일', required: false, defaultFallbacks: ['등록일', '상품등록일'] }
];
```

- [ ] **Step 2: Keep existing validation flow**

Confirm `handleStartSmartProcess` still uses:

```tsx
const missing = SYSTEM_FIELDS.filter(f => f.required && !columnMapping[f.key]);
```

No code change is needed if this line remains unchanged.

- [ ] **Step 3: Run frontend static checks**

Run:

```bash
npm --prefix frontend run lint
```

Expected: PASS, or if the repo has no lint script, npm reports `Missing script: "lint"`.

- [ ] **Step 4: Commit mapper UI update**

```bash
git add 'frontend/src/app/(ai-mall)/upload/page.tsx'
git commit -m "feat(frontend): update wholesale upload mapping fields"
```

---

### Task 6: Full Verification And Documentation

**Files:**
- Potentially modify: `docs/solutions/architecture-patterns/wholesale-upload-schema-redesign.md` if creating a post-implementation learning note manually.

- [ ] **Step 1: Run focused backend verification**

Run:

```bash
pytest services/processor/tests/test_wholesale_upload.py services/processor/tests/test_wholesale.py -v
```

Expected: PASS.

- [ ] **Step 2: Run broader processor tests**

Run:

```bash
pytest services/processor/tests -v
```

Expected: PASS, unless external API credential tests are already skipped or documented as environment-dependent.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
npm --prefix frontend run build
```

Expected: successful Next.js production build.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only intended files changed. The pre-existing `nginx/nginx.conf` change may remain unstaged and should not be reverted.

- [ ] **Step 5: Commit any verification fixes**

If verification required fixes, stage only files touched for this feature:

```bash
git add services/processor frontend/src/app/(ai-mall)/upload/page.tsx
git commit -m "fix: stabilize wholesale upload schema"
```

If no fixes were needed, do not create an empty commit.

- [ ] **Step 6: Run compound documentation when creating PR or merging**

Per `AGENTS.md`, before merging or creating a PR run:

```bash
/.antigravitycli/skills/ce-compound mode:headless
```

If that path is not executable in this environment, document the implementation with the available `ce-compound` skill or create a solution note under `docs/solutions/`.

---

## Self-Review Notes

- Spec coverage: all approved fields, first-option representative price policy, raw value preservation, parsed `option_variants`, image aggregation, smart-upsert behavior, warnings, backend tests, and frontend mapper updates are covered.
- Scope: marketplace-specific option export remains out of scope and is not included in implementation tasks.
- Type consistency: field names are consistent across parser, model, schema, backend ingestion, and frontend mapping.
