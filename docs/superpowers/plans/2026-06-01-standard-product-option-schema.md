# Standard Product Option Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize supplier uploads and future crawler imports into Auto-Selp's own `products + product_options` standard while preserving existing product processing and marketplace draft flows.

**Architecture:** Add a focused standard schema registry and option normalizer in the processor service, then adapt the current wholesale upload parser to emit both backward-compatible `option_variants` and the new standard option shape. Persist the standard option shape in JSON first to avoid a risky database split, expose it through marketplace snapshots, and update the upload/product UI labels so users see Auto-Selp's standard columns rather than supplier-shaped fields.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL JSON columns, Pandas Excel parsing, Pytest, Next.js React/TypeScript.

---

## File Structure

- Create `services/processor/utils/standard_product_schema.py`: canonical field registry, required field constants, option type constants, and pure helpers for deriving option display names and price deltas.
- Modify `services/processor/utils/wholesale_upload.py`: map legacy/current wholesale fields into the standard schema, parse option image fields, and emit `standard_options` while preserving `option_variants`.
- Modify `services/processor/tests/test_wholesale_upload.py`: add tests for colon-separated options, option images, price delta derivation, and products without options.
- Modify `services/processor/models.py`: add `standard_options` JSON column on `Product` as the compatibility-phase store for `product_options`.
- Modify `services/processor/schemas.py`: expose `standard_options` through `ProductResponse` and `MarketplaceSnapshotResponse`.
- Modify `services/processor/init_prompts.py`: add idempotent migration for `products.standard_options`.
- Modify `services/processor/main.py`: persist `standard_options` on create/update and include it in marketplace snapshots.
- Modify `services/processor/tests/test_marketplace_snapshot.py`: verify standard options and option images are included in snapshots.
- Modify `frontend/src/app/(ai-mall)/upload/page.tsx`: regroup mapper fields into required product, optional product, and option fields with Auto-Selp standard labels.
- Modify `frontend/src/app/(ai-mall)/products/page.tsx`: add `standard_options` typing and render option image/structured option details where the existing option column appears.

---

### Task 1: Add Standard Schema Registry

**Files:**
- Create: `services/processor/utils/standard_product_schema.py`
- Test: `services/processor/tests/test_wholesale_upload.py`

- [ ] **Step 1: Add failing tests for standard option helpers**

Append these tests to `services/processor/tests/test_wholesale_upload.py`:

```python
from utils.standard_product_schema import (
    REQUIRED_STANDARD_PRODUCT_FIELDS,
    build_option_display_name,
    derive_option_price_delta,
)


def test_standard_required_fields_include_origin_and_supplier_identity():
    assert REQUIRED_STANDARD_PRODUCT_FIELDS == [
        "supplier_name",
        "supplier_product_id",
        "supplier_product_code",
        "supplier_status",
        "raw_product_name",
        "origin",
        "supply_price",
        "main_image_url",
        "detail_content",
    ]


def test_build_option_display_name_joins_non_blank_values():
    option = {
        "option_value_1": "블랙",
        "option_value_2": "L",
        "option_value_3": "",
    }

    assert build_option_display_name(option) == "블랙 / L"


def test_derive_option_price_delta_uses_option_supply_price_as_source():
    assert derive_option_price_delta(option_supply_price=13000, base_supply_price=12000) == 1000
    assert derive_option_price_delta(option_supply_price=12000, base_supply_price=12000) == 0
    assert derive_option_price_delta(option_supply_price=None, base_supply_price=12000) is None
    assert derive_option_price_delta(option_supply_price=13000, base_supply_price=None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/processor
pytest tests/test_wholesale_upload.py::test_standard_required_fields_include_origin_and_supplier_identity tests/test_wholesale_upload.py::test_build_option_display_name_joins_non_blank_values tests/test_wholesale_upload.py::test_derive_option_price_delta_uses_option_supply_price_as_source -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'utils.standard_product_schema'`.

- [ ] **Step 3: Create the schema helper module**

Create `services/processor/utils/standard_product_schema.py`:

