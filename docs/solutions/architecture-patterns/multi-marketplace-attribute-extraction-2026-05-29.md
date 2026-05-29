---
title: Multi-Marketplace Attribute Extraction and Mapping Pipeline
date: 2026-05-29
category: architecture-patterns
module: Product Processor & Marketplace Service
problem_type: architecture_pattern
component: service_object
severity: medium
applies_when:
  - "When implementing multi-marketplace (Naver SmartStore, Coupang Wing) product detail page attribute extraction"
  - "When mapping generic Vision LLM extracted specifications to strict, platform-specific schema requirements"
  - "When caching external marketplace category schemas using Redis"
tags:
  - attribute-extraction
  - vision-llm
  - naver-smartstore
  - coupang
  - langgraph
  - redis-caching
---

# Multi-Marketplace Attribute Extraction and Mapping Pipeline

## Context
When registering products across various electronic marketplaces like Naver SmartStore and Coupang, each platform enforces distinct category schema structures:
1. **Naver SmartStore**: Uses strict numerical IDs (`attributeSeq` and `attributeValueSeq`) for SELECT-type attributes and custom input values paired with standard unit codes for INPUT-type attributes.
2. **Coupang Wing**: Distinguished by string-based key-value pairs categorized as purchase options (exposed as `EXPOSED`, mapped to option-level `vendorItems`) or search options (exposed as `NONE`, mapped to product-level `attributes`).

Previously, Auto-Selp had no automated way to extract high-fidelity product specifications from detail page images (which typically contain the physical specs) or map them automatically to marketplace-native payloads. The pipeline needed to:
- Extract all image URLs from raw HTML detail pages.
- Handle multi-marketplace category schema fetches with Redis caching.
- Align market-neutral Vision LLM extractions to marketplace-specific schemas via structured mappers.
- Maintain decoupled service boundaries across `processor` and `marketplace` services.

## Guidance
Use a modular, pipeline-based architecture integrated into a LangGraph workflow (`extract_attributes` node) combined with dedicated marketplace-specific schema mappers and schema providers:

### 1. Extraction Utility (`detail_image.py`)
Extract image URLs from HTML product detail descriptions or single image URLs cleanly using a fallback regex and BeautifulSoup, allowing the downstream Vision LLM node to fetch and analyze them directly.

### 2. Schema Providers (`naver_schema_provider.py` & `coupang_schema_provider.py`)
Retrieve category-specific attribute requirements from Redis using standard keys like `attr_schema:{market}:{category_id}`. Deserialized schemas utilize shared `AttributeSchema` and `AttributeDef` dataclass models. If the cache is empty, fall back cleanly to empty schemas during testing or retrieve from external APIs, caching them with a 24-hour TTL (86400s).

### 3. Attribute Mappers (`attribute_mappers.py`)
Apply dedicated mapping classes:
* **NaverAttributeMapper**: Matches extracted specifications to Naver's `meta` schema. If a `values` map is present, it formats it as SELECT-type (`{"attributeSeq": ..., "attributeValueSeq": ...}`). Otherwise, it formats it as INPUT-type with standard units (`{"attributeSeq": ..., "attributeRealValue": ..., "attributeRealValueUnitCode": ...}`).
* **CoupangAttributeMapper**: Translates extracted specifications, splitting them into `item_attributes` (exposed options) or `product_attributes` (hidden search attributes) based on their `exposed` metadata.

### 4. LangGraph Integration (`product_processor.py`)
Inject the attribute extraction step into the main processing flow:
* Define a TypedDict state field `mapped_attributes` to propagate mapped configurations.
* Execute the `extract_attributes` node after category mapping and before database persistence, tracking elapsed stage execution times in the database and tracing progress.

### 5. Listing Adapter Payload Generation (`smartstore.py` & `coupang.py`)
Modify marketplace adapters during draft generation to consume mapped attributes from the database:
* SmartStore adapter appends `productAttributes` under `detailAttribute`.
* Coupang adapter sets product-level `attributes` at the root and extends item-level option `attributes`.

## Why This Matters
- **High-Fidelity Specification Extraction**: Bypasses unstable OCR text-parsing on complex detail page images by leveraging Vision LLM directly on parsed image URLs, ensuring accurate dimension and material extraction.
- **Strict Format Alignment**: Resolves critical payload validation failures on external marketplaces by mapping generic LLM-extracted specifications into native formats (IDs for Naver, metadata scopes for Coupang).
- **Reduced API Latency & Load**: Caching category schemas in Redis with a 24-hour TTL cuts external marketplace API call overhead significantly.
- **Architectural Extensibility**: Decoupling the extraction (`processor` service) from listing payload composition (`marketplace` service) makes it straightforward to add support for new marketplaces (e.g., 11st, Gmarket) by creating a matching schema provider, mapper, and listing adapter configuration.

## When to Apply
- When integrating physical product attributes (dimensions, sizes, materials) into automatic draft listings.
- When category schema requirements require translation from raw text to ID mappings or platform-specific scopes.
- When executing complex multi-stage background processing pipelines managed by LangGraph and Celery.

## Examples

### Naver Attribute Mapper (`services/processor/utils/attribute_mappers.py`)
```python
class NaverAttributeMapper:
    def map_attributes(self, specs: dict, schema) -> list[dict]:
        mapped = []
        meta = getattr(schema, 'meta', {})
        
        for key, value in specs.items():
            if key in meta:
                attr_meta = meta[key]
                attr_seq = attr_meta.get("attributeSeq")
                
                # Check if it's a SELECT type (has values dict)
                if "values" in attr_meta and value in attr_meta["values"]:
                    mapped.append({
                        "attributeSeq": attr_seq,
                        "attributeValueSeq": attr_meta["values"][value]
                    })
                # If it's an INPUT type (no values dict)
                elif "values" not in attr_meta:
                    mapped.append({
                        "attributeSeq": attr_seq,
                        "attributeRealValue": str(value),
                        "attributeRealValueUnitCode": attr_meta.get("unitCode", "")
                    })
        return mapped
```

### Coupang Listing Adapter Attribute Injection (`services/marketplace/adapters/coupang.py`)
```python
        # Add product level and item level attributes consumption
        coupang_category = source_snapshot.get("market_categories", {}).get("coupang", {})
        mapped_attrs = coupang_category.get("mapped_attributes", {}) if coupang_category else {}
        
        if mapped_attrs and mapped_attrs.get("coupang_attributes"):
            payload["attributes"] = mapped_attrs["coupang_attributes"].get("product_attributes", [])
            
            item_attrs = mapped_attrs["coupang_attributes"].get("item_attributes", [])
            if item_attrs:
                for item in payload["items"]:
                    if "attributes" not in item:
                        item["attributes"] = []
                    item["attributes"].extend(item_attrs)
```

## Related
- [docs/superpowers/specs/2026-05-29-multi-marketplace-attribute-extraction-design.md](file:///Users/yoonjae/Desktop/auto-selp-ver2/docs/superpowers/specs/2026-05-29-multi-marketplace-attribute-extraction-design.md)
- [docs/superpowers/plans/2026-05-29-multi-marketplace-attribute-extraction-plan.md](file:///Users/yoonjae/Desktop/auto-selp-ver2/docs/superpowers/plans/2026-05-29-multi-marketplace-attribute-extraction-plan.md)
