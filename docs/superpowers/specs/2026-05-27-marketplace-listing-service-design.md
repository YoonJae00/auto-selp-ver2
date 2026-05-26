# Marketplace Listing Service Design

Date: 2026-05-27

## Goal

Add a dedicated marketplace listing capability that turns processed products into reviewable Smart Store and Coupang listing drafts, lets sellers correct marketplace-specific values, and submits selected drafts to each marketplace.

The design must support more marketplaces later without expanding the shared product table every time a channel introduces a new product field, optimization rule, attribute, or submission requirement.

## Confirmed Product Direction

The initial release uses a review-before-submit flow:

- Product processing completes before marketplace listing work begins.
- Drafts are automatically generated only for marketplace accounts the seller has connected.
- Users review and optionally edit key marketplace-specific values before submission.
- Individual and bulk registration are both supported.
- Automatic submission after processing is out of scope.
- The first UI exposes one account per marketplace, while the data model supports multiple accounts later.

Product-specific inputs such as origin, representative/additional images, and detail image or HTML are already retained by the processor and must be included in the marketplace snapshot contract.

Account-level values such as shipping, returns, standard disclosure defaults, and default certification policy are not repeatedly entered per product. They are owned by marketplace-specific account configuration and composed into the listing draft or effective submission payload by each marketplace adapter.

## Current Context

The current repository has two operational services behind a gateway:

```text
auth
processor + processor worker
postgres
redis
frontend
```

`processor` currently owns:

- supplier site and column-mapping configuration,
- spreadsheet import and smart upsert,
- normalized product fields,
- product processing through LangGraph,
- keyword curation,
- Smart Store and Coupang category mapping candidates,
- the current `ProductPlatformMapping` synchronization indicators.

Relevant processed product values already include:

```text
product_code
wholesale_product_id
original_name
refined_name
brand_name
keywords
origin
price_wholesale
price_retail
price_min_selling
option_variants
images_list
image_detail
market category mappings
```

The current platform mapping object is not a sufficient home for marketplace listing payloads. Smart Store and Coupang have structurally different payloads, and each channel can add new listing-specific rules over time.

## Architectural Choice

Use a dedicated `marketplace` service with a shared listing lifecycle and marketplace-specific adapters.

The alternatives considered were:

1. Store each marketplace's generated payload in a shared draft lifecycle model and delegate conversion/validation/submission to adapters.
2. Store one large marketplace-neutral listing model and generate external API payloads only at submit time.
3. Create separate draft tables and flows for Smart Store, Coupang, and every future marketplace.

The selected approach is option 1.

It preserves a common operational workflow while accepting that external marketplaces are not structurally identical:

```text
Common:
- draft ownership and status
- product snapshot version
- review and overrides
- validation outcomes
- submission jobs and attempts
- remote product identifiers and errors

Marketplace-specific:
- API payload shape
- title and keyword generation recipes
- category attribute rules
- images/detail conversion
- option/SKU conversion
- account setting schema
- request submission and response normalization
```

This prevents the shared `products` table from accumulating `smartstore_*`, `coupang_*`, and future marketplace-specific columns.

## Service Boundary

Add separate API and worker containers:

```text
frontend
  -> gateway
     -> auth
     -> processor
     -> marketplace

processor-api + processor-worker
  owns processed product source data and product-processing outcomes

marketplace-api + marketplace-worker
  owns marketplace accounts, configuration, listing drafts, validation,
  submissions, external remote identifiers, and listing failures

shared infrastructure in the initial deployment
  postgres
  redis
```

The initial deployment may use the existing Postgres and Redis containers, but service ownership remains strict:

- `processor` owns its product/import/processing tables.
- `marketplace` must not directly query or modify processor tables.
- `marketplace` reads product data only through processor API contracts.
- `processor` does not persist final marketplace API payloads.

This allows a later move to separate databases or event-driven integration without redesigning the product registration domain.

## Processing Completion Integration

After a product is successfully processed, `processor` requests draft generation:

```http
POST /api/marketplace/draft-generation-jobs
```

```json
{
  "source_product_id": "uuid",
  "source_product_updated_at": "2026-05-27T10:20:00Z",
  "reason": "processing_completed"
}
```

