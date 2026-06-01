# Standard Product And Option Schema Design

Date: 2026-06-01

## Goal

Redefine the wholesale upload and product management column model around Auto-Selp's own standard schema instead of around each supplier's spreadsheet format.

Supplier files, crawlers, and future manual imports may all provide different column names, option separators, and data shapes. The system should normalize every source into one internal product ledger so later AI processing, product management, and marketplace registration can depend on stable fields.

The standard model separates data into three stages:

1. `supplier_*`: collected supplier values, preserved close to the original.
2. `processed_*`: Auto-Selp generated or operator-reviewed values.
3. `listing_*`: sales-channel-ready values for Naver SmartStore, Coupang Wing, PlayAuto, and future channels.

## Marketplace Research Summary

The option model is based on current official marketplace registration structures.

### Naver SmartStore

Naver Commerce API product registration stores option data under `originProduct.detailAttribute.optionInfo`.

- `optionInfo` supports simple, combination, custom/direct-input, and standard options.
- Simple and combination options cannot be used together.
- Combination options use `optionCombinationGroupNames` plus `optionCombinations`.
- A combination option can use up to three option groups for normal products. Branch-style options may use four groups, but that is a special-case extension.
- Each combination row carries stock quantity, option price adjustment, usable status, and seller manager code.
- Standard option image fields exist for image-capable option attributes, and image URLs should come from Naver's product image upload API.

Official references:

- https://apicenter.commerce.naver.com/docs/commerce-api/current/schemas/%EC%9B%90%EC%83%81%ED%92%88-%EC%A0%95%EB%B3%B4-%EA%B5%AC%EC%A1%B0%EC%B2%B4
- https://apicenter.commerce.naver.com/docs/commerce-api/current/upload-product

### Coupang Wing

Coupang product creation uses product-level data plus `items[]`, where each item is the smallest sellable option unit.

- `items[]` supports up to 200 option items.
- Each item has item name, original price, sale price, stock quantity, external vendor SKU, images, notices, contents, and attributes.
- `externalVendorSku` is option-level seller-managed code.
- `items[].images[]` supports a required representation image and optional detail images.
- Category metadata determines which purchase options and attributes are mandatory.
- Attributes use `attributeTypeName`, `attributeValueName`, and exposure metadata to represent purchase options and search/filter attributes.

Official references:

- https://developers.coupangcorp.com/hc/ko/articles/360033877853
- https://developers.coupangcorp.com/hc/ko/articles/360033917473-Coupang-OPEN-API-%EC%95%88%EB%82%B4

## Standard Workbook Shape

Use two primary sheets or internal tables.

### `products`

One row per product. Every imported product must have a `products` row whether or not it has options.

This sheet stores product-level values: supplier identity, original product information, product images, detail content, origin, base prices, and later processed/listing fields.

### `product_options`

Zero or more rows per product. Products without options have no option rows.

Each option row represents one sellable option SKU. This maps cleanly to one Naver `optionCombinations[]` row for combination options and one Coupang `items[]` entry.

## Required Product Columns

| Field | Meaning | Notes |
| --- | --- | --- |
| `supplier_name` | Supplier name | Used for filtering and supplier-specific import templates. |
| `supplier_product_id` | Supplier product ID | Supplier's internal product ID if present. |
| `supplier_product_code` | Supplier product code | Primary product join key between `products` and `product_options`. Also used for smart upsert. |
| `supplier_status` | Supplier sale status | Examples: available, sold out, stopped. |
| `raw_product_name` | Supplier original product name | The raw name before AI refinement. |
| `origin` | Country/place of origin | Required because marketplace registration usually needs origin data. |
| `supply_price` | Base supply price | Source-of-truth product-level base cost. Option rows may override it. |
| `main_image_url` | Product representative image | Product-level default image. |
| `detail_content` | Detail HTML or detail image content | Source for marketplace detail page and visual attribute extraction. |

## Optional Product Columns

| Field | Meaning | Notes |
| --- | --- | --- |
| `supplier_category` | Supplier category text/path | Preserved as supplier-side taxonomy. |
| `supplier_registered_at` | Supplier registration date | Optional supplier metadata. |
| `supplier_updated_at` | Supplier update date | Useful for crawler/import delta checks. |
| `retail_price` | Supplier/list price | Optional. |
| `minimum_selling_price` | Minimum allowed selling price | Optional policy constraint. |
| `shipping_fee` | Supplier shipping fee | Optional cost ingredient. |
| `stock_quantity` | Product-level stock quantity | Used only when no option-level stock is provided. |
| `brand_name` | Brand name | May come from supplier, AI, or operator review. |
| `manufacturer` | Manufacturer | Optional marketplace ingredient. |
| `model_name` | Model name | Optional marketplace ingredient. |
| `extra_image_urls` | Additional product images | Ordered list. |
| `raw_options_text` | Supplier raw option text | Preserves original text such as comma/colon/slash-separated options. |
| `raw_metadata` | Full original supplier row | JSON-safe copy of all source fields. |

## Option Columns

