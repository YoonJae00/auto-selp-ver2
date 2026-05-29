import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from clients.openai_client import OpenAIClient

@pytest.mark.asyncio
async def test_openai_refine_product_name_success():
    with patch("openai.AsyncOpenAI") as MockOpenAI:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"refined_name": "정제된 상품명"}'
        
        MockOpenAI.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        
        client = OpenAIClient()
        result = await client.refine_product_name("원본 상품명 10p !!")
        
        assert result == "정제된 상품명"
        MockOpenAI.return_value.chat.completions.create.assert_called_once()

@pytest.mark.asyncio
async def test_openai_extract_product_attributes_success():
    with patch("openai.AsyncOpenAI") as MockOpenAI:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"색상": "블루", "사이즈": "M"}'
        
        MockOpenAI.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        
        client = OpenAIClient()
        client._download_image = AsyncMock(return_value=b"fake_image_bytes")
        
        result = await client.extract_product_attributes(
            refined_name="예쁜 반바지",
            image_urls=["http://example.com/img1.jpg"],
            attributes=[{"name": "색상"}, {"name": "사이즈"}]
        )
        
        assert result == {"색상": "블루", "사이즈": "M"}
        client._download_image.assert_called_once_with("http://example.com/img1.jpg")
        MockOpenAI.return_value.chat.completions.create.assert_called_once()
