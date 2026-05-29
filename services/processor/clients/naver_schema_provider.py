import json
import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List

logger = logging.getLogger(__name__)


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
    meta: dict = field(default_factory=dict)  # mapper-ready lookup: {attr_name: {attributeSeq, unitCode, ...}}


class NaverAttributeSchemaProvider:
    def __init__(self, redis_client=None, naver_client=None):
        self.redis = redis_client
        self.naver_client = naver_client

    async def get_attribute_schema(self, category_id: str) -> AttributeSchema:
        cache_key = f"attr_schema:naver:{category_id}"

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

        # Fetch from Naver Commerce API if client is available
        attributes: List[AttributeDef] = []
        meta: dict = {}

        if self.naver_client:
            try:
                raw_attrs = await self.naver_client.get_category_attributes(str(category_id))
                for attr in raw_attrs:
                    attr_name = attr.get("attributeName", "")
                    attr_seq = attr.get("attributeSeq")
                    if not attr_name or attr_seq is None:
                        continue
                    attributes.append(AttributeDef(
                        name=attr_name,
                        required=bool(attr.get("required", False)),
                        data_type="STRING",
                        input_type="INPUT",   # treat all as free-text; SELECT support needs value-name mapping
                        unit=None,
                        valid_values=None,
                    ))
                    meta[attr_name] = {
                        "attributeSeq": attr_seq,
                        "unitCode": "",
                    }
            except Exception as e:
                logger.warning(
                    "NaverAttributeSchemaProvider: API fetch failed for category %s: %s",
                    category_id,
                    e,
                )

        schema = AttributeSchema(
            market_code="naver",
            category_id=str(category_id),
            attributes=attributes,
            meta=meta,
        )

        # Cache result for 24 h (even if empty — avoids repeated API calls for invalid categories)
        if self.redis:
            await self.redis.setex(cache_key, 86400, json.dumps(asdict(schema)))

        return schema
