import httpx
from config import settings
from utils.coupang_auth import get_coupang_auth_header
from utils.backoff import retry_with_backoff

class CoupangClient:
    def __init__(self):
        self.base_url = "https://api-gateway.coupang.com"

    @retry_with_backoff(max_retries=3)
    async def predict_category(self, product_name: str, brand: str = ""):
        """
        쿠팡 카테고리 예측 API
        """
        path = "/v2/providers/openapi/apis/api/v1/categorization/predict"
        method = "POST"
        
        headers = get_coupang_auth_header(method, path)
        headers["Content-Type"] = "application/json"
        
        body = {
            "productName": product_name,
            "brand": brand,
            "attributes": {}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=body,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
