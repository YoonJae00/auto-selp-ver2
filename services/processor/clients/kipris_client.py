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
                "word": word,
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if "content" in data and len(data["content"]) > 0:
                    text_content = data["content"][0].get("text", "")
                    
                    if not text_content or "there is no result" in text_content.lower():
                        return {"exists": False, "title": "", "details": []}
                        
                    try:
                        result_data = json.loads(text_content)
                        items = result_data.get("items", [])
                        total_count = result_data.get("total_count", 0)
                    except json.JSONDecodeError:
                        # Handle markdown table
                        items = []
                        lines = [line.strip() for line in text_content.strip().split('\n') if line.strip().startswith('|')]
                        if len(lines) > 2:
                            headers = [h.strip() for h in lines[0].split('|')[1:-1]]
                            for line in lines[2:]:
                                values = [v.strip() for v in line.split('|')[1:-1]]
                                items.append(dict(zip(headers, values)))
                        
                        total_count = len(items)

                    exists = total_count > 0 or len(items) > 0
                    
                    # TrademarkName is the column used by mcp_kipris
                    title = ""
                    if exists and items:
                        title = items[0].get("title", "") or items[0].get("TrademarkName", "")
                    
                    return {
                        "exists": exists,
                        "title": title,
                        "details": items
                    }
                
        except Exception as e:
            logger.error(f"KIPRIS MCP call failed for {word}: {e}")
            return {"exists": False, "title": "", "details": [], "error": str(e)}

    async def check_trademark(self, word: str) -> bool:
        """
        상표권 존재 여부 확인 (True: 존재함/사용불가, False: 없음/사용가능)
        """
        result = await self.search_trademark(word)
        return result["exists"]
