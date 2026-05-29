# Multi-Marketplace Attribute Extraction Pipeline Design

Date: 2026-05-29

## Goal

Add an automated attribute extraction pipeline that analyzes product detail page content with LLM to extract marketplace-specific attributes for Naver SmartStore and Coupang simultaneously. The design must support additional marketplaces without restructuring the pipeline.

## Context

### Current State

The processor service handles product processing through a LangGraph pipeline:

```
load_product_context → mark_processing → refine_name → curate_keywords → map_categories → persist_success
```

After processing, the marketplace service generates listing drafts using adapters. Currently:

- **SmartStore adapter**: Generates `detailAttribute` with `originAreaInfo` and `optionInfo` only. `productAttributes` (category-specific attributes) is not generated.
- **Coupang adapter**: Hardcodes `"옵션"` as the only `attributeTypeName` in `items[].attributes[]`. Category-specific attributes are not reflected.
- **Processor**: `ProductPlatformMapping.mapped_attributes` (JSON) exists in the DB model but is never populated.
- **Detail page**: `image_detail` stores HTML/URL strings from wholesale supplier data but no text extraction or analysis occurs.

### Why Detail Page Content Matters

Product attributes (dimensions, weight, material, color, etc.) are typically embedded within the product's detail page, not the product name. For example:

- "가로 10cm, 세로 5cm, 높이 15cm"
- "무게: 500g"
- "소재: 스테인리스 스틸 304"

Without analyzing the detail page, the system cannot extract these values.

## Marketplace Attribute API Structures

### Naver SmartStore

**Attribute schema lookup:**
```
GET /v1/product-attributes/attributes?categoryId={id}
GET /v1/product-attributes/attribute-values?categoryId={id}
```

**Registration payload path:** `originProduct.detailAttribute.productAttributes[]`

Each attribute uses numeric IDs:
```json
{
  "attributeSeq": 12345,
  "attributeValueSeq": 67890,
  "attributeRealValue": "10",
  "attributeRealValueUnitCode": "CM"
}
```

Key characteristics:
- Numeric ID-based mapping (`attributeSeq` + `attributeValueSeq`).
- Predefined value IDs for select-type attributes.
- `attributeRealValue` + unit code for range/freetext attributes.
- Disallowed values are silently excluded during save.

### Coupang

**Attribute schema lookup:**
```
GET /v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/{displayCategoryCode}
```

**Registration payload:** Product-level `attributes[]` and item-level `vendorItems[].attributes[]`

Each attribute uses string name pairs:
```json
{
  "attributeTypeName": "브랜드",
  "attributeValueName": "우리브랜드"
}
```

Key characteristics:
- String name-based mapping (`attributeTypeName` + `attributeValueName`).
- `required: "MANDATORY"` / `"OPTIONAL"` field indicates necessity.
- `inputType: "SELECT"` attributes have `inputValues[]` constraining valid choices.
- `inputType: "INPUT"` attributes accept freetext.
- `exposed: "EXPOSED"` = purchase options (buyer-facing, create vendorItems). `exposed: "NONE"` = search options (filtering only).
- `dataType` (`STRING`, `NUMBER`, `DATE`) indicates expected format; even `NUMBER` values are passed as strings.
- `basicUnit` (cm, g, etc.) when applicable.

## Architecture

### Two-Phase Design: Market-Neutral Extraction → Market-Specific Mapping

A single LLM call extracts a standardized set of product specifications from the product name and detail page content. Separate mapping engines then convert those specs into each marketplace's native format. This avoids duplicating LLM calls per marketplace and makes adding new marketplaces a mapping-only task.

```
                    ┌────────────────────────────┐
                    │   Product Detail Content    │
                    │   (HTML with images / URLs) │
                    └──────────┬─────────────────┘
                               │
                    ┌──────────▼─────────────────┐
                    │   Detail Image Gathering    │
                    │   (Extract image URLs)      │
                    └──────────┬─────────────────┘
                               │
          ┌────────────────────▼────────────────────┐
          │     Vision LLM Attribute Extraction     │
          │  Input: product name + images +         │
          │         category attribute schemas      │
          │  Output: standardized key-value specs   │
          └────────────────────┬────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼────────┐ ┌─────▼──────────┐
    │ NaverMapper     │ │ CoupangMapper │ │ FutureMapper   │
    │ specs→attrSeq   │ │ specs→typeName│ │ specs→???      │
    │ /valueSeq       │ │ /valueName    │ │                │
    └─────────┬──────┘ └──────┬────────┘ └─────┬──────────┘
              │                │                │
    ┌─────────▼──────┐ ┌──────▼────────┐ ┌─────▼──────────┐
    │ naver mapping   │ │ coupang       │ │ future mapping │
    │ in DB           │ │ mapping in DB │ │ in DB          │
    └────────────────┘ └───────────────┘ └────────────────┘
```

