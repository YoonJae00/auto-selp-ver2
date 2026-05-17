# Auto-Selp Project Implementation State (2026-05-17)

## 1. DB Schema (Auth & Processor)
**Table: `users`**
- `id`: UUID (Primary Key)
- `username`: String (Unique, Indexed, used as login ID/Email)
- `nickname`: String (Display name)
- `hashed_password`: String (Nullable for OAuth users)
- `is_admin`: Boolean
- `provider`: String (local, google, naver)
- `provider_id`: String (OAuth unique identifier)
- `encrypted_api_keys`: JSON (AES-256 encrypted)

**Table: `prompts`**
- `key`: String (Primary Key, e.g., 'refine_name')
- `template`: Text
- `description`: String
- `updated_at`: DateTime

## 2. Implemented Services

### Auth Service (Port 8001)
- JWT-based authentication flow (Register/Login/Me).
- **Multi-Provider Support**: Google and Naver OAuth2 integration.
- **Secure Admin Registration**: Requires a secret key for admin account creation.
- **Profile Management**: Support for display names (`nickname`).
- Password hashing and API key encryption (Fernet).
- CORS enabled for frontend integration.

### Product Processor Service (Port 8002)
- Async pipeline using Celery & Redis.
- **Stage 1 (Refine)**: Gemini 3.1 Flash-Lite / GPT-4o based naming refinement.
- **Stage 2 (Keyword)**: 3-Phase curation with Naver Search AD API (Signature & Encoding fixed).
- **Stage 3 (Category)**: Naver/Coupang individual category matching (Independent columns).
- **Infrastructure**: Shared Docker volume (`uploads_data`) for Processor and Worker containers.

- **Frontend (Port 3000)**
- **Auth**: Zustand-based persistent state management.
- **Login/Register**: Redesigned UI with social login buttons and nickname support.
- **UI**: Apple-style design, Drag & Drop Excel upload, column mapping dropdowns.
- **Dashboard**: Implemented 3-tier Command Center layout with refined workspace padding and soft background for premium feel.
- **Components**: Reusable Dashboard components (KpiCard, ProgressBar, ActionItem) with Vanilla CSS modules.
- **Intelligence Capsule**: Apple Intelligence-inspired global status indicator with Siri-glow animation and glassmorphism.
- **Task Polling**: Global `useTaskPolling` hook for background status monitoring (Stabilized with stable frequency and Auth Guard).
- **Settings**: Global LLM engine selection and mapping persistence (LocalStorage).


## 3. Tech Stack Details
- **FastAPI**: Main backend framework.
- **LLM Support**: Gemini 3.1 Flash-Lite, OpenAI gpt-5.4-nano.
- **Celery**: Persistent worker processes for heavy tasks.
- **Nginx**: API Gateway for service routing.