```python
from typing import Any


REQUIRED_STANDARD_PRODUCT_FIELDS = [
    "supplier_name",
    "supplier_product_id",
    "supplier_product_code",
    "supplier_status",
    "raw_product_name",
    "origin",
    "supply_price",
    "main_image_url",
    "detail_content",
]

OPTION_TYPES = {"single", "combination", "custom", "standard"}


def clean_standard_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_option_display_name(option: dict[str, Any]) -> str:
    values = [
        clean_standard_text(option.get("option_value_1")),
        clean_standard_text(option.get("option_value_2")),
        clean_standard_text(option.get("option_value_3")),
    ]
    visible_values = [value for value in values if value]
    return " / ".join(visible_values)


def derive_option_price_delta(
    option_supply_price: int | None,
    base_supply_price: int | None,
) -> int | None:
    if option_supply_price is None or base_supply_price is None:
        return None
    return option_supply_price - base_supply_price
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd services/processor
pytest tests/test_wholesale_upload.py::test_standard_required_fields_include_origin_and_supplier_identity tests/test_wholesale_upload.py::test_build_option_display_name_joins_non_blank_values tests/test_wholesale_upload.py::test_derive_option_price_delta_uses_option_supply_price_as_source -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/processor/utils/standard_product_schema.py services/processor/tests/test_wholesale_upload.py
git commit -m "feat: add standard product schema helpers"
```

---

### Task 2: Normalize Current Upload Options Into Standard Options

**Files:**
- Modify: `services/processor/utils/wholesale_upload.py`
- Modify: `services/processor/tests/test_wholesale_upload.py`

- [ ] **Step 1: Add failing tests for standard options from current upload rows**

Append these tests to `services/processor/tests/test_wholesale_upload.py`:

```python
def test_parse_wholesale_row_emits_standard_options_with_price_delta_and_images():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "옵션값": "블랙,L",
            "가격": "12000,13000",
            "원산지": "국산",
            "목록이미지1": "https://img.example/product.jpg",
            "상세이미지": "<img src='detail.jpg'>",
            "옵션이미지": "https://img.example/black.jpg,https://img.example/large.jpg",
        }
    )
    mapping = {
        "wholesale_status": "상태",
        "wholesale_product_id": "제품번호",
        "product_code": "상품코드",
        "original_name": "상품명",
        "option_values_raw": "옵션값",
        "price_wholesale_raw": "가격",
        "origin": "원산지",
        "image_list_1": "목록이미지1",
        "image_detail": "상세이미지",
        "option_image_urls_raw": "옵션이미지",
    }

    parsed = parse_wholesale_row(row, mapping)

    assert parsed["product_data"]["standard_options"] == [
        {
            "supplier_product_code": "ABC-001",
            "option_sku": "ABC-001-1",
            "option_type": "combination",
            "option_group_1": "옵션",
            "option_value_1": "블랙",
            "option_group_2": None,
            "option_value_2": None,
            "option_group_3": None,
            "option_value_3": None,
            "option_display_name": "블랙",
            "option_supply_price": 12000,
            "option_sale_price": None,
            "option_price_delta": 0,
            "option_stock_quantity": None,
            "option_status": "정상",
            "option_usable": True,
            "option_main_image_url": "https://img.example/black.jpg",
            "option_extra_image_urls": [],
            "option_position": 1,
            "raw_option_text": "블랙",
            "raw_option_metadata": {
                "source": "option_values_raw",
                "price_token": "12000",
                "image_token": "https://img.example/black.jpg",
            },
        },
        {
            "supplier_product_code": "ABC-001",
            "option_sku": "ABC-001-2",
            "option_type": "combination",
            "option_group_1": "옵션",
            "option_value_1": "L",
            "option_group_2": None,
            "option_value_2": None,
            "option_group_3": None,
            "option_value_3": None,
            "option_display_name": "L",
            "option_supply_price": 13000,
            "option_sale_price": None,
            "option_price_delta": 1000,
            "option_stock_quantity": None,
            "option_status": "정상",
            "option_usable": True,
            "option_main_image_url": "https://img.example/large.jpg",
            "option_extra_image_urls": [],
            "option_position": 2,
            "raw_option_text": "L",
            "raw_option_metadata": {
                "source": "option_values_raw",
                "price_token": "13000",
                "image_token": "https://img.example/large.jpg",
            },
        },
    ]


def test_parse_wholesale_row_without_options_has_empty_standard_options():
    row = pd.Series(
        {
            "상태": "정상",
            "제품번호": "12345",
            "상품코드": "ABC-001",
            "상품명": "테스트 상품",
            "가격": "12000",
            "원산지": "국산",
            "목록이미지1": "https://img.example/product.jpg",
            "상세이미지": "<img src='detail.jpg'>",
        }
    )

    parsed = parse_wholesale_row(row, {})

    assert parsed["product_data"]["price_wholesale"] == 12000
    assert parsed["product_data"]["option_variants"] == []
    assert parsed["product_data"]["standard_options"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd services/processor
pytest tests/test_wholesale_upload.py::test_parse_wholesale_row_emits_standard_options_with_price_delta_and_images tests/test_wholesale_upload.py::test_parse_wholesale_row_without_options_has_empty_standard_options -v
```

