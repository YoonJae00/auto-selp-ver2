# Auto-Selp Project Implementation State

Last updated: 2026-05-28

This document is the current implementation snapshot. For active backlog items, use `TODO.md` and GitHub open issues as the source of truth. Older files under `docs/superpowers/plans/` are historical planning artifacts; unchecked boxes there are not reliable status indicators.

## 1. Current Priority Queue

1. GitHub #43: KIPRIS copyright/trademark UX cleanup
   - Move KIPRIS/LLM suspected keyword information into the Intelligence Capsule trace view.
   - Distinguish KIPRIS-confirmed exclusions from LLM-suspected exclusions.
   - Show an explicit "no trademark issue" state when applicable.
   - Remove legacy `TrademarkModal.tsx` and unused modal CSS after the inline trace UX is complete.

2. GitHub #45: PlayAuto export and column mapping
   - Define the PlayAuto bulk registration Excel schema.
   - Map processed/stored product data to PlayAuto output fields.
   - Connect wholesale-site Visual Column Mapper results to PlayAuto field mapping.

3. GitHub #32: Batch processing optimization
   - Parallelize LLM calls for larger datasets.
   - Keep rate limits and KIPRIS monthly limits in mind.

4. GitHub #33: User API key management
   - Build UI for user-managed Naver/Coupang credentials.
   - Backend model already documents `encrypted_api_keys`; implementation should verify current API support before adding UI.

5. GitHub #34: Mobile responsive UI
   - Audit Dashboard, Process, Settings, and Intelligence Capsule drawer/detail views on tablet and mobile widths.

6. GitHub #35: CI/CD pipeline
   - Add GitHub Actions for automated tests and deployment checks.

7. GitHub #47: 내일할일 도매처 Naver/Coupang 등록 양식 대응 및 AI 가공 파이프라인 연계
   - '내일할일' Excel 레이아웃의 데이터 파싱 및 column mapping 연동
   - Naver Smart Store 및 Coupang Wing 전용 대량 엑셀 등록 서식 구조 정의 및 export API 구현
   - 네이버/쿠팡 노출 가이드(글자수 제한, 상표권/금지어 필터링, 검색 태그 추출)에 맞춤화된 AI 가공 프롬프트 및 파이프라인 추가
   - 상품 목록 Dashboard에서 네이버/쿠팡 전용 엑셀 다운로드 UI 통합

## 2. Implemented Backend

### Auth Service (Port 8001)

- JWT-based Register/Login/Me flow.
- HttpOnly cookie authentication and logout support.
- Google and Naver OAuth2 integration.
- Admin registration guarded by secret key.
- User profile nickname support.
- Password hashing and Fernet-based API key encryption utilities.
- CORS enabled for frontend integration.

### Product Processor Service (Port 8002)