This request is a notification to generate current drafts, not the complete product payload.

`marketplace` obtains the normalized product source through a processor API:

```http
GET /api/processor/products/{product_id}/marketplace-snapshot
```

Example contract:

```json
{
  "product_id": "uuid",
  "version": "product-revision-or-updated-at",
  "product_code": "ABC-001",
  "wholesale_product_id": "12345",
  "refined_name": "스테인리스 텀블러",
  "brand_name": "우리브랜드",
  "keywords": ["보온", "대용량", "빨대형"],
  "origin": "해외|아시아|중국",
  "price": {
    "wholesale": 8000,
    "retail": 15900,
    "minimum_selling": 12000
  },
  "images": {
    "list": ["https://example/main.jpg", "https://example/sub.jpg"],
    "detail_content": "<img src=\"https://example/detail.jpg\">"
  },
  "options": [
    {
      "name": "블랙",
      "price_wholesale": 8000,
      "position": 1
    }
  ],
  "market_categories": {
    "smartstore": {
      "category_id": "50000123",
      "category_path": "생활/주방 > 컵"
    },
    "coupang": {
      "category_id": "123456",
      "category_path": null
    }
  }
}
```

The draft-generation request must be retryable. A duplicate request for the same product version and market account must update or reuse the applicable unsubmitted draft rather than create duplicates.

The notification version is the version requested for draft generation. When `marketplace` fetches the snapshot:

- if the processor snapshot has the notified version, generate drafts from it;
- if the processor reports that the notified version is no longer current and does not expose historical snapshots, generate from the latest available version and record that version on the generation job and drafts;
- if a later notification for the same product arrives while generation is in progress, allow the newer version to supersede unsubmitted output and leave only the newest draft awaiting review.

Track generation requests separately from drafts:

```text
market_draft_generation_jobs
- id
- user_id
- source_product_id
- requested_source_version
- generated_source_version
- reason
- status                      # queued, processing, completed, failed, superseded
- error JSONB
- created_at
- completed_at
```

If marketplace draft generation is unavailable or fails, product processing remains completed. The failure is surfaced as a marketplace-generation error that can be retried separately.

## Marketplace Accounts And Settings

Marketplace configuration differs by channel. Do not build one generic shipping/return/settings form that assumes the same fields for all marketplaces.

The initial UI exposes one connected account for each marketplace, but drafts and submissions reference `market_account_id` so multi-account support can be introduced without a database redesign.

Suggested tables:

```text
market_accounts
- id
- user_id
- market_code                 # smartstore, coupang, future channels
- display_name
- credentials_encrypted
- connection_status
- is_primary
- created_at
- updated_at

market_account_settings
- id
- market_account_id
- settings_schema_version
- connection_config JSONB
- fulfillment_config JSONB
- claim_config JSONB
- listing_defaults JSONB
- generation_rules JSONB
- created_at
- updated_at
```

The settings page uses one entry area with marketplace-specific tabs:

```text
/marketplaces/accounts

[Smart Store] [Coupang] [Future Marketplace...]
```

Smart Store configuration can include:

```text
- API connection and channel information
- outbound/return location identifiers
- Smart Store delivery and claim defaults
- A/S defaults
- product-information notice defaults and override policy
- certification default policy
- Naver Shopping registration setting
- title recipe and tag-generation recipe versions
- later: attribute and catalog matching defaults
```

Coupang configuration can include:

```text
- API connection, vendorId, and vendorUserId
- outbound shipping place and return center codes
- Coupang delivery and claim defaults
- notice and certification defaults and override policy
- Coupang title recipe version
- items/SKU and attribute-generation rules
```

Only the page shell and lifecycle are common. Field definitions, validation, and account-setting panels are adapter-specific.

## Draft Storage Model

Use ordinary columns for lifecycle/query/display needs and JSONB for expandable marketplace content.

```text
market_listing_drafts
- id
- source_product_id
- source_product_version
- market_account_id
- market_code
- draft_kind                  # create, later update
- status                      # generated, needs_review, ready, submitting,
                              # submitted, failed, update_required
- display_title               # list/search summary
- category_id                 # list filter summary
- sale_price                  # list/sort summary
- primary_image_url           # thumbnail summary
- source_snapshot JSONB
- generated_payload JSONB
- override_patch JSONB
- validation_result JSONB
- adapter_version
- recipe_versions JSONB
- remote_product_id
- created_at
- updated_at
```

