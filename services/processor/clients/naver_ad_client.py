import httpx
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
        uri = "/keywordstool"
        method = "GET"
        params = {
            "hintKeywords": keywords[:5],  # 한 번에 최대 5개
            "showDetail": "1"
        }
        
        headers = get_naver_ad_header(method, uri)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{uri}",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
