# Design Specification: Processor API Clients & Auth

## 1. Overview
This specification covers the implementation of authentication modules and API clients for Naver and Coupang within the `Product Processor` service. It also includes a generic exponential backoff utility for handling rate limits (HTTP 429).

## 2. Exponential Backoff Utility
### 2.1 File: `services/processor/utils/backoff.py`
### 2.2 Logic
A decorator `@retry_with_backoff` will be implemented to wrap async API calls.
- **Target Exception**: `httpx.HTTPStatusError` where `response.status_code == 429`.
- **Parameters**:
    - `max_retries`: Maximum number of retry attempts (default: 5).
    - `base_delay`: Initial delay in seconds (default: 1.0).
- **Delay Calculation**: 
    1. Check for `Retry-After` header. If present and numeric, use it.
    2. Otherwise, use $delay = base\_delay \times 2^{attempt}$.
- **Async Safety**: Use `asyncio.sleep` to ensure the event loop is not blocked.

## 3. Naver API Clients
### 3.1 Naver Search Ad API Auth
- **File**: `services/processor/utils/naver_auth.py`
- **Function**: `generate_signature(method: str, uri: str, timestamp: str, secret_key: str) -> str`
- **Algorithm**:
    ```python
    message = timestamp + "." + method + "." + uri
    signature = base64.b64encode(hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()).decode('utf-8')
    ```

### 3.2 Naver Search Ad Client
- **File**: `services/processor/clients/naver_ad_client.py`
- **Endpoint**: `https://api.searchad.naver.com/keywordstool`
- **Headers**:
    - `X-Timestamp`: Current timestamp in milliseconds.
    - `X-API-KEY`: From `settings.NAVER_API_KEY`.
    - `X-Customer`: From `settings.NAVER_CUSTOMER_ID`.
    - `X-Signature`: Generated signature.

### 3.3 Naver Shopping Search Client
- **File**: `services/processor/clients/naver_search_client.py`
- **Endpoint**: `https://openapi.naver.com/v1/search/shop.json`
- **Headers**:
    - `X-Naver-Client-Id`: From `settings.NAVER_CLIENT_ID`.
    - `X-Naver-Client-Secret`: From `settings.NAVER_CLIENT_SECRET`.

## 4. Coupang API Client
### 4.1 Coupang Auth (CEA)
- **File**: `services/processor/utils/coupang_auth.py`
- **Function**: `generate_signature(method: str, path: str, query_string: str, timestamp: str, secret_key: str) -> str`
- **Algorithm**:
    ```python
    message = timestamp + method + path + query_string
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    ```

### 4.2 Coupang Client
- **File**: `services/processor/clients/coupang_client.py`
- **Endpoint**: `https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v1/categorization/predict`
- **Headers**:
    - `Authorization`: `CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={timestamp}, signature={signature}`

## 5. Testing (TDD)
- **Backoff**: Verify that a 429 response triggers retries with increasing delays.
- **Auth Utils**: Unit tests with known inputs/outputs to verify signature correctness.
- **Clients**: Mock `httpx.AsyncClient` calls using `respx` or `pytest-mock` to verify headers, URLs, and error handling.
- **Async Support**: All tests will use `pytest-asyncio`.
