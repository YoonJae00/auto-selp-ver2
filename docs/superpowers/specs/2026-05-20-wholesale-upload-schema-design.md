# Wholesale Upload Schema Redesign Spec

## 1. Goal
Revise the wholesale product upload schema so supplier Excel files can preserve their original business fields while also producing normalized product data for processing, smart upsert, product listing, and future marketplace registration.

The upload mapper currently exposes 10 standard fields. The new schema expands this into supplier-oriented fields such as status, supplier product ID, product code, option values, option prices, image slots, detail image, and supplier registration date.

## 2. Required Upload Columns
The upload page should expose these standard mapping targets:

| Field Key | Excel Meaning | Required | Notes |
| --- | --- | --- | --- |
| `wholesale_status` | 상태 | Yes | Examples: 정상, 품절, 판매중지 |
| `wholesale_product_id` | 제품번호 | Yes | Supplier mall internal product ID |
| `product_code` | 상품코드 | Yes | Supplier product code. Used for smart upsert identity |
| `original_name` | 상품명 | Yes | Raw product name for processing |
| `option_values_raw` | 옵션값 | No | Example: `L자형,V자형` |
| `price_wholesale_raw` | 가격 | Yes | Supply price. May contain comma-separated option prices |
| `price_retail` | 소비자가 | No | List price |
| `price_min_selling` | 판매준수가 | No | Minimum allowed sale price |
| `origin` | 원산지 | Yes | Example: `해외|아시아|중국` |
| `image_list_1` | 목록이미지1 | Yes | Primary list image candidate |
| `image_list_2` | 목록이미지2 | No | Additional image |
| `image_list_3` | 목록이미지3 | No | Additional image |
| `image_list_4` | 목록이미지4 | No | Additional image |
| `image_list_5` | 목록이미지5 | No | Additional image |
| `image_detail` | 상세이미지 | Yes | Detail HTML or detail image URL |
| `wholesale_registered_at` | 등록일 | No | Supplier mall registration date |

## 3. Normalized Product Fields
The backend should convert mapped upload values into these storage fields:

- `wholesale_status`: required string.
- `wholesale_product_id`: required string.
- `product_code`: required string and the smart upsert key.
- `original_name`: required string.
- `origin`: required string.
- `price_wholesale_raw`: required raw string.
- `price_wholesale`: integer representative supply price.
- `option_values_raw`: optional raw string.
- `option_variants`: parsed JSON list.
- `price_retail`: optional integer.
- `price_min_selling`: optional integer.
- `images_list`: ordered string array made from `image_list_1` through `image_list_5`, dropping blanks.
- `image_detail`: required string.
- `wholesale_registered_at`: optional date/string.
- `raw_metadata`: full original Excel row, unchanged except for JSON-safe conversion.

## 4. Option And Price Parsing
Supplier files may encode option names and option prices as parallel comma-separated strings:

```text
옵션값: L자형,V자형
가격: 2640,2820
```

The upload pipeline should preserve both raw strings and parse them into:

```json
{
  "price_wholesale": 2640,
  "option_values_raw": "L자형,V자형",
  "price_wholesale_raw": "2640,2820",
  "option_variants": [
    { "name": "L자형", "price_wholesale": 2640, "position": 1 },
    { "name": "V자형", "price_wholesale": 2820, "position": 2 }
  ]
}
```

Representative price policy: `price_wholesale` is the first option price. If there is no option list, it is the parsed single supply price.

Parsing behavior:

- Split `option_values_raw` and `price_wholesale_raw` on commas.
- Trim whitespace around every token.
- Parse prices into integers after removing common formatting such as commas inside numbers, currency symbols, and blank spaces where possible.
- If option and price counts match, create one `option_variants` item per pair.
- If options are absent and price is present, store an empty `option_variants` list and set `price_wholesale` from the single price.
- If counts do not match or a price cannot be parsed, do not discard the row. Preserve raw values and add a structured warning.

## 5. Data Model Approach
Use a hybrid model:

1. Keep raw supplier fields in `raw_metadata`.
2. Store commonly queried fields as first-class product columns.
3. Store option details in a JSON field such as `option_variants`.

This avoids a larger normalized `product_options` table for now while still giving future marketplace registration code a structured source of option data. A separate options table can be introduced later if the product needs option-level stock, option-level sync status, option images, or option-specific marketplace IDs.

## 6. Upload UI Behavior
The Visual Column Mapper should replace the current 10 mapping targets with the 16 supplier-oriented targets above.

Required fields should block processing if unmapped:

- `wholesale_status`
- `wholesale_product_id`
- `product_code`
- `original_name`
- `price_wholesale_raw`
- `origin`
- `image_list_1`
- `image_detail`

Auto-matching should use common Korean header fallbacks. The saved `WholesaleSite.column_mapping` remains the per-supplier template storage mechanism.

## 7. Smart Upsert And Change Tracking
`product_code` remains the primary smart upsert identity for a user's products.

On re-upload:

- Update supplier fields, prices, options, images, and raw metadata.
- Compare representative `price_wholesale` against platform mappings' `last_synced_price`.
- Compare `wholesale_status` against `last_synced_status`.
- If either changes, set platform mapping sync status to `pending_update` and keep the existing change flags.

Option-level changes should be detectable later from `option_variants`, but the first implementation only needs row-level warnings and representative price change tracking.

## 8. Error Handling And Warnings
The upload pipeline should prefer ingesting rows with warnings over rejecting entire files.

Reject before processing only when required mappings are missing or the mapped Excel header does not exist.

Record warnings for:

- Required row value is blank.
- Price cannot be parsed.
- Option count and price count differ.
- `image_list_1` or `image_detail` is blank.
- Registration date cannot be parsed.

Warnings may be stored in `Product.warnings` or inside `raw_metadata` until a dedicated import validation surface exists.

## 9. Testing
Backend tests should cover:

- New required field mapping validation.
- Image slot aggregation into `images_list`.
- Single-price parsing.
- Parallel option/price parsing.
- Mismatched option/price count warnings.
- Smart upsert keeps `product_code` as identity and updates new supplier fields.

Frontend checks should cover:

- All 16 fields render in the mapper.
- Required fields are enforced before processing.
- Saved wholesale-site templates round-trip through the UI.

## 10. Out Of Scope
This spec does not implement marketplace-specific option export formats yet.

Marketplace registration should consume `option_variants` later and transform it into each channel's required option schema.
