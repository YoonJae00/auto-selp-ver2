import json
import logging
from dataclasses import asdict
from typing import List

from clients.naver_schema_provider import AttributeSchema, AttributeDef

logger = logging.getLogger(__name__)


class CoupangAttributeSchemaProvider:
    def __init__(self, redis_client=None, coupang_client=None):
        self.redis = redis_client
        self.coupang_client = coupang_client

    async def get_attribute_schema(self, category_id: str) -> AttributeSchema:
        cache_key = f"attr_schema:coupang:{category_id}"

        # Try Redis cache first
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                attributes = [AttributeDef(**attr) for attr in data["attributes"]]
                return AttributeSchema(
                    market_code=data["market_code"],
                    category_id=data["category_id"],
                    attributes=attributes,
                    meta=data.get("meta", {}),
                )

        # Fetch from Coupang API if client is available
        attributes: List[AttributeDef] = []
        meta: dict = {}

        if self.coupang_client:
            try:
                raw_response = await self.coupang_client.get_category_attributes(str(category_id))
                # Response shape: {"code": "SUCCESS", "data": [{..., "attributes": [...]}]}
                data_list = raw_response.get("data", [])
                raw_attrs = data_list[0].get("attributes", []) if data_list else []

                for attr in raw_attrs:
                    attr_name = attr.get("attributeTypeName", "")
                    if not attr_name:
                        continue

                    required_str = attr.get("required", "OPTIONAL")
                    input_type_raw = attr.get("inputType", "INPUT")
                    valid_vals = attr.get("inputValues", []) or None

                    attributes.append(AttributeDef(
                        name=attr_name,
                        required=(required_str == "MANDATORY"),
                        data_type=attr.get("dataType", "STRING"),
                        input_type=input_type_raw,  # "INPUT" or "SELECT"
                        unit=attr.get("basicUnit"),
                        valid_values=valid_vals if valid_vals else None,
                    ))
                    # CoupangMapper uses `exposed` key; Coupang API has no such field.
                    # All attributes mapped to product_attributes (exposed="NONE") for now.
                    meta[attr_name] = {
                        "exposed": "NONE",
                    }
            except Exception as e:
                logger.warning(
                    "CoupangAttributeSchemaProvider: API fetch failed for category %s: %s",
                    category_id,
                    e,
                )

        schema = AttributeSchema(
            market_code="coupang",
            category_id=str(category_id),
            attributes=attributes,
            meta=meta,
        )

        # Cache result for 24 h
        if self.redis:
            await self.redis.setex(cache_key, 86400, json.dumps(asdict(schema)))

        return schema
