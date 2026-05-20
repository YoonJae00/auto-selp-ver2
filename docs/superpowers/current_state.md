# Auto-Selp Project Implementation State

Last updated: 2026-05-20

This document is the current implementation snapshot. For active backlog items, use `TODO.md` and GitHub open issues as the source of truth. Older files under `docs/superpowers/plans/` are historical planning artifacts; unchecked boxes there are not reliable status indicators.

## 1. Current Priority Queue

1. GitHub #43: KIPRIS copyright/trademark UX cleanup
   - Move KIPRIS/LLM suspected keyword information into the Intelligence Capsule trace view.
   - Distinguish KIPRIS-confirmed exclusions from LLM-suspected exclusions.
   - Show an explicit "no trademark issue" state when applicable.
   - Remove legacy `TrademarkModal.tsx` and unused modal CSS after the inline trace UX is complete.

2. GitHub #32: Batch processing optimization
   - Parallelize LLM calls for larger datasets.
   - Keep rate limits and KIPRIS monthly limits in mind.

3. GitHub #33: User API key management
   - Build UI for user-managed Naver/Coupang credentials.
   - Backend model already documents `encrypted_api_keys`; implementation should verify current API support before adding UI.

4. GitHub #34: Mobile responsive UI
   - Audit Dashboard, Process, Settings, and Intelligence Capsule drawer/detail views on tablet and mobile widths.

5. GitHub #35: CI/CD pipeline
   - Add GitHub Actions for automated tests and deployment checks.

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
- **PillButton Upgrade (NEW)**: Added support for `disabled` prop on `PillButton` to control double-form submissions.

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