### Pipeline Change

The existing LangGraph pipeline gains one node after `map_categories`:

```
load_product_context → mark_processing → refine_name → curate_keywords → map_categories → extract_attributes → persist_success
```

`extract_attributes` depends on `map_categories` because category IDs are needed to fetch attribute schemas. It utilizes the already resolved `state["naver_category"]["id"]` and `state["coupang_category"]` values from the DB mapping context.

### Detail Content Vision Processing

The `image_detail` field in the product model contains HTML content with `<img>` tags or raw image URLs. Since product specifications in wholesale data are heavily reliant on images rather than raw text, we will bypass HTML text parsing entirely and rely on a Vision LLM.

```python
def extract_images_from_detail_content(image_detail: str | None) -> list[str]:
    """
    1. If None/empty → return []
    2. Parse HTML to extract all `src` from `<img>` tags.
    3. If it's just a raw URL, return it as a list.
    """
```

The Vision LLM will be supplied with these images directly (using models like Gemini 1.5 Pro/Flash Vision capabilities) to visually parse spec tables, dimension markers, and textual details embedded in the images.

### Attribute Schema Providers

Each marketplace implements a provider that fetches the attribute schema for a given category:

```python
class AttributeSchemaProvider(ABC):
    @abstractmethod
    async def get_attribute_schema(self, category_id: str) -> AttributeSchema:
        """Returns the list of attributes and valid values for a category."""

@dataclass
class AttributeDef:
    name: str                        # "색상", "사이즈", etc.
    required: bool                   # True if mandatory
    data_type: str                   # "STRING", "NUMBER", "DATE"
    input_type: str                  # "SELECT" or "INPUT"
    unit: str | None                 # "cm", "g", etc.
    valid_values: list[str] | None   # For SELECT type

@dataclass
class AttributeSchema:
    market_code: str
    category_id: str
    attributes: list[AttributeDef]
```

**NaverAttributeSchemaProvider:**
- Calls `GET /v1/product-attributes/attributes` and `GET /v1/product-attributes/attribute-values`.
- Maps response into `AttributeSchema` with `attributeSeq` preserved for later mapping.
- Naver-specific extension: stores `attributeSeq` and `attributeValueSeq` lookup tables.

**CoupangAttributeSchemaProvider:**
- Calls `GET /v2/providers/.../category-related-metas/display-category-codes/{code}`.
- Maps response into `AttributeSchema`.
- Coupang-specific extension: stores `exposed` flag and `inputValues` lists.

**Caching:** Category attribute schemas change infrequently. The providers cache results in Redis with a TTL of 24 hours, keyed by `{market_code}:{category_id}`.

### Vision LLM Attribute Extraction

The Vision LLM receives the product name, the extracted detail images, and a unified summary of required attributes from all target marketplaces. It returns a single set of standardized specs.

**Input:**
```
상품명: {refined_name}
브랜드: {brand_name}
상세페이지 이미지: [Image 1], [Image 2], ...

[필요한 속성 목록]
- 색상 (필수, 선택: 레드/블루/블랙/화이트)
- 사이즈 (필수, 선택: S/M/L/XL)
- 소재 (선택, 직접입력)
- 가로 (필수, 숫자, 단위: cm)
- 세로 (필수, 숫자, 단위: cm)
- 개당 중량 (필수, 숫자, 단위: g)
```

**Output:**
```json
{
  "extracted_specs": {
    "색상": "블랙",
    "사이즈": "L",
    "소재": "스테인리스 스틸",
    "가로": "10",
    "세로": "5",
    "개당 중량": "500"
  },
  "confidence": 0.82,
  "extraction_notes": "가로/세로는 상세페이지 스펙표에서 추출"
}
```

The attribute list fed to the Vision LLM is a union of all marketplace schemas, deduplicated by normalized attribute name. This ensures one LLM call covers all marketplaces.

### Attribute Mappers

After LLM extraction, mappers convert the standardized specs to each marketplace's native format.

**NaverAttributeMapper:**
```python
class NaverAttributeMapper(AttributeMapper):
    def map_attributes(self, specs: dict, schema: NaverAttributeSchema) -> list[dict]:
        """
        For each spec key-value:
        1. Find matching attributeSeq by name
        2. For SELECT type: find matching attributeValueSeq
        3. For INPUT/RANGE type: use attributeRealValue + unitCode
        4. Skip if no match found
        """
```

