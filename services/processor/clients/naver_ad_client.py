import httpx
import urllib.parse
from config import settings
from utils.naver_auth import get_naver_ad_header
from utils.backoff import retry_with_backoff

class NaverAdClient:
    def __init__(self):
        self.base_url = settings.NAVER_API_BASE_URL

    @retry_with_backoff(max_retries=3)
    async def get_keyword_stats(self, keywords: list[str]):
        """
        네이버 검색광고 API: 키워드별 검색량 및 경쟁도 조회
        """
        method = "GET"
        # hintKeywords=A,B,C format, must be URL encoded for signature
        keywords_str = ",".join(keywords[:5])
        encoded_keywords = urllib.parse.quote(keywords_str)
        uri = f"/keywordstool?hintKeywords={encoded_keywords}&showDetail=1"
        
        headers = get_naver_ad_header(method, uri)
        
        async with httpx.AsyncClient() as client:
            # Note: headers["X-Signature"] is based on the encoded URI
            response = await client.get(
                f"{self.base_url}{uri}",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
