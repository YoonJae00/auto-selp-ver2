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

    async def check_trademark(self, word: str) -> bool:
        """
        상표권 존재 여부 확인 (True: 존재함/사용불가, False: 없음/사용가능)
        """
        result = await self.search_trademark(word)
        return result["exists"]
