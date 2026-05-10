# Auto-Selp Project Implementation State (2026-05-11)

## 1. DB Schema (Auth Service)
**Table: `users`**
- `id`: UUID (Primary Key)
- `username`: String (Unique, Indexed)
- `hashed_password`: String (PBKDF2-SHA256)
- `is_admin`: Boolean
- `encrypted_api_keys`: JSON (AES-256 Fernet encrypted values)

## 2. API Specifications
### Auth Service (Port 8001 / Gateway /api/auth/)
- `GET /health`: Health check
- `POST /register`: User registration
- `POST /token`: Login & JWT acquisition
- `GET /me`: Current user info (JWT required)

## 3. Infrastructure Configuration
- **API Gateway**: Nginx on port 80.
- **Database**: PostgreSQL 16 on port 5432.
- **Cache/Queue**: Redis 7 on port 6379.
- **Encryption**: AES-256 (Fernet) with a 32-byte base64 key.

## 4. Tech Stack Details
- **FastAPI**: Main web framework.
- **LLM Support**: Multi-provider support (Gemini, OpenAI).
    - Gemini: `gemini-3.1-flash-lite`
    - OpenAI: `gpt-5.4-nano`
- **Celery**: Task queue for async processing.
