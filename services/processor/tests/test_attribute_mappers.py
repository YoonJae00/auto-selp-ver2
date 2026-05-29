from utils.attribute_mappers import NaverAttributeMapper, CoupangAttributeMapper
from clients.naver_schema_provider import AttributeSchema, AttributeDef

def test_naver_mapper():
    mapper = NaverAttributeMapper()
    # Mock schema holding mapping meta
    schema = AttributeSchema(
        market_code="naver", category_id="1", 
        attributes=[AttributeDef(name="색상", required=True, data_type="STRING", input_type="SELECT", unit=None, valid_values=["레드"])]
    )
    # Mocking internal meta dict that would be built by the real client
    schema.meta = {"색상": {"attributeSeq": 123, "values": {"레드": 456}}}
    
    specs = {"색상": "레드", "가로": "10"} # "가로" is not in schema
    
    result = mapper.map_attributes(specs, schema)
    
    assert len(result) == 1
    assert result[0] == {"attributeSeq": 123, "attributeValueSeq": 456}

def test_coupang_mapper():
    mapper = CoupangAttributeMapper()
    schema = AttributeSchema(
        market_code="coupang", category_id="1",
        attributes=[
            AttributeDef(name="색상", required=True, data_type="STRING", input_type="SELECT", unit=None, valid_values=["레드"]),
            AttributeDef(name="브랜드", required=False, data_type="STRING", input_type="INPUT", unit=None, valid_values=None)
        ]
    )
    schema.meta = {"색상": {"exposed": "EXPOSED"}, "브랜드": {"exposed": "NONE"}}
    
    specs = {"색상": "레드", "브랜드": "우리브랜드"}
    
    result = mapper.map_attributes(specs, schema)
    
    assert len(result["item_attributes"]) == 1
    assert result["item_attributes"][0] == {"attributeTypeName": "색상", "attributeValueName": "레드"}
    
    assert len(result["product_attributes"]) == 1
    assert result["product_attributes"][0] == {"attributeTypeName": "브랜드", "attributeValueName": "우리브랜드"}
