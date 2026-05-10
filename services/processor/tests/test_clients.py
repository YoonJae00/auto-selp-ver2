import pytest
import respx
from httpx import Response
from clients.naver_ad_client import NaverAdClient
from clients.naver_search_client import NaverSearchClient
from clients.coupang_client import CoupangClient

@pytest.mark.asyncio
@respx.mock
async def test_naver_ad_client():
    client = NaverAdClient()
    respx.get("https://api.naver.com/keywordstool").mock(return_value=Response(200, json={"keywordList": []}))
    
    result = await client.get_keyword_stats(["test"])
    assert "keywordList" in result

@pytest.mark.asyncio
@respx.mock
async def test_naver_search_client():
    client = NaverSearchClient()
    respx.get("https://openapi.naver.com/v1/search/shop.json").mock(return_value=Response(200, json={"items": []}))
    
    result = await client.search_shop("test")
    assert "items" in result

@pytest.mark.asyncio
@respx.mock
async def test_coupang_client():
    client = CoupangClient()
    respx.post("https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v1/categorization/predict").mock(
        return_value=Response(200, json={"data": {"predictedCategoryId": 1001}})
    )
    
    result = await client.predict_category("test product")
    assert result["data"]["predictedCategoryId"] == 1001
