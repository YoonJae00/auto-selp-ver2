import pytest
from unittest.mock import AsyncMock
from clients.coupang_schema_provider import CoupangAttributeSchemaProvider
from clients.naver_schema_provider import AttributeSchema, AttributeDef

@pytest.mark.asyncio
async def test_coupang_get_attribute_schema_cached(mocker):
    provider = CoupangAttributeSchemaProvider(redis_client=AsyncMock())
    
    cached_data = '{"market_code": "coupang", "category_id": "456", "attributes": [{"name": "브랜드", "required": true, "data_type": "STRING", "input_type": "INPUT", "unit": null, "valid_values": null}]}'
    provider.redis.get.return_value = cached_data
    
    result = await provider.get_attribute_schema("456")
    
    assert isinstance(result, AttributeSchema)
    assert result.category_id == "456"
    assert result.attributes[0].name == "브랜드"
