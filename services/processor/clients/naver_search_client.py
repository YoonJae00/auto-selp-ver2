import httpx
from config import settings
from utils.backoff import retry_with_backoff

class NaverSearchClient:
    def __init__(self):
        self.base_url = "https://openapi.naver.com/v1/search"

    @retry_with_backoff(max_retries=3)
    async def search_shop(self, query: str):
        """
        네이버 쇼핑 검색 API: 상품명 기반 카테고리 경로 조회
        """
        uri = "/shop.json"
        headers = {
            "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET
        }
        params = {
            "query": query,
            "display": 1
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{uri}",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
