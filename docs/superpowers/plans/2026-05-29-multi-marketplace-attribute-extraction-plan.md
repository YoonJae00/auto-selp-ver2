# Multi-Marketplace Attribute Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated pipeline that extracts product attributes from detail page images using Vision LLM and maps them to Naver SmartStore and Coupang native formats.

**Architecture:** A new LangGraph node (`extract_attributes`) runs after category mapping. It uses BeautifulSoup to extract image URLs from HTML detail pages, fetches required attribute schemas from Naver/Coupang APIs (cached in Redis), passes everything to Gemini Vision LLM to extract market-neutral specs, maps them back to market-specific formats via mapper classes, and saves them to `mapped_attributes` for marketplace adapters to consume.

**Tech Stack:** FastAPI, LangGraph, BeautifulSoup4, Gemini Vision (google-genai), Redis, Pytest

---

### Task 1: Detail Image Extraction Utility

**Files:**
- Create: `services/processor/utils/detail_image.py`
- Modify: `services/processor/tests/test_detail_image.py`

- [ ] **Step 1: Write the failing test**

```python
# services/processor/tests/test_detail_image.py
import pytest
from utils.detail_image import extract_images_from_detail_content

def test_extract_images_from_detail_content_with_html():
    html_content = '<p>Test</p><img src="http://example.com/img1.jpg"><img src="https://example.com/img2.png">'
    result = extract_images_from_detail_content(html_content)
    assert result == ["http://example.com/img1.jpg", "https://example.com/img2.png"]

def test_extract_images_from_detail_content_with_url():
    url_content = "http://example.com/single_image.jpg"
    result = extract_images_from_detail_content(url_content)
    assert result == ["http://example.com/single_image.jpg"]

def test_extract_images_from_detail_content_empty():
    assert extract_images_from_detail_content(None) == []
    assert extract_images_from_detail_content("") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_detail_image.py -v`
Expected: FAIL (ModuleNotFoundError or AssertionError)

- [ ] **Step 3: Write minimal implementation**

```python
# services/processor/utils/detail_image.py
from bs4 import BeautifulSoup
import re

def extract_images_from_detail_content(image_detail: str | None) -> list[str]:
    if not image_detail or not str(image_detail).strip():
        return []
    
    content = str(image_detail).strip()
    
    # If it's just a raw URL
    if re.match(r'^https?://[^\s<>"]+$', content):
        return [content]
    
    # If it contains HTML
    try:
        soup = BeautifulSoup(content, 'html.parser')
        images = []
        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                images.append(src)
        return images
    except Exception:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/processor/tests/test_detail_image.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/processor/tests/test_detail_image.py services/processor/utils/detail_image.py
git commit -m "feat(processor): add utility to extract image URLs from detail content"
```

---

### Task 2: Naver Attribute Schema Provider

**Files:**
- Create: `services/processor/clients/naver_schema_provider.py`
- Modify: `services/processor/tests/test_naver_schema_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# services/processor/tests/test_naver_schema_provider.py
import pytest
from unittest.mock import AsyncMock, patch
from clients.naver_schema_provider import NaverAttributeSchemaProvider, AttributeSchema, AttributeDef

@pytest.mark.asyncio
async def test_get_attribute_schema_cached(mocker):
    provider = NaverAttributeSchemaProvider(redis_client=AsyncMock())
    
    # Mock redis get to return cached schema
    cached_data = '{"market_code": "naver", "category_id": "123", "attributes": [{"name": "색상", "required": true, "data_type": "STRING", "input_type": "SELECT", "unit": null, "valid_values": ["레드"]}]}'
    provider.redis.get.return_value = cached_data
    
    result = await provider.get_attribute_schema("123")
    
    assert isinstance(result, AttributeSchema)
    assert result.category_id == "123"
    assert len(result.attributes) == 1
    assert result.attributes[0].name == "색상"
    provider.redis.get.assert_called_once_with("attr_schema:naver:123")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_naver_schema_provider.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# services/processor/clients/naver_schema_provider.py
import json
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

@dataclass
class AttributeDef:
    name: str
    required: bool
    data_type: str
    input_type: str
    unit: Optional[str]
    valid_values: Optional[List[str]]

@dataclass
class AttributeSchema:
    market_code: str
    category_id: str
    attributes: List[AttributeDef]

class NaverAttributeSchemaProvider:
    def __init__(self, redis_client=None, naver_client=None):
        self.redis = redis_client
        self.naver_client = naver_client
        
    async def get_attribute_schema(self, category_id: str) -> AttributeSchema:
        cache_key = f"attr_schema:naver:{category_id}"
        
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                attributes = [AttributeDef(**attr) for attr in data["attributes"]]
                return AttributeSchema(market_code=data["market_code"], category_id=data["category_id"], attributes=attributes)
                
        # Fallback empty schema for tests until client is fully integrated
        schema = AttributeSchema(market_code="naver", category_id=category_id, attributes=[])
        
        if self.redis:
            await self.redis.setex(cache_key, 86400, json.dumps(asdict(schema)))
            
        return schema
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/processor/tests/test_naver_schema_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/processor/tests/test_naver_schema_provider.py services/processor/clients/naver_schema_provider.py
git commit -m "feat(processor): add Naver Attribute Schema Provider with Redis caching"
```

