import pytest
from unittest.mock import AsyncMock, patch
from clients.naver_schema_provider import NaverAttributeSchemaProvider, AttributeSchema, AttributeDef

@pytest.mark.asyncio
async def test_get_attribute_schema_cached(mocker):
    provider = NaverAttributeSchemaProvider(redis_client=AsyncMock())
    
    # Mock redis get to return cached schema
    cached_data = '{"market_code": "naver", "category_id": "123", "attributes": [{"name": "색상", "required": true, "data_type": "STRING", "input_type": "SELECT", "unit": null, "valid_values": ["레드"]}]}'
    provider.redis.get.return_value = cached_data
    
    result = await provider.get_attribute_schema("123")
    
    assert isinstance(result, AttributeSchema)
    assert result.category_id == "123"
    assert len(result.attributes) == 1
    assert result.attributes[0].name == "색상"
    provider.redis.get.assert_called_once_with("attr_schema:naver:123")
