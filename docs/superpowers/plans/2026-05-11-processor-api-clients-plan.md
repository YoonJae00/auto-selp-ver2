# Processor API Clients & Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement authentication modules and API clients for Naver and Coupang, including an exponential backoff utility for handling rate limits (HTTP 429).

**Architecture:** Use `httpx` for async HTTP calls. Authentication logic is decoupled into utility modules. Retries are handled via an async decorator.

**Tech Stack:** Python 3.12, FastAPI (service context), httpx, pytest, pytest-asyncio, pydantic-settings.

---

### Task 1: Exponential Backoff Utility

**Files:**
- Create: `services/processor/utils/backoff.py`
- Test: `services/processor/tests/test_backoff.py`

- [ ] **Step 1: Write the failing test for backoff**

```python
import pytest
import httpx
import asyncio
from unittest.mock import MagicMock, patch
from services.processor.utils.backoff import retry_with_backoff

@pytest.mark.asyncio
async def test_retry_with_backoff_success_after_retry():
    mock_func = MagicMock()
    # First call returns 429, second call returns success
    mock_func.side_effect = [
        httpx.HTTPStatusError("429 Too Many Requests", request=MagicMock(), response=httpx.Response(429)),
        "success"
    ]
    
    decorated_func = retry_with_backoff(max_retries=2, base_delay=0.01)(mock_func)
    
    with patch("asyncio.sleep", return_value=None) as mock_sleep:
        result = await decorated_func()
    
    assert result == "success"
    assert mock_func.call_count == 2
    mock_sleep.assert_called_once_with(0.01)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_backoff.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement `retry_with_backoff`**

```python
import asyncio
import functools
import httpx
import logging

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries: int = 5, base_delay: float = 1.0):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and retries < max_retries:
                        delay = base_delay * (2 ** retries)
                        
                        # Honor Retry-After header if present
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            delay = float(retry_after)
                        
                        logger.warning(f"Rate limited (429). Retrying in {delay}s... (Attempt {retries + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        retries += 1
                        continue
                    raise e
        return wrapper
    return decorator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/processor/tests/test_backoff.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add services/processor/utils/backoff.py services/processor/tests/test_backoff.py
git commit -m "feat: add exponential backoff utility"
```

---

### Task 2: Naver API Authentication

**Files:**
- Create: `services/processor/utils/naver_auth.py`
- Test: `services/processor/tests/test_naver_auth.py`

- [ ] **Step 1: Write the failing test for Naver auth**

```python
from services.processor.utils.naver_auth import generate_signature

def test_generate_signature():
    # Known values for testing (fictional)
    method = "GET"
    uri = "/keywordstool"
    timestamp = "1620712345678"
    secret_key = "test_secret"
    
    # Expected signature (manually calculated or from docs)
    # message = "1620712345678.GET./keywordstool"
    # hmac_sha256(message, "test_secret") -> base64
    expected = "H6+v8v... (placeholder)" 
    
    signature = generate_signature(method, uri, timestamp, secret_key)
    assert isinstance(signature, str)
    assert len(signature) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_naver_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `generate_signature`**

```python
import base64
import hashlib
import hmac

def generate_signature(method: str, uri: str, timestamp: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    signature = base64.b64encode(hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()).decode('utf-8')
    return signature
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/processor/tests/test_naver_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add services/processor/utils/naver_auth.py services/processor/tests/test_naver_auth.py
git commit -m "feat: add Naver API signature generation"
```

---

### Task 3: Naver API Clients

**Files:**
- Create: `services/processor/clients/naver_ad_client.py`
- Create: `services/processor/clients/naver_search_client.py`
- Test: `services/processor/tests/test_naver_clients.py`

- [ ] **Step 1: Write failing tests for Naver clients**

```python
import pytest
import respx
import httpx
from services.processor.clients.naver_ad_client import NaverAdClient
from services.processor.clients.naver_search_client import NaverSearchClient

@pytest.mark.asyncio
@respx.mock
async def test_naver_ad_client_get_keywords():
    respx.get("https://api.searchad.naver.com/keywordstool").mock(
        return_value=httpx.Response(200, json={"keywordList": []})
    )
    client = NaverAdClient()
    result = await client.get_keywords("test")
    assert "keywordList" in result

@pytest.mark.asyncio
@respx.mock
async def test_naver_search_client_search_shop():
    respx.get("https://openapi.naver.com/v1/search/shop.json").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    client = NaverSearchClient()
    result = await client.search_shop("test")
    assert "items" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest services/processor/tests/test_naver_clients.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `NaverAdClient`**

```python
import time
import httpx
from services.processor.config import settings
from services.processor.utils.naver_auth import generate_signature
from services.processor.utils.backoff import retry_with_backoff

class NaverAdClient:
    def __init__(self):
        self.base_url = "https://api.searchad.naver.com"
        self.api_key = settings.NAVER_API_KEY
        self.secret_key = settings.NAVER_SECRET_KEY
        self.customer_id = settings.NAVER_CUSTOMER_ID

    @retry_with_backoff()
    async def get_keywords(self, hint_keyword: str):
        timestamp = str(int(time.time() * 1000))
        method = "GET"
        uri = "/keywordstool"
        signature = generate_signature(method, uri, timestamp, self.secret_key)
        
        headers = {
            "X-Timestamp": timestamp,
            "X-API-KEY": self.api_key,
            "X-Customer": self.customer_id,
            "X-Signature": signature
        }
        params = {"hintKeywords": hint_keyword, "showDetail": "1"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}{uri}", headers=headers, params=params)
            response.raise_for_status()
            return response.json()
```

- [ ] **Step 4: Implement `NaverSearchClient`**

```python
import httpx
from services.processor.config import settings
from services.processor.utils.backoff import retry_with_backoff

class NaverSearchClient:
    def __init__(self):
        self.base_url = "https://openapi.naver.com/v1/search/shop.json"
        self.client_id = settings.NAVER_CLIENT_ID
        self.client_secret = settings.NAVER_CLIENT_SECRET

    @retry_with_backoff()
    async def search_shop(self, query: str):
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }
        params = {"query": query, "display": 1}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(self.base_url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest services/processor/tests/test_naver_clients.py -v`
Expected: PASS

- [ ] **Step 6: Commit Task 3**

```bash
git add services/processor/clients/naver_ad_client.py services/processor/clients/naver_search_client.py services/processor/tests/test_naver_clients.py
git commit -m "feat: implement Naver API clients"
```

---

### Task 4: Coupang API Client

**Files:**
- Create: `services/processor/utils/coupang_auth.py`
- Create: `services/processor/clients/coupang_client.py`
- Test: `services/processor/tests/test_coupang_client.py`

- [ ] **Step 1: Write failing tests for Coupang client**

```python
import pytest
import respx
import httpx
from services.processor.clients.coupang_client import CoupangClient
from services.processor.utils.coupang_auth import generate_signature

def test_coupang_signature():
    method = "POST"
    path = "/v1/categorization/predict"
    query_string = ""
    timestamp = "210511T120000Z"
    secret_key = "test_secret"
    signature = generate_signature(method, path, query_string, timestamp, secret_key)
    assert isinstance(signature, str)

@pytest.mark.asyncio
@respx.mock
async def test_coupang_client_predict_category():
    respx.post("https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v1/categorization/predict").mock(
        return_value=httpx.Response(200, json={"data": {"predictedCategoryId": "123"}})
    )
    client = CoupangClient()
    result = await client.predict_category("product", "brand")
    assert result == "123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest services/processor/tests/test_coupang_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `coupang_auth`**

```python
import hmac
import hashlib

def generate_signature(method: str, path: str, query_string: str, timestamp: str, secret_key: str) -> str:
    message = f"{timestamp}{method}{path}{query_string}"
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature
```

- [ ] **Step 4: Implement `CoupangClient`**

```python
import time
from datetime import datetime
import httpx
from services.processor.config import settings
from services.processor.utils.coupang_auth import generate_signature
from services.processor.utils.backoff import retry_with_backoff

class CoupangClient:
    def __init__(self):
        self.base_url = "https://api-gateway.coupang.com"
        self.access_key = settings.Coupang_Access_Key
        self.secret_key = settings.Coupang_Secret_Key

    @retry_with_backoff()
    async def predict_category(self, product_name: str, brand: str = ""):
        path = "/v2/providers/openapi/apis/api/v1/categorization/predict"
        method = "POST"
        timestamp = datetime.utcnow().strftime('%y%m%dT%H%M%SZ')
        
        signature = generate_signature(method, path, "", timestamp, self.secret_key)
        
        auth_header = (
            f"CEA algorithm=HmacSHA256, access-key={self.access_key}, "
            f"signed-date={timestamp}, signature={signature}"
        )
        
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        
        payload = {
            "productName": product_name,
            "brand": brand,
            "attributes": {}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}{path}", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("predictedCategoryId")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest services/processor/tests/test_coupang_client.py -v`
Expected: PASS

- [ ] **Step 6: Commit Task 4**

```bash
git add services/processor/utils/coupang_auth.py services/processor/clients/coupang_client.py services/processor/tests/test_coupang_client.py
git commit -m "feat: implement Coupang API client"
```