Expected: FAIL with `KeyError: 'standard_options'`.

- [ ] **Step 3: Add option image fallback and standard option builder**

Modify `services/processor/utils/wholesale_upload.py`:

```python
from utils.standard_product_schema import build_option_display_name, derive_option_price_delta
```

Add `"option_image_urls_raw": ["옵션이미지", "옵션 이미지", "옵션별이미지", "옵션별 이미지"]` to `FIELD_FALLBACKS`.

Add this helper below `parse_option_variants`:

```python
def build_standard_options(
    *,
    supplier_product_code: str | None,
    supplier_status: str | None,
    option_values_raw: Any,
    price_wholesale_raw: Any,
    base_supply_price: int | None,
    option_image_urls_raw: Any,
) -> list[dict[str, Any]]:
    option_names = split_csv_text(option_values_raw)
    if not option_names:
        return []

    price_tokens = split_option_price_text(price_wholesale_raw)
    simple_price_tokens = split_csv_text(price_wholesale_raw)
    if len(price_tokens) != len(option_names) and len(simple_price_tokens) == len(option_names):
        price_tokens = simple_price_tokens
    image_tokens = split_csv_text(option_image_urls_raw)

    options: list[dict[str, Any]] = []
    for index, option_name in enumerate(option_names):
        price_token = price_tokens[index] if index < len(price_tokens) else None
        image_token = image_tokens[index] if index < len(image_tokens) else None
        option_supply_price = parse_int_price(price_token)
        option = {
            "supplier_product_code": supplier_product_code,
            "option_sku": f"{supplier_product_code}-{index + 1}" if supplier_product_code else None,
            "option_type": "combination",
            "option_group_1": "옵션",
            "option_value_1": option_name,
            "option_group_2": None,
            "option_value_2": None,
            "option_group_3": None,
            "option_value_3": None,
            "option_display_name": "",
            "option_supply_price": option_supply_price,
            "option_sale_price": None,
            "option_price_delta": derive_option_price_delta(option_supply_price, base_supply_price),
            "option_stock_quantity": None,
            "option_status": supplier_status,
            "option_usable": supplier_status not in {"품절", "판매중지", "중지"},
            "option_main_image_url": clean_text(image_token),
            "option_extra_image_urls": [],
            "option_position": index + 1,
            "raw_option_text": option_name,
            "raw_option_metadata": {
                "source": "option_values_raw",
                "price_token": clean_text(price_token),
                "image_token": clean_text(image_token),
            },
        }
        option["option_display_name"] = build_option_display_name(option)
        options.append(option)
    return options
```

- [ ] **Step 4: Include option image input and standard options in row parsing**

In `parse_wholesale_row`, add the mapped value:

```python
"option_image_urls_raw": get_mapped_value(row, mapping, "option_image_urls_raw"),
```

Then add this field to `product_data`:

```python
"standard_options": build_standard_options(
    supplier_product_code=clean_text(mapped_values["product_code"]),
    supplier_status=clean_text(mapped_values["wholesale_status"]),
    option_values_raw=mapped_values["option_values_raw"],
    price_wholesale_raw=mapped_values["price_wholesale_raw"],
    base_supply_price=option_result["price_wholesale"],
    option_image_urls_raw=mapped_values["option_image_urls_raw"],
),
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
cd services/processor
pytest tests/test_wholesale_upload.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/processor/utils/wholesale_upload.py services/processor/tests/test_wholesale_upload.py
git commit -m "feat: normalize supplier options to standard options"
```

---

### Task 3: Persist And Expose Standard Options

**Files:**
- Modify: `services/processor/models.py`
- Modify: `services/processor/schemas.py`
- Modify: `services/processor/init_prompts.py`
- Modify: `services/processor/main.py`
- Modify: `services/processor/tests/test_marketplace_snapshot.py`

- [ ] **Step 1: Add failing snapshot test**

