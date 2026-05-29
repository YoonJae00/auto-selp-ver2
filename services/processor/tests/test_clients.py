import pytest
import respx
from httpx import Response
from clients.naver_ad_client import NaverAdClient
from clients.naver_search_client import NaverSearchClient
from clients.coupang_client import CoupangClient
from clients.kipris_client import KiprisClient

@pytest.mark.asyncio
@respx.mock
async def test_naver_ad_client():
    client = NaverAdClient()
    respx.get(url__regex=r".*/keywordstool.*").mock(return_value=Response(200, json={"keywordList": []}))
    
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