- FastAPI upload/status/download API.
- Celery + Redis async processing pipeline.
- Excel processing with configurable column mapping.
- `.xls` and `.xlsx` output normalized to `_processed.xlsx` through `openpyxl`.
- LLM provider selection through Gemini/OpenAI client factory.
- Prompt manager backed by the `prompts` table.
- Keyword curation with Naver Search AD data, blacklist filtering, LLM brand classification, and KIPRIS MCP verification.
- KIPRIS optimization: only LLM `brand_suspected` keywords are checked against KIPRIS when KIPRIS is enabled.
- KIPRIS disabled mode: LLM-suspected brand keywords are excluded with `llm_suspected` warnings.
- Celery progress metadata includes `stage`, `current_name`, `completed_rows`, warnings, per-stage timings, refined names, keywords, filtered keywords, and category results.
- **PostgreSQL Product Management DB (NEW)**: Core/Platform 1:N extensible database schema utilizing JSONB for schema-less marketplace customization. Direct Celery upsert to `products` and `product_platform_mappings` per row.
- **DB REST APIs (NEW)**: `POST /process-db` (bulk inserts products as pending and starts Celery), `GET /products` (paginated, searchable, status-filtered, import-batch filtered), `POST /products/export` (streams memory-buffered Excel), and `GET /imports` (lists import history).
- **Wholesale Management & Smart Upsert (NEW, GitHub #46)**: Wholesale-site metadata and JSONB column mappings, supplier upload schema ingestion, formatted option-price parsing, and SMART UPSERT change tracking for price/stock updates.
- **Marketplace Draft Notification (NEW)**: Successful DB product processing now commits the completed product first, then best-effort requests marketplace draft generation through the internal marketplace API. Notification failures are stored as `marketplace_generation` warnings and do not fail the processed product.

### Marketplace Listing Service (Port 8003)

- Dedicated marketplace API/worker boundary for listing preparation, separate from the processor service.
- Market account storage with encrypted credentials and account-scoped marketplace settings for connection, fulfillment, claim, listing defaults, and generation rules.
- Protected internal draft-generation job API and Celery worker task that retrieves processor snapshots and generates reviewable listing drafts.
- Protected processor product snapshot contract containing product-specific registration ingredients, including origin, images, detail content, options, prices, and market category mappings.
- Smart Store and Coupang adapter-based draft generation from processor snapshots, storing channel-native JSON payloads with adapter and recipe versions.
- Marketplace-specific pricing policy calculation with cost, proposed sale price, expected profit, and achieved margin summaries.
- Versioned draft payloads, structured validation, and PostgreSQL-verified concurrency protection for stale generation, active draft insert contention, and `submitting` drafts.
- Authenticated draft query APIs for the future registration inbox.
- CORS middleware configured to allow cross-origin requests from the Next.js frontend, preventing 'Failed to fetch' browser errors.
- External marketplace submission calls and registration UI are intentionally deferred.

## 3. Implemented Frontend

- Next.js App Router frontend on port 3000.
- Zustand auth store with persistent auth state.
- Login/Register UI with social login buttons and nickname support.
- AI Mall layout with sidebar navigation.
- Dashboard command center layout with KPI cards, progress bar, and action queue components.
- Process page with Excel upload, column mapping, LLM provider usage, KIPRIS toggle usage, and background task creation.
- Settings page for global LLM provider, KIPRIS verification toggle, and persisted column mapping.
- Global `taskStore` persisted in localStorage.
- Stable global polling through `useTaskPolling`, guarded by auth state and using `useTaskStore.getState()` inside the polling interval.
- Intelligence Capsule mounted in the AI Mall layout with task list, progress state, accordion/detail trace view, shimmer active stage, and completed row stage timing display.
- **Product Management Page (NEW)**: A premium Apple-inspired dashboard grid supporting multi-checkbox selection, text search debouncing, processing status filters, upload-batch filters, pagination controls, real-time status badges, and customized Excel exports.
- **Wholesale Upload & Visual Column Mapper (NEW, GitHub #46)**: `/upload` supports wholesale-site management, drag-and-drop supplier Excel uploads, supplier-specific field mapping, and product-list filters/badges for wholesale update tracking.
- **PillButton Upgrade (NEW)**: Added support for `disabled` prop on `PillButton` to control double-form submissions.
- **Real-Time Product List Syncing (NEW)**: Integrated the local product processing grid (`/process`) with the global Zustand `taskStore`. The UI now dynamically overlays progress (`processing`, `completed`, `failed` statuses, AI refined names, and keywords) in real-time as Celery tasks run in the background (Approach 2), with an automatic DB refetch exactly once when the task finishes.
- **Product Processing UX Enhancements (NEW)**: Added a dynamic page size selection filter dropdown (10, 30, 50, 100, 200 products) with an optimized 30-product default view. Added a native checkbox selector in the table's first column header (`선택` column of `<thead>`) to handle page-wide select-all toggle, replacing the secondary `PillButton` control for better visual clarity and standard UX conventions.
- **Sidebar Clickability, Layout Alignment, & Automatic Collapsing Fix (NEW)**: Resolved sidebar unclickability and icon misalignment issues on dense pages (such as `/process`) by adding a stacking context (`z-index: 100`) to `.sidebar` and setting `display: none` on `.sidebarCollapsed .navLabel`. Also resolved the ultimate root cause of UI unresponsiveness: fixed a critical React infinite rendering loop in `ProcessPage`'s task synchronization hook by replacing a state-driven previous task tracker with `useRef`. Additionally, fixed the automatic sidebar collapse regression for dense workspaces (`/process`, `/products`, `/upload`) by implementing workspace-aware separate localStorage preferences (`autoselp.sidebarCollapsed.dense` and `autoselp.sidebarCollapsed.normal`) to prevent a global user toggle preference from permanently disabling the automatic page-specific collapse behavior.
- **Premium Landing Page Redesign (NEW)**: Completely overhauled the landing page with an Apple-inspired minimalist design, featuring high-fidelity responsive sections, a frosted-glass header with primary and secondary pill buttons, and an interactive **Live Task Graph** (`LiveTaskGraph.tsx`) that visualizes Auto-Selp's 5-stage AI processing pipeline (Upload, Refining, Keywords & Trademark, Category Mapping, Smart Upsert & Sync) with glowing SVG animated flows and live data panels.

## 4. Data Model Snapshot

### `users`

- `id`: UUID primary key
- `username`: unique login ID/email
- `nickname`: display name
- `hashed_password`: nullable for OAuth users
- `is_admin`: boolean
- `provider`: `local`, `google`, or `naver`
- `provider_id`: OAuth provider identifier
- `encrypted_api_keys`: encrypted credential payload

### `prompts`

- `key`: prompt identifier
- `template`: prompt text
- `description`: human-readable description
- `updated_at`: timestamp

### `product_imports` (NEW)

- `id`: UUID primary key
- `user_id`: foreign key to users
- `filename`: Excel file name
- `status`: `pending`, `processing`, `completed`, `failed`
- `total_count`: total records
- `processed_count`: processed records
- `created_at`: timestamp
- `updated_at`: timestamp

### `products` (NEW)

- `id`: UUID primary key
- `user_id`: foreign key to users
- `import_id`: foreign key to product_imports
- `original_name`: core raw product name
- `refined_name`: refined product name
- `keywords`: array of strings
- `status`: `pending`, `processing`, `completed`, `failed`
- `warnings`: JSONB list of warnings
- `raw_metadata`: JSONB key-value metadata
- `created_at`: timestamp
- `updated_at`: timestamp

### `product_platform_mappings` (NEW)

- `id`: UUID primary key
- `product_id`: foreign key to products (Cascade on delete)
- `platform_name`: `naver`, `coupang`, etc.
- `category_id`: platform-specific category ID
- `category_path`: full human-readable category path
- `sync_status`: `pending`, `syncing`, `synced`, `failed`
- `sync_error`: error log string
- `mapped_attributes`: JSONB schema-less custom attributes
- `created_at`: timestamp
- `updated_at`: timestamp

## 5. Known Gaps And Cleanup

- KIPRIS trace UX is only partially inline today: completed keyword stages show filtered keywords, but they do not yet distinguish KIPRIS-confirmed vs LLM-suspected exclusions or show an explicit no-issue state.
- `frontend/src/app/(ai-mall)/process/TrademarkModal.tsx` remains in the tree as a legacy unused component.
- `frontend/src/app/(ai-mall)/process/process.module.css` still contains legacy TrademarkModal styles.
- Historical plan documents contain stale unchecked boxes. Treat them as design/implementation history unless a current TODO or GitHub issue references the work.

## 6. Tech Stack

- FastAPI
- SQLAlchemy
- PostgreSQL 16
- Celery 5
- Redis 7
- Nginx API gateway
- Next.js 14
- React 18
- Zustand
- Vanilla CSS modules
- Gemini and OpenAI LLM clients
- KIPRIS MCP integration

## 7. Continuous Improvement & Knowledge Compounding

- **Compound Engineering Integration**: Completed local installation of `EveryInc/compound-engineering-plugin` core skills (including `/ce-compound`, `/ce-sessions`, `/ce-plan`) under `./.antigravitycli/skills/`.
- **Workflow Automation**: Integrated the Compound workflow into `AGENTS.md` instructions. Agents will automatically check `docs/solutions/` before work and run `/ce-compound mode:headless` after successfully completing/merging dev branches or implementing code review fixes to capture valuable lessons, preventing repeated regressions.
- **Knowledge Base**: Established `docs/solutions/` directory for searchable knowledge storage of past solutions (bugs, architectural patterns, conventions).
- **GitHub MCP Fix (2026-05-20)**: Resolved JSON parsing error by initializing empty `mcp_config.json` with `{}` and successfully authenticated the remote Copilot MCP server using token headers in `settings.json` and plugin configurations, resolving OAuth issues.