In `services/processor/tests/test_marketplace_snapshot.py`, update `build_product` to include:

```python
standard_options=[
    {
        "supplier_product_code": "P-100",
        "option_sku": "P-100-1",
        "option_type": "combination",
        "option_group_1": "옵션",
        "option_value_1": "L자형",
        "option_group_2": None,
        "option_value_2": None,
        "option_group_3": None,
        "option_value_3": None,
        "option_display_name": "L자형",
        "option_supply_price": 12000,
        "option_sale_price": None,
        "option_price_delta": 0,
        "option_stock_quantity": None,
        "option_status": "판매중",
        "option_usable": True,
        "option_main_image_url": "https://img.example/option-l.jpg",
        "option_extra_image_urls": [],
        "option_position": 1,
        "raw_option_text": "L자형",
        "raw_option_metadata": {"source": "fixture"},
    }
],
```

Add this assertion in `test_marketplace_snapshot_success`:

```python
assert body["standard_options"] == [
    {
        "supplier_product_code": "P-100",
        "option_sku": "P-100-1",
        "option_type": "combination",
        "option_group_1": "옵션",
        "option_value_1": "L자형",
        "option_group_2": None,
        "option_value_2": None,
        "option_group_3": None,
        "option_value_3": None,
        "option_display_name": "L자형",
        "option_supply_price": 12000,
        "option_sale_price": None,
        "option_price_delta": 0,
        "option_stock_quantity": None,
        "option_status": "판매중",
        "option_usable": True,
        "option_main_image_url": "https://img.example/option-l.jpg",
        "option_extra_image_urls": [],
        "option_position": 1,
        "raw_option_text": "L자형",
        "raw_option_metadata": {"source": "fixture"},
    }
]
```

- [ ] **Step 2: Run snapshot test to verify it fails**

Run:

```bash
cd services/processor
pytest tests/test_marketplace_snapshot.py::test_marketplace_snapshot_success -v
```

Expected: FAIL because `standard_options` is missing from the response.

- [ ] **Step 3: Add model and schema fields**

In `services/processor/models.py`, add after `option_variants`:

```python
standard_options: Mapped[list | None] = mapped_column(JSON, nullable=True)
```

In `services/processor/schemas.py`, add to `ProductResponse` after `option_variants`:

```python
standard_options: Optional[List[Dict[str, Any]]] = None
```

Add to `MarketplaceSnapshotResponse` after `options`:

```python
standard_options: List[Dict[str, Any]] = []
```

- [ ] **Step 4: Add idempotent migration**

In `services/processor/init_prompts.py`, add the migration next to the option columns:

```python
await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS standard_options JSON"))
```

- [ ] **Step 5: Persist standard options on create and update**

In `services/processor/main.py`, when updating `existing_product`, add:

```python
existing_product.standard_options = product_data["standard_options"]
```

When creating `Product(...)`, add:

```python
standard_options=product_data["standard_options"],
```

In the marketplace snapshot response body, add:

```python
"standard_options": product.standard_options or [],
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd services/processor
pytest tests/test_wholesale_upload.py tests/test_marketplace_snapshot.py::test_marketplace_snapshot_success -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/processor/models.py services/processor/schemas.py services/processor/init_prompts.py services/processor/main.py services/processor/tests/test_marketplace_snapshot.py
git commit -m "feat: persist standard product options"
```

---

### Task 4: Update Upload Mapper To Show Auto-Selp Standard Fields

**Files:**
- Modify: `frontend/src/app/(ai-mall)/upload/page.tsx`

- [ ] **Step 1: Replace flat `SYSTEM_FIELDS` with grouped standard fields**

In `frontend/src/app/(ai-mall)/upload/page.tsx`, replace `const SYSTEM_FIELDS = [...]` with:

