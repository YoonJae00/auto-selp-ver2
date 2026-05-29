import json
from clients.naver_schema_provider import AttributeSchema, AttributeDef

class CoupangAttributeSchemaProvider:
    def __init__(self, redis_client=None, coupang_client=None):
        self.redis = redis_client
        self.coupang_client = coupang_client
        
    async def get_attribute_schema(self, category_id: str) -> AttributeSchema:
        cache_key = f"attr_schema:coupang:{category_id}"
        
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                attributes = [AttributeDef(**attr) for attr in data["attributes"]]
                return AttributeSchema(market_code=data["market_code"], category_id=data["category_id"], attributes=attributes)
                
        schema = AttributeSchema(market_code="coupang", category_id=category_id, attributes=[])
        return schema
