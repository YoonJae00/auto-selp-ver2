import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from clients.openai_client import OpenAIClient, WholesaleMappingRule, WholesaleMappingSuggestion

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


@pytest.mark.asyncio
async def test_openai_smartstore_candidates_json_and_failure_fallback():
    with patch("openai.AsyncOpenAI") as MockOpenAI:
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = '{"candidates": ["후보 하나", "후보 둘", "후보 셋"]}'
        create = MockOpenAI.return_value.chat.completions.create = AsyncMock(return_value=response)
        client = OpenAIClient()

        assert await client.generate_smartstore_name_candidates("정제명", ["키워드"]) == ["후보 하나", "후보 둘", "후보 셋"]
        assert create.call_args.kwargs["response_format"] == {"type": "json_object"}

        create.side_effect = ValueError("bad json")
        assert await client.generate_smartstore_name_candidates("정제명", ["키워드"]) == []


@pytest.mark.asyncio
async def test_wholesale_mapping_uses_direct_parse_without_beta_access():
    parsed = WholesaleMappingSuggestion(
        rules=[WholesaleMappingRule(target="product_code", source="자체상품코드")],
        notes=["상품코드는 자체상품코드를 사용합니다."],
    )
    parse = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))]
        )
    )
    client = object.__new__(OpenAIClient)
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))
    )
    client.model = "test-model"

    result = await client.suggest_wholesale_mapping(
        ["자체상품코드"],
        [{"자체상품코드": "ABC-1"}],
    )

    assert result == {
        "column_mapping": {"product_code": "자체상품코드"},
        "notes": ["상품코드는 자체상품코드를 사용합니다."],
    }
    parse.assert_awaited_once()
    prompt = parse.call_args.kwargs["messages"][1]["content"]
    assert "map that source only to price_wholesale_raw" in prompt
    assert "do not map it to option_price_deltas_raw" in prompt
    assert "first price as the base wholesale price and computes deltas (0,1000)" in prompt