```typescript
const SYSTEM_FIELD_GROUPS = [
  {
    title: '필수 상품 컬럼',
    fields: [
      { key: 'supplier_name', label: '도매처명 (필수)', required: true, defaultFallbacks: ['도매처', '도매처명', '공급사', '공급처'] },
      { key: 'wholesale_product_id', standardKey: 'supplier_product_id', label: '도매처 상품 ID (필수)', required: true, defaultFallbacks: ['제품번호', '제품ID', '상품ID'] },
      { key: 'product_code', standardKey: 'supplier_product_code', label: '도매처 상품 코드 (필수)', required: true, defaultFallbacks: ['상품코드', '도매코드', '자체상품코드', '코드'] },
      { key: 'wholesale_status', standardKey: 'supplier_status', label: '도매처 판매 상태 (필수)', required: true, defaultFallbacks: ['상태', '품절상태', '품절여부', '판매상태'] },
      { key: 'original_name', standardKey: 'raw_product_name', label: '도매처 원본 상품명 (필수)', required: true, defaultFallbacks: ['상품명', '원본상품명', '제품명'] },
      { key: 'origin', label: '원산지 (필수)', required: true, defaultFallbacks: ['원산지', '제조국', '제조국가'] },
      { key: 'price_wholesale_raw', standardKey: 'supply_price', label: '기본 공급가 (필수)', required: true, defaultFallbacks: ['공급가', '도매가', '공급가격', '도매가격', '가격'] },
      { key: 'image_list_1', standardKey: 'main_image_url', label: '대표 이미지 (필수)', required: true, defaultFallbacks: ['목록이미지1', '대표이미지', '상품이미지', '이미지'] },
      { key: 'image_detail', standardKey: 'detail_content', label: '상세 이미지/HTML (필수)', required: true, defaultFallbacks: ['상세이미지', '상세설명이미지', '상세HTML'] },
    ],
  },
  {
    title: '선택 상품 컬럼',
    fields: [
      { key: 'supplier_category', label: '도매처 카테고리', required: false, defaultFallbacks: ['카테고리', '분류', '도매카테고리'] },
      { key: 'price_retail', standardKey: 'retail_price', label: '소비자가', required: false, defaultFallbacks: ['소비자가', '소매가', '소매가격'] },
      { key: 'price_min_selling', standardKey: 'minimum_selling_price', label: '판매준수가', required: false, defaultFallbacks: ['판매준수가', '최소판매가', '최저가'] },
      { key: 'stock_quantity', label: '상품 재고', required: false, defaultFallbacks: ['재고', '재고수량', '수량'] },
      { key: 'brand_name', label: '브랜드명', required: false, defaultFallbacks: ['브랜드', '브랜드명'] },
      { key: 'manufacturer', label: '제조사', required: false, defaultFallbacks: ['제조사', '제조원'] },
      { key: 'model_name', label: '모델명', required: false, defaultFallbacks: ['모델명', '모델'] },
      { key: 'image_list_2', standardKey: 'extra_image_urls', label: '추가 이미지 1', required: false, defaultFallbacks: ['목록이미지2', '추가이미지1'] },
      { key: 'image_list_3', standardKey: 'extra_image_urls', label: '추가 이미지 2', required: false, defaultFallbacks: ['목록이미지3', '추가이미지2'] },
      { key: 'image_list_4', standardKey: 'extra_image_urls', label: '추가 이미지 3', required: false, defaultFallbacks: ['목록이미지4', '추가이미지3'] },
      { key: 'image_list_5', standardKey: 'extra_image_urls', label: '추가 이미지 4', required: false, defaultFallbacks: ['목록이미지5', '추가이미지4'] },
      { key: 'wholesale_registered_at', standardKey: 'supplier_registered_at', label: '도매처 등록일', required: false, defaultFallbacks: ['등록일', '상품등록일'] },
    ],
  },
  {
    title: '옵션 컬럼',
    fields: [
      { key: 'option_values_raw', standardKey: 'raw_options_text', label: '옵션 원본값', required: false, defaultFallbacks: ['옵션값', '옵션', '선택사항', '옵션명'] },
      { key: 'option_image_urls_raw', label: '옵션별 이미지', required: false, defaultFallbacks: ['옵션이미지', '옵션 이미지', '옵션별이미지', '옵션별 이미지'] },
      { key: 'option_stock_quantity', label: '옵션별 재고', required: false, defaultFallbacks: ['옵션재고', '옵션 재고', '옵션수량'] },
      { key: 'option_sku', label: '옵션 코드', required: false, defaultFallbacks: ['옵션코드', '옵션 SKU', '옵션SKU'] },
    ],
  },
];

const SYSTEM_FIELDS = SYSTEM_FIELD_GROUPS.flatMap(group => group.fields);
```

- [ ] **Step 2: Update mapper rendering to show group headings**

Find the mapper section that currently does:

```tsx
{SYSTEM_FIELDS.map(field => (
```

Replace the surrounding loop with:

