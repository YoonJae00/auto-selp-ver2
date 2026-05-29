import json
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

@dataclass
class AttributeDef:
    name: str
    required: bool
    data_type: str
    input_type: str
    unit: Optional[str]
    valid_values: Optional[List[str]]

@dataclass
class AttributeSchema:
    market_code: str
    category_id: str
    attributes: List[AttributeDef]

class NaverAttributeSchemaProvider:
    def __init__(self, redis_client=None, naver_client=None):
        self.redis = redis_client
        self.naver_client = naver_client
        
    async def get_attribute_schema(self, category_id: str) -> AttributeSchema:
        cache_key = f"attr_schema:naver:{category_id}"
        
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                attributes = [AttributeDef(**attr) for attr in data["attributes"]]
                return AttributeSchema(market_code=data["market_code"], category_id=data["category_id"], attributes=attributes)
                
        # Fallback empty schema for tests until client is fully integrated
        schema = AttributeSchema(market_code="naver", category_id=category_id, attributes=[])
        
        if self.redis:
            await self.redis.setex(cache_key, 86400, json.dumps(asdict(schema)))
            
        return schema