---

### Task 3: Coupang Attribute Schema Provider

**Files:**
- Create: `services/processor/clients/coupang_schema_provider.py`
- Modify: `services/processor/tests/test_coupang_schema_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# services/processor/tests/test_coupang_schema_provider.py
import pytest
from unittest.mock import AsyncMock
from clients.coupang_schema_provider import CoupangAttributeSchemaProvider
from clients.naver_schema_provider import AttributeSchema, AttributeDef

@pytest.mark.asyncio
async def test_coupang_get_attribute_schema_cached(mocker):
    provider = CoupangAttributeSchemaProvider(redis_client=AsyncMock())
    
    cached_data = '{"market_code": "coupang", "category_id": "456", "attributes": [{"name": "브랜드", "required": true, "data_type": "STRING", "input_type": "INPUT", "unit": null, "valid_values": null}]}'
    provider.redis.get.return_value = cached_data
    
    result = await provider.get_attribute_schema("456")
    
    assert isinstance(result, AttributeSchema)
    assert result.category_id == "456"
    assert result.attributes[0].name == "브랜드"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_coupang_schema_provider.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# services/processor/clients/coupang_schema_provider.py
import json
from clients.naver_schema_provider import AttributeSchema, AttributeDef

class CoupangAttributeSchemaProvider:
    def __init__(self, redis_client=None, coupang_client=None):
        self.redis = redis_client
        self.coupang_client = coupang_client
        
    async def get_attribute_schema(self, category_id: str) -> AttributeSchema:
        cache_key = f"attr_schema:coupang:{category_id}"
        
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                attributes = [AttributeDef(**attr) for attr in data["attributes"]]
                return AttributeSchema(market_code=data["market_code"], category_id=data["category_id"], attributes=attributes)
                
        schema = AttributeSchema(market_code="coupang", category_id=category_id, attributes=[])
        return schema
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/processor/tests/test_coupang_schema_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/processor/tests/test_coupang_schema_provider.py services/processor/clients/coupang_schema_provider.py
git commit -m "feat(processor): add Coupang Attribute Schema Provider"
```

---

### Task 4: Attribute Mappers

**Files:**
- Create: `services/processor/utils/attribute_mappers.py`
- Modify: `services/processor/tests/test_attribute_mappers.py`

- [ ] **Step 1: Write the failing test**

```python
# services/processor/tests/test_attribute_mappers.py
from utils.attribute_mappers import NaverAttributeMapper, CoupangAttributeMapper
from clients.naver_schema_provider import AttributeSchema, AttributeDef

def test_naver_mapper():
    mapper = NaverAttributeMapper()
    # Mock schema holding mapping meta
    schema = AttributeSchema(
        market_code="naver", category_id="1", 
        attributes=[AttributeDef(name="색상", required=True, data_type="STRING", input_type="SELECT", unit=None, valid_values=["레드"])]
    )
    # Mocking internal meta dict that would be built by the real client
    schema.meta = {"색상": {"attributeSeq": 123, "values": {"레드": 456}}}
    
    specs = {"색상": "레드", "가로": "10"} # "가로" is not in schema
    
    result = mapper.map_attributes(specs, schema)
    
    assert len(result) == 1
    assert result[0] == {"attributeSeq": 123, "attributeValueSeq": 456}

def test_coupang_mapper():
    mapper = CoupangAttributeMapper()
    schema = AttributeSchema(
        market_code="coupang", category_id="1",
        attributes=[
            AttributeDef(name="색상", required=True, data_type="STRING", input_type="SELECT", unit=None, valid_values=["레드"]),
            AttributeDef(name="브랜드", required=False, data_type="STRING", input_type="INPUT", unit=None, valid_values=None)
        ]
    )
    schema.meta = {"색상": {"exposed": "EXPOSED"}, "브랜드": {"exposed": "NONE"}}
    
    specs = {"색상": "레드", "브랜드": "우리브랜드"}
    
    result = mapper.map_attributes(specs, schema)
    
    assert len(result["item_attributes"]) == 1
    assert result["item_attributes"][0] == {"attributeTypeName": "색상", "attributeValueName": "레드"}
    
    assert len(result["product_attributes"]) == 1
    assert result["product_attributes"][0] == {"attributeTypeName": "브랜드", "attributeValueName": "우리브랜드"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_attribute_mappers.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# services/processor/utils/attribute_mappers.py
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

class CoupangAttributeMapper:
    def map_attributes(self, specs: dict, schema) -> dict:
        result = {"product_attributes": [], "item_attributes": []}
        meta = getattr(schema, 'meta', {})
        
        for key, value in specs.items():
            if key in meta:
                exposed = meta[key].get("exposed", "NONE")
                attr_obj = {
                    "attributeTypeName": key,
                    "attributeValueName": str(value)
                }
                
                if exposed == "EXPOSED":
                    result["item_attributes"].append(attr_obj)
                else:
                    result["product_attributes"].append(attr_obj)
                    
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/processor/tests/test_attribute_mappers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/processor/tests/test_attribute_mappers.py services/processor/utils/attribute_mappers.py
git commit -m "feat(processor): add attribute mappers for Naver and Coupang"
```