Responsibilities of the JSON documents:

- `source_snapshot`: the processor data version on which this draft was generated.
- `generated_payload`: adapter output before user edits.
- `override_patch`: seller edits to marketplace-specific product values.
- `validation_result`: adapter-produced errors and warnings for the effective draft.
- `recipe_versions`: trace of title, tag, attribute, or future optimization rule versions.

Non-secret account defaults used to create or validate a draft may be reflected in `generated_payload` or in validation metadata for review. Credentials are never copied into a draft. At submission time the adapter re-reads current account configuration, reapplies settings that affect the external request, and revalidates so stale account settings cannot be submitted silently.

The effective submission payload is calculated from:

```text
generated_payload
  + override_patch
  + market-account configuration required at submission time
```

Summary columns must be refreshed whenever generated output or relevant overrides change so the registration inbox can filter and sort without interpreting every JSON document in the browser.

## Extensible Generation Rules

Final marketplace listing values are not processor-owned product columns. The processor provides ingredients; each adapter builds marketplace output using versioned recipes.

Example Smart Store title input:

```text
brand_name = "우리브랜드"
refined_name = "스테인리스 텀블러"
keywords = ["보온", "대용량", "빨대형"]
```

Example recipe output:

```text
smartstore-title:v1
-> "우리브랜드 스테인리스 텀블러 대용량 보온"
```

Keyword variation must not use unrestricted random words. A title recipe may vary ordering or choose from processor-approved, product-relevant keyword candidates after applying duplicate, prohibited-term, length, and marketplace-policy checks.

This applies equally to Coupang and future marketplaces. A channel can implement its own:

```text
- title recipe
- keyword/tag recipe
- category attribute recipe
- option/SKU recipe
- image/detail-content recipe
- pricing policy recipe
```

Recipes are versioned and stored on the draft. If the rule changes later, existing submissions remain auditable and unsubmitted drafts can be regenerated explicitly or during source-product changes.

## Adapter Contract

`marketplace` implements a shared adapter contract:

```python
class MarketplaceAdapter:
    market_code: str

    def generate_draft(source_snapshot, account_settings) -> DraftResult:
        ...

    def validate(effective_payload, account_settings) -> ValidationResult:
        ...

    def apply_overrides(generated_payload, override_patch) -> dict:
        ...

    async def submit(effective_payload, credentials) -> SubmissionResult:
        ...
```

Adapters also define their supported settings/editing shape for frontend integration, either through explicit marketplace-specific API responses in the initial implementation or through a later editor-schema mechanism.

### Smart Store Adapter

The Smart Store adapter is responsible for:

```text
- Smart Store title recipe and later SEO-related recipes
- `origin` conversion to origin-area registration values
- `images_list` conversion to representative/additional images
- `image_detail` conversion to detail content
- `option_variants` conversion to option information
- Smart Store category mapping consumption
- account default composition for channel/listing configuration
- later attributes, tags, brand/manufacturer/model mapping,
  and catalog matching support
```

Smart Store official seller help treats product name, option name, model name, attributes, detail description, and detail-spec tags as registration quality/policy concerns. The draft model therefore must be capable of gaining these values through adapter versions without schema churn.

### Coupang Adapter

The Coupang adapter is responsible for:

```text
- Coupang-specific title recipe
- Coupang display category mapping consumption
- `option_variants` conversion to `items[]` and `attributes[]`
- `images_list` conversion to item image structures
- `image_detail` conversion to `contents[]`
- account default composition for vendor, fulfillment, and claim values
- later category attribute, documentation, or certification support
```

Coupang product structures are particularly SKU- and item-oriented, so the adapter must retain channel-native payload structure rather than flatten it into a shared column list.

## Draft Regeneration And Override Rules

When a product changes through re-upload or reprocessing:

### Unsubmitted draft

For statuses before successful external submission:

```text
- fetch the latest processor snapshot
- regenerate generated_payload using the active adapter and recipes
- update source_product_version and summary columns
- reapply overrides when their target paths are still valid
- mark needs_review when an override conflicts with regenerated data
  or a warning/error requires confirmation
```

### Submitted product

For a successfully submitted listing:

```text
- preserve the submitted draft and all submission attempts
- mark that marketplace listing as update_required
- create a separate future update draft rather than overwriting evidence
```

Actual external marketplace update submission is outside the first implementation, but the state model must leave a clear path for it.

## Registration Inbox And Editing UI

Add a new sidebar destination:

```text
/marketplaces
```

It is a unified registration inbox, not separate disconnected top-level pages for Smart Store and Coupang.

Filters and tabs:

```text
Marketplace:
[All] [Smart Store] [Coupang] [Future...]

Status:
- needs review
- ready
- submitting
- submitted
- failed
- product changed / update required
```

The list uses summary columns:

| Select | Marketplace | Product Title | Category | Price | Image | Validation | Submission Status | Updated |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- |

Draft editing supports shared product-specific areas:

```text
- marketplace-visible product title
- sale price
- marketplace category
- origin
- representative/additional images
- detail image or detail content
- options and option prices
```

It also exposes channel-specific editing sections:

```text
Smart Store:
- title recipe output/regeneration
- later tags, attributes, brand/manufacturer/model, and catalog matching

Coupang:
- items/SKU composition
- attributes
- contents blocks
- Coupang-specific display title output
```

Do not expose shipping, returns, or standard account defaults as repetitive product edit fields. The draft screen may show which configured template is being applied and surface missing configuration errors, but editing those settings routes to the marketplace account tab.

## Submission Workflow

The UI supports both individual and bulk submission.

Submission endpoint shape:

```http
POST /api/marketplace/submissions
```

```json
{
  "draft_ids": ["uuid"],
  "market_account_id": "uuid"
}
```

If a user selects drafts across multiple marketplaces or accounts, the frontend or API partitions them into separate account/market submission jobs. External submissions from different marketplaces are not mixed into one channel API request.

Submission sequence:

```text
1. Compute effective payload:
   generated_payload + override_patch + account configuration.
2. Run adapter validation immediately before submission.
3. Reject blocked drafts and leave their validation errors visible.
4. Create a job for valid drafts.
5. Submit through marketplace-worker.
6. Store each actual request/response attempt.
7. Update the draft lifecycle state and surface progress in the UI.
```

Suggested tables:

```text
market_submission_jobs
- id
- user_id
- market_account_id
- market_code
- status
- total_count
- success_count
- failed_count
- created_at
- completed_at

market_submission_attempts
- id
- job_id
- draft_id
- attempt_number
- submitted_payload JSONB
- normalized_error JSONB
- raw_response JSONB
- remote_product_id
- status
- created_at
```

The attempt must store the actual submitted payload. A draft can be edited later, while production support must still know exactly what request received an error or created an external product.

## State Model

Draft lifecycle:

```text
generated
  -> needs_review      warning, missing optional confirmation, or user review required
  -> ready             required validation passes and seller approves
  -> submitting        active external API submission
  -> submitted         registration succeeded
  -> failed            generation or submission failed

Unsubmitted product change:
  generated / needs_review / ready / failed
  -> needs_review      regenerated from latest product source

Submitted product change:
  submitted
  -> update_required   preserve registration evidence and prepare later update work
```

## Validation And Failure Handling

Adapters return structured validation results:

```json
{
  "status": "blocked",
  "errors": [
    {
      "code": "SMARTSTORE_MISSING_ORIGIN",
      "path": "originProduct.detailAttribute.originAreaInfo",
      "message": "원산지 변환값이 필요합니다."
    }
  ],
  "warnings": [
    {
      "code": "SMARTSTORE_TITLE_REVIEW_RECOMMENDED",
      "path": "originProduct.name",
      "message": "상품명 생성 규칙 적용 결과를 확인하세요."
    }
  ]
}
```

Rules:

- Errors block `ready` or submission.
- Warnings are shown to the seller and may be acknowledged before ready status.
- A draft generation failure for one product does not block processing or other products.
- A failed bulk submission does not roll back successful drafts in the same job.
- Retry only failed or unresolved drafts unless a seller intentionally resubmits.
- External timeout or ambiguous response cases need a distinct unresolved/confirmation path before a blind duplicate registration request; the exact remote lookup/idempotency implementation is marketplace-specific.