| Field | Meaning | Notes |
| --- | --- | --- |
| `supplier_product_code` | Parent product join key | Must match `products.supplier_product_code`. |
| `option_sku` | Option-level SKU/code | Maps to Naver `sellerManagerCode` and Coupang `externalVendorSku` where applicable. |
| `option_type` | Option structure type | Allowed values: `single`, `combination`, `custom`, `standard`. Default `combination` for normal selectable variants. |
| `option_group_1` | First option group name | Example: color. |
| `option_value_1` | First option value | Example: black. |
| `option_group_2` | Second option group name | Example: size. |
| `option_value_2` | Second option value | Example: L. |
| `option_group_3` | Third option group name | Example: type. |
| `option_value_3` | Third option value | Example: basic. |
| `option_display_name` | Human/market item name | Example: black / L / basic. Maps well to Coupang `itemName`. |
| `option_supply_price` | Actual option-level supply price | Source-of-truth cost for this option. |
| `option_sale_price` | Proposed option-level sale price | Optional listing-ready price. |
| `option_price_delta` | Difference from product base price | Derived from `option_supply_price - products.supply_price` unless explicitly supplied. Useful for Naver combination option price. |
| `option_stock_quantity` | Option-level stock | Preferred over product-level stock when present. |
| `option_status` | Option sale status | Supplier or normalized status. |
| `option_usable` | Whether this option can be listed | Boolean. Maps to Naver `usable`; controls whether adapters include the option. |
| `option_main_image_url` | Option representative image | Used for option-specific images where supported. |
| `option_extra_image_urls` | Option additional images | Ordered list. Maps naturally to Coupang item detail images. |
| `option_position` | Display order | Stable sort key. |
| `raw_option_text` | Supplier raw option string | Preserves original option text. |
| `raw_option_metadata` | Supplier raw option metadata | JSON-safe source object for this option row. |

## Option Rules

- A product with no options has one `products` row and zero `product_options` rows.
- A product with options has one `products` row and one `product_options` row per sellable option SKU.
- The standard model supports up to three normal option groups by default because this aligns with Naver combination options and is sufficient for typical Coupang items.
- Four-level branch-style Naver options remain out of the default schema and should be handled later as an explicit special case.
- Option images belong on option rows, not only on the parent product. If an option image is absent, marketplace adapters may fall back to the product representative image.
- `option_supply_price` is the source-of-truth option cost.
- `option_price_delta` is stored as a derived convenience value for marketplace adapters. If both values are supplied and disagree, import validation should warn and recompute the delta from `option_supply_price`.
- `option_sale_price` is optional because sale price may be calculated later by pricing policy.

## Import Normalization

Each supplier import template or crawler becomes an adapter from supplier-specific fields into the standard workbook shape.

Examples:

- A supplier using comma-separated options should parse its raw option text into multiple `product_options` rows.
- A supplier using colon-separated key/value text should parse group names and values into `option_group_n` and `option_value_n`.
- A supplier with one row per option should merge repeated product-level fields into one `products` row and create multiple option rows.
- A crawler should emit the same standard product and option records directly, bypassing spreadsheet header variability.

The supplier's original row or scraped object must still be preserved in `raw_metadata` and `raw_option_metadata`.

## Marketplace Mapping

### Naver

- `products.raw_product_name` or processed/listing product name maps to Naver product name fields after AI processing.
- `products.origin` maps to origin area information.
- `products.main_image_url` and `extra_image_urls` map to product images after image upload.
- `products.detail_content` maps to detail content.
- `product_options.option_group_1..3` become `optionCombinationGroupNames`.
- `product_options.option_value_1..3` become each `optionCombinations[]` row's `optionName1..3`.
- `product_options.option_price_delta` maps to combination option `price`.
- `product_options.option_stock_quantity` maps to `stockQuantity`.
- `product_options.option_usable` maps to `usable`.
- `product_options.option_sku` maps to seller manager code where supported.
- `option_main_image_url` and `option_extra_image_urls` are retained for standard/image-capable option handling and future group product flows.

### Coupang

- Each `product_options` row becomes one `items[]` entry.
- If a product has no option rows, the adapter creates one default item from product-level data.
- `option_display_name` maps to `itemName`.
- `option_sku` maps to `externalVendorSku`.
- `option_sale_price` maps to `salePrice` when provided; otherwise pricing policy calculates it.
- Product/list price maps to `originalPrice` according to pricing policy.
- `option_stock_quantity` maps to `maximumBuyCount`.
- `option_main_image_url` and `option_extra_image_urls` map to `items[].images[]`.
- `option_group_n` and `option_value_n` feed item attributes and purchase option attributes according to category metadata.

## Data Model Direction

The current `products.option_variants` JSON field is a good bridge, but the target model should introduce an explicit option record boundary.

Recommended phased approach:

1. Define the standard field registry in code and UI.
2. Update upload mapping so supplier columns map into standard product and option fields.
3. Keep writing `option_variants` JSON for backward compatibility while shaping it from the new option schema.
4. Add a first-class `product_options` table when marketplace registration needs option-level IDs, image state, stock updates, or sync status.

## UI Direction

The upload UI should stop presenting supplier-shaped fields as the final product definition.

Instead:

- Supplier templates choose how source columns map into Auto-Selp standard columns.
- The mapper should show required product fields first, optional product fields second, and option fields in their own section.
- The upload preview should show both original rows and the normalized result preview.
- Option parsing controls should be supplier-template-specific, including separator rules, one-row-per-option detection, group/value extraction, and option image mapping.

## Testing

Backend tests should cover:

- Required product field validation including `origin`.
- Products without options produce no option rows and still create a default marketplace item when needed.
- Products with comma-separated, colon-separated, and repeated-row supplier options normalize into identical standard option rows.
- Option-level images are preserved.
- `option_supply_price` drives `option_price_delta` derivation.
- Marketplace snapshot/adapters can transform the standard option model into Naver and Coupang payload shapes.

Frontend tests/checks should cover:

- Required and optional standard fields render in grouped sections.
- Option fields render separately from product fields.
- Supplier templates persist option parsing/mapping settings.
- Normalized preview makes supplier input and Auto-Selp output easy to compare.

## Out Of Scope

- Full implementation of Naver standard option image flows.
- Four-level Naver branch-style options.
- Marketplace submission APIs.
- PlayAuto export schema details.
- Dedicated option-level stock sync and marketplace option ID tracking.