```tsx
{SYSTEM_FIELD_GROUPS.map(group => (
  <div key={group.title} className={styles.mapperGroup}>
    <h3 className={styles.mapperGroupTitle}>{group.title}</h3>
    {group.fields.map(field => (
      // keep the existing field row JSX here unchanged
    ))}
  </div>
))}
```

Keep the existing select and mapping update logic inside each field row.

- [ ] **Step 3: Add minimal styles for grouped sections**

In `frontend/src/app/(ai-mall)/upload/upload.module.css`, add:

```css
.mapperGroup {
  display: grid;
  gap: 10px;
  padding: 14px 0;
  border-top: 1px solid var(--hairline);
}

.mapperGroup:first-child {
  border-top: 0;
  padding-top: 0;
}

.mapperGroupTitle {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
}
```

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(ai-mall\)/upload/page.tsx frontend/src/app/\(ai-mall\)/upload/upload.module.css
git commit -m "feat: group upload mapper by standard product schema"
```

---

### Task 5: Render Standard Options In Product Management

**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/page.tsx`
- Modify: `frontend/src/app/(ai-mall)/products/products.module.css`

- [ ] **Step 1: Extend product type**

In `frontend/src/app/(ai-mall)/products/page.tsx`, add:

```typescript
type StandardOption = {
  option_sku: string | null;
  option_display_name: string;
  option_supply_price: number | null;
  option_price_delta: number | null;
  option_stock_quantity: number | null;
  option_status: string | null;
  option_main_image_url: string | null;
  option_position: number;
};
```

Then add to `interface Product`:

```typescript
standard_options?: StandardOption[] | null;
```

- [ ] **Step 2: Add a renderer for standard options**

Inside `ProductsPage`, before the table return block, add:

```typescript
const renderStandardOptions = (product: Product) => {
  const options = product.standard_options || [];
  if (options.length === 0) {
    return <span className={styles.emptyInline}>옵션 없음</span>;
  }

  const first = options[0];
  return (
    <div className={styles.standardOptionPreview}>
      {first.option_main_image_url && (
        <img
          src={first.option_main_image_url}
          alt=""
          className={styles.standardOptionImage}
        />
      )}
      <div className={styles.standardOptionText}>
        <span className={styles.optionCount}>옵션 {options.length}개</span>
        <span>{first.option_display_name || first.option_sku || '-'}</span>
        <span>{formatPrice(first.option_supply_price)}</span>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Prefer standard option rendering in the option column**

Find `case 'option_variants':` and replace the first branch with:

```tsx
{p.standard_options && p.standard_options.length > 0 ? (
  renderStandardOptions(p)
) : p.option_variants && p.option_variants.length > 0 ? (
  // keep the existing option_variants JSX here
) : (
  <span className={styles.emptyInline}>옵션 없음</span>
)}
```

- [ ] **Step 4: Add option preview styles**

In `frontend/src/app/(ai-mall)/products/products.module.css`, add:

```css
.standardOptionPreview {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 180px;
}

.standardOptionImage {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  object-fit: cover;
  border: 1px solid var(--hairline);
  background: var(--canvas-subtle);
}

.standardOptionText {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.standardOptionText span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/\(ai-mall\)/products/page.tsx frontend/src/app/\(ai-mall\)/products/products.module.css
git commit -m "feat: show standard options in product management"
```

---

### Task 6: Full Verification

**Files:**
- Verify changes from Tasks 1-5.

- [ ] **Step 1: Run processor tests**

Run:

```bash
cd services/processor
pytest tests/test_wholesale_upload.py tests/test_marketplace_snapshot.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short
```

Expected: clean working tree after the task commits.

- [ ] **Step 4: Record implementation learning**

Because this project requires solution documentation after finishing work that is merged or turned into a PR, run:

```bash
/ce-compound mode:headless
```

Expected: a new or updated document under `docs/solutions/` that captures the standard schema and option-normalization lesson.

---

## Self-Review

- Spec coverage: the plan covers the standard field registry, required `origin`, `products + product_options` workbook shape via `standard_options`, option images, option price delta derivation, marketplace snapshot exposure, upload UI grouping, and product management display.
- Intentional deferral: a first-class `product_options` SQL table is not introduced in this plan. The approved spec recommends a phased approach, and this plan implements the compatibility phase by storing standard options in JSON.
- Placeholder scan: the plan contains concrete file paths, code snippets, commands, and expected outcomes for every task.