## Security

- Marketplace API credentials are encrypted at rest and never included in product snapshots or frontend responses.
- API routes enforce user ownership of accounts, drafts, and source product access.
- Submitted payload and marketplace response storage must avoid exposing secret credentials or authorization headers.
- Processor-to-marketplace and marketplace-to-processor internal calls require authenticated service communication in deployment configuration.

## Testing Strategy

### Processor Contract Tests

- Processed product snapshot exposes all registration ingredients: origin, images, detail content, options, pricing, category candidates, name, brand, and keywords.
- Successful processing triggers marketplace draft generation notification.
- Marketplace notification failure does not revert a completed product.

### Marketplace Common Tests

- Drafts are generated only for connected marketplace accounts.
- Duplicate product-version/account generation requests do not create duplicate active drafts.
- Unsubmitted drafts regenerate on product source changes.
- Applicable overrides are reapplied; incompatible overrides result in `needs_review`.
- Effective payload includes adapter output, overrides, and account-specific configuration.
- Individual and bulk submission jobs record per-draft attempts.
- One failed attempt does not roll back successful submissions.

### Smart Store Adapter Tests

- Origin, images, detail content, options, and category map into Smart Store payload form.
- Title recipe output and recipe version are persisted.
- Product-specific extension values can be added in generated payload without table changes.
- Smart Store account configuration composes only into Smart Store drafts.

### Coupang Adapter Tests

- Options become Coupang `items[]` and associated `attributes[]`.
- Images and detail content become Coupang item-native structures.
- Title recipe output and recipe version are persisted.
- Coupang account configuration composes only into Coupang drafts.

### Frontend Tests

- Unified marketplace inbox filters by channel and lifecycle state.
- Draft detail shows shared editable values plus marketplace-specific sections.
- Account configuration page renders independent Smart Store and Coupang tabs/panels.
- Validation messages, overrides, individual submission, and bulk submission states are surfaced correctly.

## First Release Scope

Included:

```text
- marketplace API and worker containers
- gateway routing for marketplace endpoints
- processor marketplace-snapshot contract
- processing-completed draft generation request
- marketplace account/settings data model
- Smart Store and Coupang adapter boundaries
- draft storage, regeneration, validation, and override model
- unified registration inbox
- marketplace-specific settings tabs
- individual and bulk registration jobs
- structured submission history
```

Excluded from the first release:

```text
- automatic registration after processing
- multi-account UI, despite multi-account-capable storage
- actual update submission for already registered marketplace products
- comprehensive Smart Store SEO/tag/attribute automation
- comprehensive Coupang category attribute automation
- broker/event-driven service integration
- fully schema-driven generic editor renderer for every future marketplace
```

The first adapters must expose clear extension points for title recipes and channel-specific attributes so these excluded automations can be introduced without replacing the draft model.

## Implementation Order Recommendation

The future implementation plan should decompose the feature into bounded increments:

1. Establish marketplace service/container, database ownership, gateway route, and account/settings skeleton.
2. Add processor snapshot API and processing-completed notification contract.
3. Implement shared drafts, adapter interface, generation idempotency, and validation model.
4. Implement initial Smart Store and Coupang draft adapters using currently confirmed product-specific data.
5. Build unified registration inbox and marketplace-specific settings/editor panels.
6. Add submission jobs, worker calls, external API clients, attempt history, and bulk execution.
7. Add recipe-driven title/attribute extensions as separate scoped follow-up work.

## Reference Notes

Documentation consulted during discovery:

- Naver Commerce API Context7 documentation library: `/websites/apicenter_commerce_naver`
- Coupang Developers Portal Context7 documentation library: `/websites/developers_coupang`
- Naver Smart Store seller help on product registration precautions:
  `https://help.sell.smartstore.naver.com/faq/content.help?faqId=15745`

The Smart Store seller help page confirms that product-name, option-name, model-name, attribute, detail-description, and detail-spec information are marketplace-specific listing concerns, supporting an adapter-owned extensible payload design.