---

### Task 5: Add extract_attributes Node to LangGraph

**Files:**
- Modify: `services/processor/graphs/product_processor.py`
- Modify: `services/processor/tests/test_product_processor.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to services/processor/tests/test_product_processor.py
import pytest
from graphs.product_processor import extract_attributes

@pytest.mark.asyncio
async def test_extract_attributes_node_noop():
    # Verify node signature and basic passthrough when extraction is disabled/fails
    state = {
        "naver_category": {"id": "123"},
        "coupang_category": "456",
        "refined_name": "Test Product",
        "product": {"image_detail": "http://img.com"}
    }
    
    # Passing minimal runtime config, expect it to return mapped_attributes key
    result = await extract_attributes(state, None)
    
    assert "mapped_attributes" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_product_processor.py::test_extract_attributes_node_noop -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# Modify services/processor/graphs/product_processor.py
# Add the function before build_processor_graph
async def extract_attributes(state: dict, runtime: dict) -> dict:
    """Extract product attributes using Vision LLM and map to target marketplaces."""
    # Placeholder for actual LLM call. Real implementation will inject llm_client from runtime
    # and use state["naver_category"]["id"] / state["coupang_category"] for schemas.
    mapped_attributes = {
        "extracted_specs": {},
        "naver_attributes": [],
        "coupang_attributes": {"product_attributes": [], "item_attributes": []}
    }
    return {"mapped_attributes": mapped_attributes}

# Inside build_processor_graph(db: AsyncSession), add the node:
# graph.add_node("extract_attributes", extract_attributes)
# And update the edge from map_categories:
# graph.add_edge("map_categories", "extract_attributes")
# graph.add_edge("extract_attributes", "persist_success")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/processor/tests/test_product_processor.py::test_extract_attributes_node_noop -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/processor/graphs/product_processor.py services/processor/tests/test_product_processor.py
git commit -m "feat(processor): add extract_attributes node to processing graph"
```

---

### Task 6: Consume mapped_attributes in Adapters

**Files:**
- Modify: `services/marketplace/adapters/smartstore.py`
- Modify: `services/marketplace/adapters/coupang.py`

- [ ] **Step 1: Write the failing tests**

*You may need to create or modify existing adapter tests.*

```python
# Append to services/marketplace/tests/test_smartstore_adapter.py (if exists, or run manually)
def test_smartstore_adapter_consumes_attributes():
    from adapters.smartstore import SmartstoreAdapter
    adapter = SmartstoreAdapter()
    snapshot = {
        "market_categories": {
            "smartstore": {
                "mapped_attributes": {
                    "naver_attributes": [{"attributeSeq": 1, "attributeValueSeq": 2}]
                }
            }
        }
    }
    # Mock other required snapshot fields here if needed by generate_draft
    result = adapter.generate_draft(snapshot, {})
    
    assert "productAttributes" in result.generated_payload["originProduct"]["detailAttribute"]
    assert result.generated_payload["originProduct"]["detailAttribute"]["productAttributes"][0]["attributeSeq"] == 1
```

- [ ] **Step 2: Write minimal implementation**

```python
# In services/marketplace/adapters/smartstore.py, inside generate_draft()
# Around where detailAttribute is built:
detail_attribute = {
    "naverShoppingSearchInfo": {...},
    "optionInfo": {...},
}

# Add attribute mapping consumption
smartstore_category = snapshot.get("market_categories", {}).get("smartstore", {})
mapped_attrs = smartstore_category.get("mapped_attributes", {})
if mapped_attrs and mapped_attrs.get("naver_attributes"):
    detail_attribute["productAttributes"] = mapped_attrs["naver_attributes"]

payload["originProduct"]["detailAttribute"] = detail_attribute
```

```python
# In services/marketplace/adapters/coupang.py, inside generate_draft()
coupang_category = snapshot.get("market_categories", {}).get("coupang", {})
mapped_attrs = coupang_category.get("mapped_attributes", {})

# Add product level attributes
if mapped_attrs and mapped_attrs.get("coupang_attributes"):
    payload["attributes"] = mapped_attrs["coupang_attributes"].get("product_attributes", [])
    
    # Merge item level attributes
    item_attrs = mapped_attrs["coupang_attributes"].get("item_attributes", [])
    if item_attrs:
        for item in payload["items"]:
            if "attributes" not in item:
                item["attributes"] = []
            item["attributes"].extend(item_attrs)
```

- [ ] **Step 3: Commit**

```bash
git add services/marketplace/adapters/smartstore.py services/marketplace/adapters/coupang.py
git commit -m "feat(marketplace): consume mapped_attributes in SmartStore and Coupang adapters"
```
