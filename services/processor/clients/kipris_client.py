import httpx
import logging
from config import settings
from utils.backoff import retry_with_backoff

logger = logging.getLogger(__name__)

class KiprisClient:
    """
    KIPRIS MCP 서버 또는 직접 API 연동 클라이언트
    """
    def __init__(self):
        self.api_key = settings.KIPRIS_API_KEY
        self.base_url = "http://kipris-mcp:8080" # MCP 컨테이너 주소 가정

    @retry_with_backoff(max_retries=2)
    async def check_trademark(self, word: str) -> bool:
        """
        상표권 존재 여부 확인 (True: 존재함/사용불가, False: 없음/사용가능)
        """
        # 실제 KIPRIS Open API 호출 로직 (또는 MCP 통신)
        # 여기서는 기본적으로 API 호출 형태 예시 작성
        try:
            params = {
                "ServiceKey": self.api_key,
                "title": word,
                "resultType": "json"
            }
            # KIPRIS API 특성상 XML일 수 있으나 JSON 요청 가정
            async with httpx.AsyncClient() as client:
                # url = "http://plus.kipris.or.kr/openapi/rest/trademarkInfoSearchService/freeSearchInfo"
                # response = await client.get(url, params=params)
                # ...
                return False # 임시 mock
        except Exception as e:
            logger.error(f"KIPRIS check failed for {word}: {e}")
            return False
