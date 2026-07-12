import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from clients.gemini_client import GeminiClient

@pytest.mark.asyncio
async def test_gemini_refine_product_name_success():
    with patch("google.generativeai.GenerativeModel") as MockModel:
        mock_response = MagicMock()
        mock_response.text = '{"refined_name": "정제된 상품명"}'
        
        # AsyncMock for generate_content_async
        MockModel.return_value.generate_content_async = AsyncMock(return_value=mock_response)
        
        client = GeminiClient()
        result = await client.refine_product_name("원본 상품명 10p !!")
        
        assert result == "정제된 상품명"
        MockModel.return_value.generate_content_async.assert_called_once()

@pytest.mark.asyncio
async def test_gemini_refine_product_name_retry_success():
    with patch("google.generativeai.GenerativeModel") as MockModel:
        # 1st fail, 2nd success
        mock_response_fail = MagicMock()
        mock_response_fail.text = "invalid json"
        
        mock_response_success = MagicMock()
        mock_response_success.text = '{"refined_name": "두번째 시도 성공"}'
        
        MockModel.return_value.generate_content_async = AsyncMock(
            side_effect=[mock_response_fail, mock_response_success]
        )
        
        client = GeminiClient()
        result = await client.refine_product_name("테스트 상품")
        
        assert result == "두번째 시도 성공"
        assert MockModel.return_value.generate_content_async.call_count == 2

@pytest.mark.asyncio
async def test_gemini_refine_product_name_all_fail_fallback():
    with patch("google.generativeai.GenerativeModel") as MockModel:
        MockModel.return_value.generate_content_async = AsyncMock(side_effect=Exception("API Error"))
        
        client = GeminiClient()
        original = "원본 상품명"
        result = await client.refine_product_name(original)
        
        # All attempts fail, should return original
        assert result == original
        assert MockModel.return_value.generate_content_async.call_count == 3

@pytest.mark.asyncio
async def test_gemini_extract_product_attributes_success():
    with patch("google.generativeai.GenerativeModel") as MockModel:
        mock_response = MagicMock()
        mock_response.text = '{"색상": "레드", "사이즈": "L"}'
        
        MockModel.return_value.generate_content_async = AsyncMock(return_value=mock_response)
        
        client = GeminiClient()
        client._download_image = AsyncMock(return_value=b"fake_image_bytes")
        
        result = await client.extract_product_attributes(
            refined_name="멋진 티셔츠",
            image_urls=["http://example.com/img1.jpg"],
            attributes=[{"name": "색상"}, {"name": "사이즈"}]
        )
        
        assert result == {"색상": "레드", "사이즈": "L"}
        client._download_image.assert_called_once_with("http://example.com/img1.jpg")
        MockModel.return_value.generate_content_async.assert_called_once()


@pytest.mark.asyncio
async def test_gemini_smartstore_candidates_json_and_failure_fallback():
    with patch("google.generativeai.GenerativeModel") as MockModel:
        response = MagicMock()
        response.text = '```json\n{"candidates": ["후보 하나", "후보 둘", "후보 셋"]}\n```'
        generate = MockModel.return_value.generate_content_async = AsyncMock(return_value=response)
        client = GeminiClient()

        assert await client.generate_smartstore_name_candidates("정제명", ["키워드"]) == ["후보 하나", "후보 둘", "후보 셋"]

        generate.side_effect = ValueError("bad json")
        assert await client.generate_smartstore_name_candidates("정제명", ["키워드"]) == []
