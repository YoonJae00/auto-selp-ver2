class NaverAttributeMapper:
    def map_attributes(self, specs: dict, schema) -> list[dict]:
        mapped = []
        meta = getattr(schema, 'meta', {})
        
        for key, value in specs.items():
            if key in meta:
                attr_meta = meta[key]
                attr_seq = attr_meta.get("attributeSeq")
                
                # Check if it's a SELECT type (has values dict)
                if "values" in attr_meta and value in attr_meta["values"]:
                    mapped.append({
                        "attributeSeq": attr_seq,
                        "attributeValueSeq": attr_meta["values"][value]
                    })
                # If it's an INPUT type (no values dict)
                elif "values" not in attr_meta:
                    mapped.append({
                        "attributeSeq": attr_seq,
                        "attributeRealValue": str(value),
                        "attributeRealValueUnitCode": attr_meta.get("unitCode", "")
                    })
        return mapped

class CoupangAttributeMapper:
    def map_attributes(self, specs: dict, schema) -> dict:
        result = {"product_attributes": [], "item_attributes": []}
        meta = getattr(schema, 'meta', {})
        
        for key, value in specs.items():
            if key in meta:
                exposed = meta[key].get("exposed", "NONE")
                attr_obj = {
                    "attributeTypeName": key,
                    "attributeValueName": str(value)
                }
                
                if exposed == "EXPOSED":
                    result["item_attributes"].append(attr_obj)
                else:
                    result["product_attributes"].append(attr_obj)
                    
        return result
