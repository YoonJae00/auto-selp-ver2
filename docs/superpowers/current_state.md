# Auto-Selp Project Implementation State

Last updated: 2026-05-20

This document is the current implementation snapshot. For active backlog items, use `TODO.md` and GitHub open issues as the source of truth. Older files under `docs/superpowers/plans/` are historical planning artifacts; unchecked boxes there are not reliable status indicators.

## 1. Current Priority Queue

1. GitHub #43: KIPRIS copyright/trademark UX cleanup
   - Move KIPRIS/LLM suspected keyword information into the Intelligence Capsule trace view.
   - Distinguish KIPRIS-confirmed exclusions from LLM-suspected exclusions.
   - Show an explicit "no trademark issue" state when applicable.
   - Remove legacy `TrademarkModal.tsx` and unused modal CSS after the inline trace UX is complete.

2. GitHub #42: Product DB migration
   - Move from Excel-only output management to PostgreSQL-backed product records.
   - Add `products` schema, Celery upsert, list/detail/delete APIs, product list UI, search/filter/edit, and Excel export.

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

## 5. Known Gaps And Cleanup

- KIPRIS trace UX is only partially inline today: completed keyword stages show filtered keywords, but they do not yet distinguish KIPRIS-confirmed vs LLM-suspected exclusions or show an explicit no-issue state.
- `frontend/src/app/(ai-mall)/process/TrademarkModal.tsx` remains in the tree as a legacy unused component.
- `frontend/src/app/(ai-mall)/process/process.module.css` still contains legacy TrademarkModal styles.
- Product results are still primarily file-based; no `products` table or product management UI exists yet.
- Historical plan documents contain stale unchecked boxes. Treat them as design/implementation history unless a current TODO or GitHub issue references the work.

## 6. Tech Stack

- FastAPI
- SQLAlchemy
- PostgreSQL
- Celery
- Redis
- Nginx API gateway
- Next.js
- React
- Zustand
- Vanilla CSS modules
- Gemini and OpenAI LLM clients
- KIPRIS MCP integration

## 7. Continuous Improvement & Knowledge Compounding

- **Compound Engineering Integration**: Completed local installation of `EveryInc/compound-engineering-plugin` core skills (including `/ce-compound`, `/ce-sessions`, `/ce-plan`) under `./.antigravitycli/skills/`.
- **Workflow Automation**: Integrated the Compound workflow into `AGENTS.md` instructions. Agents will automatically check `docs/solutions/` before work and run `/ce-compound mode:headless` after successfully completing/merging dev branches or implementing code review fixes to capture valuable lessons, preventing repeated regressions.
- **Knowledge Base**: Established `docs/solutions/` directory for searchable knowledge storage of past solutions (bugs, architectural patterns, conventions).
- **GitHub MCP Fix (2026-05-20)**: Resolved JSON parsing error by initializing empty `mcp_config.json` with `{}` and successfully authenticated the remote Copilot MCP server using token headers in `settings.json` and plugin configurations, resolving OAuth issues.
