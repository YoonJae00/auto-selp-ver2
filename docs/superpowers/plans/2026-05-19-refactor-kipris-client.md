# Refactor KiprisClient to use MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `KiprisClient` to communicate with the KIPRIS MCP server instead of a placeholder implementation.

**Architecture:** Use `httpx.AsyncClient` to call the KIPRIS MCP server's `/tools/call` endpoint. The client will send a JSON payload specifying the `trademark_search` tool and parse the results to determine if a trademark exists.

**Tech Stack:** Python, FastAPI (context), httpx, pytest, respx.

---

### Task 1: Write failing test for KiprisClient

**Files:**
- Modify: `services/processor/tests/test_clients.py`

- [ ] **Step 1: Add a test case for KiprisClient in test_clients.py**

```python
import pytest
import respx
from httpx import Response
from clients.kipris_client import KiprisClient

@pytest.mark.asyncio
@respx.mock
async def test_kipris_client_search_success():
    client = KiprisClient()
    mock_response = {
        "content": [
            {
                "type": "text",
                "text": '{"total_count": 1, "items": [{"title": "Test Trademark", "application_number": "12345"}]}'
            }
        ]
    }
    respx.post("http://kipris-mcp:8080/tools/call").mock(
        return_value=Response(200, json=mock_response)
    )
    
    result = await client.search_trademark("test")
    assert result["exists"] is True
    assert result["title"] == "Test Trademark"
    assert "application_number" in result["details"][0]

@pytest.mark.asyncio
@respx.mock
async def test_kipris_client_search_no_results():
    client = KiprisClient()
    mock_response = {
        "content": [
            {
                "type": "text",
                "text": '{"total_count": 0, "items": []}'
            }
        ]
    }
    respx.post("http://kipris-mcp:8080/tools/call").mock(
        return_value=Response(200, json=mock_response)
    )
    
    result = await client.search_trademark("unique_word")
    assert result["exists"] is False
    assert result["title"] == ""
    assert result["details"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/processor/tests/test_clients.py -k test_kipris_client`
Expected: FAIL (AttributeError: 'KiprisClient' object has no attribute 'search_trademark' or similar)

- [ ] **Step 3: Commit**

```bash
git add services/processor/tests/test_clients.py
git commit -m "test: add failing tests for KiprisClient MCP integration"
```

### Task 2: Implement KiprisClient MCP communication

**Files:**
- Modify: `services/processor/clients/kipris_client.py`

- [ ] **Step 1: Update KiprisClient with MCP call logic**

```python
import httpx
import logging
import json
from config import settings
from utils.backoff import retry_with_backoff

logger = logging.getLogger(__name__)

class KiprisClient:
    """
    KIPRIS MCP 서버 연동 클라이언트
    """
    def __init__(self):
        self.base_url = "http://kipris-mcp:8080"

    @retry_with_backoff(max_retries=2)
    async def search_trademark(self, word: str) -> dict:
        """
        KIPRIS MCP 서버의 trademark_search 도구를 호출하여 상표권 검색
        """
        url = f"{self.base_url}/tools/call"
        payload = {
            "name": "trademark_search",
            "arguments": {
                "keyword": word,
                "docs_count": 1,
                "desc_sort": True
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # MCP response format: {"content": [{"type": "text", "text": "..."}]}
                if "content" in data and len(data["content"]) > 0:
                    text_content = data["content"][0].get("text", "{}")
                    result_data = json.loads(text_content)
                    
                    items = result_data.get("items", [])
                    total_count = result_data.get("total_count", 0)
                    
                    exists = total_count > 0 or len(items) > 0
                    title = items[0].get("title", "") if exists else ""
                    
                    return {
                        "exists": exists,
                        "title": title,
                        "details": items
                    }
                
                return {"exists": False, "title": "", "details": []}
                
        except Exception as e:
            logger.error(f"KIPRIS MCP call failed for {word}: {e}")
            return {"exists": False, "title": "", "details": [], "error": str(e)}

    # Keep check_trademark for backward compatibility if needed, or refactor usages
    async def check_trademark(self, word: str) -> bool:
        result = await self.search_trademark(word)
        return result["exists"]
```

- [ ] **Step 2: Run tests to verify it passes**

Run: `pytest services/processor/tests/test_clients.py -k test_kipris_client`
Expected: PASS

- [ ] **Step 3: Refactor and clean up**

Ensure `check_trademark` is correctly using `search_trademark` if it's still needed by other parts of the system.

- [ ] **Step 4: Commit**

```bash
git add services/processor/clients/kipris_client.py
git commit -m "feat(processor): integrate kipris client with MCP server"
```

### Task 3: Final Verification

- [ ] **Step 1: Run all client tests**

Run: `pytest services/processor/tests/test_clients.py`
Expected: ALL PASS

- [ ] **Step 2: Check for any linting issues (optional but good)**

Run: `flake8 services/processor/clients/kipris_client.py` (or similar)