**CoupangAttributeMapper:**
```python
class CoupangAttributeMapper(AttributeMapper):
    def map_attributes(self, specs: dict, schema: CoupangAttributeSchema) -> dict:
        """
        Returns separate lists for product-level and item-level attributes:
        {
          "product_attributes": [...],  # exposed: NONE (search options)
          "item_attributes": [...]      # exposed: EXPOSED (purchase options)
        }
        For SELECT type: validate value against inputValues
        For INPUT type: pass value directly
        """
```

### Data Storage

Extracted attributes are stored in `ProductPlatformMapping.mapped_attributes` (existing JSON column):

```json
{
  "schema_version": "v1",
  "extracted_at": "2026-05-29T10:00:00Z",
  "extracted_specs": {
    "색상": "블랙",
    "가로": "10",
    "세로": "5"
  },
  "confidence": 0.82,
  "naver_attributes": [
    {"attributeSeq": 12345, "attributeValueSeq": 67890},
    {"attributeSeq": 23456, "attributeRealValue": "10", "attributeRealValueUnitCode": "CM"}
  ],
  "coupang_attributes": {
    "product_attributes": [
      {"attributeTypeName": "브랜드", "attributeValueName": "우리브랜드"}
    ],
    "item_attributes": [
      {"attributeTypeName": "색상", "attributeValueName": "블랙"}
    ]
  }
}
```

### Adapter Consumption

The SmartStore and Coupang adapters read `mapped_attributes` from the marketplace snapshot and incorporate them into the generated payload.

**SmartStore adapter change:**
```python
# In SmartstoreAdapter.generate_draft():
# After building detailAttribute...
mapped = self._extract_mapped_attributes(source_snapshot)
if mapped and mapped.get("naver_attributes"):
    payload["originProduct"]["detailAttribute"]["productAttributes"] = mapped["naver_attributes"]
```

**Coupang adapter change:**
```python
# In CoupangAdapter.generate_draft():
# Product-level attributes
mapped = self._extract_mapped_attributes(source_snapshot)
if mapped and mapped.get("coupang_attributes"):
    coupang_attrs = mapped["coupang_attributes"]
    payload["attributes"] = coupang_attrs.get("product_attributes", [])
    # Item-level attributes merged into each item
    for item in payload.get("items", []):
        existing = item.get("attributes", [])
        item["attributes"] = existing + coupang_attrs.get("item_attributes", [])
```

### Marketplace Snapshot Contract Extension

The marketplace snapshot already includes `mapped_attributes` per platform mapping. No contract change is needed. The existing structure:

```json
{
  "market_categories": {
    "smartstore": {
      "category_id": "50000123",
      "category_path": "생활/주방 > 컵",
      "mapped_attributes": { ... }
    },
    "coupang": {
      "category_id": "123456",
      "mapped_attributes": { ... }
    }
  }
}
```

## Error Handling

- **LLM extraction failure**: Log warning, continue without attributes. Product is still registerable without optional attributes.
- **Schema provider API failure**: Use cached schema if available. If no cache, log warning and skip attribute extraction for that marketplace.
- **Mapper validation failure** (e.g., SELECT value not in valid list): Exclude that specific attribute, add a warning to product warnings.
- **Empty detail content**: Extract what's possible from product name and brand alone. Log that detail content was unavailable.

Attribute extraction failures never block the product processing pipeline. They produce warnings that the user can review.

## Scope Boundaries

### In scope
- Extracting image URLs from detail page HTML.
- Vision LLM-based attribute extraction from detail images.
- Using existing mapped category IDs (`state["naver_category"]["id"]`, `state["coupang_category"]`) for schema lookups.
- Naver SmartStore attribute schema provider and mapper.
- Coupang attribute schema provider and mapper.
- Redis caching for attribute schemas.
- `extract_attributes` LangGraph node.
- SmartStore adapter consuming `productAttributes`.
- Coupang adapter consuming product-level and item-level attributes.
- LLM prompt template stored in the `prompts` table.

### Out of scope (follow-up iterations)
- Fallback text-only extraction for text-heavy detail pages without images.
- User-facing attribute review/edit UI.
- Attribute extraction accuracy dashboard.
- Attribute schema cache invalidation webhook.
- Additional marketplace providers beyond Naver and Coupang.

## New Dependencies

- Naver Commerce API client credentials for attribute schema lookup.
- Coupang Open API client credentials for category metadata lookup.
- No new database tables or migrations needed (`mapped_attributes` column already exists).

## Extensibility Contract

Adding a new marketplace requires:

1. Implement `AttributeSchemaProvider` subclass for the new marketplace.
2. Implement `AttributeMapper` subclass for the new marketplace.
3. Register both in provider/mapper dictionaries.
4. Update the marketplace adapter to consume `mapped_attributes`.

No changes to the LLM prompt, extraction logic, or pipeline graph are needed.
