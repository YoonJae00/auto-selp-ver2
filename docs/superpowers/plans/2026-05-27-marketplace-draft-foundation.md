# Marketplace Draft Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an isolated marketplace backend that consumes processed-product snapshots and generates reviewable Smart Store and Coupang listing drafts for connected market accounts.

**Architecture:** `processor` remains the source of normalized product data and sends a best-effort generation notification after processing success. A new `marketplace` API/worker pair owns market accounts, versioned settings, generation jobs, adapter-generated JSON drafts, and validation results; it calls a processor snapshot API over an authenticated internal HTTP contract rather than reading processor tables. This phase stops before frontend screens and before real marketplace submission calls.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async/PostgreSQL, Celery/Redis, HTTPX, Pydantic Settings, python-jose, cryptography/Fernet, pytest/pytest-asyncio, Docker Compose, Nginx.

**Origin Design:** `docs/superpowers/specs/2026-05-27-marketplace-listing-service-design.md`

---

## Scope Boundary

Included in this plan:

- `marketplace-api` and `marketplace-worker` containers with gateway routing.
- Marketplace-owned account/settings, generation-job, and draft persistence.
- JWT user access for account/draft endpoints and service-token access for internal generation/snapshot endpoints.
- Processor marketplace snapshot API.
- Best-effort processor notification after one product is successfully processed.
- Initial Smart Store and Coupang adapters for currently available product data:
  name ingredients, price, origin, list/detail images, option variants, and category candidates.
- Marketplace-account-specific pricing policy persistence and backend margin calculation for draft price/profit summaries.
- Draft generation idempotency, unsubmitted regeneration, summary fields, versioned recipes, and structured validation.
- Backend tests and a Docker smoke verification path.

Deferred to subsequent plans:

- `/marketplaces` frontend inbox, marketplace-specific settings panels, and draft editing.
- Interactive margin-calculator UI, bulk price recalculation controls, and per-product sale-price overrides.
- `override_patch` mutation UI/API beyond reserving the storage field.
- External Smart Store/Coupang registration submission and submission jobs/attempts.
- Automatic SEO/title or category-attribute enrichment beyond deterministic initial recipe stubs.
- Already-submitted product update synchronization.
- Multiple marketplace accounts exposed through the UI.

## Existing Patterns To Follow

- Use the service structure already established by `services/processor/main.py`, `services/processor/database.py`, `services/processor/config.py`, `services/processor/celery_app.py`, and `services/processor/Dockerfile`.
- Route services through `nginx/nginx.conf` using an upstream and `/api/<service>/` prefix.
- Use existing JWT cookie/Bearer decoding behavior from `services/processor/main.py:get_current_user` for browser-facing marketplace routes.
- Preserve `services/processor/graphs/product_processor.py` as the product-level success boundary and keep marketplace generation failure non-fatal to product processing.
- Store extensible channel data in JSON columns, consistent with `ProductPlatformMapping.mapped_attributes` and wholesale mapping storage.
- Run focused tests from within each service with `PYTHONPATH=.` when imports are module-relative.

## File Structure

### New Marketplace Service

- Create `services/marketplace/Dockerfile`
  - Build and run the marketplace FastAPI container on port `8003`.
- Create `services/marketplace/requirements.txt`
  - Runtime and test dependencies matching repository conventions.
- Create `services/marketplace/config.py`
  - Database, Redis, JWT, encryption, processor URL, and internal-token settings.
- Create `services/marketplace/database.py`
  - Marketplace SQLAlchemy base/session.
- Create `services/marketplace/security.py`
  - Encrypt/decrypt marketplace credential JSON.
- Create `services/marketplace/auth.py`
  - Browser-user JWT dependency and internal service-token dependency.
- Create `services/marketplace/models.py`
  - `MarketAccount`, `MarketAccountSettings`, `MarketDraftGenerationJob`, and `MarketListingDraft`.
- Create `services/marketplace/schemas.py`
  - API requests/responses, snapshot DTOs, validation DTOs, and adapter result DTOs.
- Create `services/marketplace/main.py`
  - Health, account/settings, generation, and draft query endpoints.
- Create `services/marketplace/celery_app.py`
  - Celery app scoped to the marketplace service.
- Create `services/marketplace/tasks.py`
  - Generation task wrapper and async execution entrypoint.
- Create `services/marketplace/clients/processor_client.py`
  - Internal HTTP client for processor snapshot retrieval.
- Create `services/marketplace/adapters/base.py`
  - Shared adapter interface and registry.
- Create `services/marketplace/adapters/smartstore.py`
  - Initial Smart Store draft conversion and validation.
- Create `services/marketplace/adapters/coupang.py`
  - Initial Coupang draft conversion and validation.
- Create `services/marketplace/services/draft_generation.py`
  - Connected-account iteration, adapter execution, draft upsert, and job status behavior.
- Create `services/marketplace/services/pricing.py`
  - Marketplace-account policy validation and proposed sale-price/profit calculation.

### Marketplace Tests

- Create `services/marketplace/tests/conftest.py`
  - Environment defaults and reusable fake objects/dependency overrides.
- Create `services/marketplace/tests/test_health.py`
  - Service health surface.
- Create `services/marketplace/tests/test_security.py`
  - Credential encryption.
- Create `services/marketplace/tests/test_accounts.py`
  - Account/settings ownership and credential response safety.
- Create `services/marketplace/tests/test_adapters.py`
  - Smart Store/Coupang payload conversion and structured validation.
- Create `services/marketplace/tests/test_draft_generation.py`
  - Generation idempotency, account selection, regeneration, and summary fields.
- Create `services/marketplace/tests/test_pricing.py`
  - Fee/margin formula, rounding, and invalid-policy validation.
- Create `services/marketplace/tests/test_generation_api.py`
  - Internal request authentication and job scheduling.

### Processor Integration

- Modify `services/processor/config.py`
  - Marketplace URL and internal service token.
- Create `services/processor/clients/marketplace_client.py`
  - Best-effort generation notification client.
- Modify `services/processor/schemas.py`
  - Processor snapshot response DTO.
- Modify `services/processor/main.py`
  - Internal snapshot endpoint and internal-token verification.
- Modify `services/processor/graphs/product_processor.py`
  - Invoke optional notifier only after successful product persistence.
- Modify `services/processor/tasks.py`
  - Construct notifier dependency for graph context.
- Modify `services/processor/tests/test_product_processor_graph.py`
  - Success/failure notification behavior.
- Create `services/processor/tests/test_marketplace_snapshot.py`
  - Snapshot contract and authorization tests.

### Deployment Wiring

- Modify `docker-compose.yml`
  - Add `marketplace` and `marketplace-worker`, and wire gateway dependency.
- Modify `nginx/nginx.conf`
  - Proxy `/api/marketplace/` to port `8003`.

## API Contracts Fixed By This Plan

Browser-authenticated marketplace endpoints:

```text
POST /api/marketplace/accounts
GET  /api/marketplace/accounts
PUT  /api/marketplace/accounts/{account_id}/settings
GET  /api/marketplace/drafts
GET  /api/marketplace/drafts/{draft_id}
```

Internal service endpoints:

```text
POST /api/marketplace/internal/draft-generation-jobs
GET  /api/processor/internal/products/{product_id}/marketplace-snapshot?user_id={uuid}
```

Every internal request sends:

```http
X-Internal-Service-Token: <INTERNAL_SERVICE_TOKEN>
```

The processor notification body is:

```json
{
  "source_product_id": "uuid",
  "source_product_updated_at": "2026-05-27T10:20:00Z",
  "source_user_id": "uuid",
  "reason": "processing_completed"
}
```

---

### Task 1: Scaffold The Marketplace Service And Route It Through Docker

**Files:**
- Create: `services/marketplace/requirements.txt`
- Create: `services/marketplace/Dockerfile`
- Create: `services/marketplace/config.py`
- Create: `services/marketplace/database.py`
- Create: `services/marketplace/main.py`
- Create: `services/marketplace/tests/conftest.py`
- Create: `services/marketplace/tests/test_health.py`
- Modify: `docker-compose.yml`
- Modify: `nginx/nginx.conf`

- [ ] **Step 1: Write the failing health test**

Create `services/marketplace/tests/conftest.py` with environment defaults required at import time:

```python
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
os.environ.setdefault("PROCESSOR_BASE_URL", "http://processor:8002")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")
```

Create `services/marketplace/tests/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_marketplace_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "marketplace"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_health.py -v
```

Expected: FAIL because the `marketplace` service modules do not exist.

- [ ] **Step 3: Create the minimal service runtime**

Create `services/marketplace/requirements.txt`:

```text
fastapi
uvicorn
sqlalchemy[asyncio]
asyncpg
pydantic-settings
python-jose[cryptography]
cryptography
redis
celery
httpx
pytest
pytest-asyncio
```

Create `services/marketplace/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
```

Create `services/marketplace/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    PROCESSOR_BASE_URL: str = "http://processor:8002"
    INTERNAL_SERVICE_TOKEN: str

    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")


settings = Settings()
```

Create `services/marketplace/database.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session
        await session.commit()
```

Create `services/marketplace/main.py`:

```python
from fastapi import FastAPI


app = FastAPI(title="Auto-Selp Marketplace Listing")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "marketplace"}
```

- [ ] **Step 4: Route and compose the new service**

Add to `docker-compose.yml` under `services`:

```yaml
  marketplace:
    build: ./services/marketplace
    env_file: .env
    ports:
      - "8003:8003"
    depends_on:
      - db
      - redis

  marketplace-worker:
    build: ./services/marketplace
    command: celery -A tasks.celery_app worker --loglevel=info
    env_file: .env
    depends_on:
      - db
      - redis
    restart: always
```

Add `marketplace` to `gateway.depends_on`, then add this upstream and location in `nginx/nginx.conf`:

```nginx
    upstream marketplace_service {
        server marketplace:8003;
    }

        location /api/marketplace/ {
            proxy_pass http://marketplace_service/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```

- [ ] **Step 5: Run focused verification**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_health.py -v
cd ../..
docker compose config --quiet
```

Expected: health test PASS; Docker Compose configuration exits with status `0`.

- [ ] **Step 6: Commit**

```bash
git add services/marketplace docker-compose.yml nginx/nginx.conf
git commit -m "feat(marketplace): scaffold listing service containers"
```

### Task 2: Add Marketplace Account, Settings, Job, And Draft Persistence

**Files:**
- Create: `services/marketplace/models.py`
- Create: `services/marketplace/schemas.py`
- Create: `services/marketplace/security.py`
- Create: `services/marketplace/tests/test_security.py`
- Create: `services/marketplace/tests/test_models.py`
- Modify: `services/marketplace/main.py`

- [ ] **Step 1: Write failing credential and model tests**

Create `services/marketplace/tests/test_security.py`:

```python
from security import decrypt_credentials, encrypt_credentials


def test_market_credentials_are_encrypted_as_one_json_document():
    credentials = {"client_id": "id", "client_secret": "secret"}

    encrypted = encrypt_credentials(credentials)

    assert "secret" not in encrypted
    assert decrypt_credentials(encrypted) == credentials
```

Create `services/marketplace/tests/test_models.py`:

```python
from models import (
    MarketAccount,
    MarketAccountSettings,
    MarketDraftGenerationJob,
    MarketListingDraft,
)


def test_marketplace_models_use_distinct_owned_tables():
    assert MarketAccount.__tablename__ == "market_accounts"
    assert MarketAccountSettings.__tablename__ == "market_account_settings"
    assert MarketDraftGenerationJob.__tablename__ == "market_draft_generation_jobs"
    assert MarketListingDraft.__tablename__ == "market_listing_drafts"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_security.py tests/test_models.py -v
```

Expected: FAIL with missing `security` or `models` imports.

- [ ] **Step 3: Implement encryption utility and database models**

Create `services/marketplace/security.py`:

```python
import json

from cryptography.fernet import Fernet

from config import settings

fernet = Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_credentials(credentials: dict[str, str]) -> str:
    serialized = json.dumps(credentials, ensure_ascii=True, sort_keys=True)
    return fernet.encrypt(serialized.encode()).decode()


def decrypt_credentials(encrypted: str) -> dict[str, str]:
    serialized = fernet.decrypt(encrypted.encode()).decode()
    return json.loads(serialized)
```

Create `services/marketplace/models.py` with these model responsibilities and constraints:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database import Base


class MarketAccount(Base):
    __tablename__ = "market_accounts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    market_code: Mapped[str] = mapped_column(String, index=True)
    display_name: Mapped[str] = mapped_column(String)
    credentials_encrypted: Mapped[str] = mapped_column(Text)
    connection_status: Mapped[str] = mapped_column(String, default="connected")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    settings = relationship("MarketAccountSettings", back_populates="account", uselist=False, cascade="all, delete-orphan")
    drafts = relationship("MarketListingDraft", back_populates="account")

class MarketAccountSettings(Base):
    __tablename__ = "market_account_settings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("market_accounts.id", ondelete="CASCADE"), unique=True)
    settings_schema_version: Mapped[str] = mapped_column(String, default="v1")
    connection_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fulfillment_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    claim_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    listing_defaults: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    account = relationship("MarketAccount", back_populates="settings")


class MarketDraftGenerationJob(Base):
    __tablename__ = "market_draft_generation_jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source_product_id: Mapped[uuid.UUID] = mapped_column(index=True)
    requested_source_version: Mapped[str] = mapped_column(String)
    generated_source_version: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MarketListingDraft(Base):
    __tablename__ = "market_listing_drafts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_product_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source_product_version: Mapped[str] = mapped_column(String)
    market_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("market_accounts.id", ondelete="CASCADE"), index=True)
    market_code: Mapped[str] = mapped_column(String, index=True)
    draft_kind: Mapped[str] = mapped_column(String, default="create")
    status: Mapped[str] = mapped_column(String, default="generated")
    display_title: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sale_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_profit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_margin_rate: Mapped[float | None] = mapped_column(nullable=True)
    primary_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    generated_payload: Mapped[dict] = mapped_column(JSON)
    override_patch: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_result: Mapped[dict] = mapped_column(JSON)
    adapter_version: Mapped[str] = mapped_column(String)
    recipe_versions: Mapped[dict] = mapped_column(JSON)
    remote_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    account = relationship("MarketAccount", back_populates="drafts")

    __table_args__ = (UniqueConstraint("source_product_id", "market_account_id", "draft_kind", name="uq_active_product_account_draft"),)
```

- [ ] **Step 4: Create response/request schema surface and initialize tables**

Create `services/marketplace/schemas.py` with Pydantic models covering:

```python
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MarketAccountCreate(BaseModel):
    market_code: str
    display_name: str
    credentials: dict[str, str]


class MarketAccountResponse(BaseModel):
    id: UUID
    market_code: str
    display_name: str
    connection_status: str
    is_primary: bool
    model_config = ConfigDict(from_attributes=True)


class MarketAccountSettingsUpdate(BaseModel):
    settings_schema_version: str = "v1"
    connection_config: dict[str, Any] | None = None
    fulfillment_config: dict[str, Any] | None = None
    claim_config: dict[str, Any] | None = None
    listing_defaults: dict[str, Any] | None = None
    generation_rules: dict[str, Any] | None = None


class MarketAccountSettingsResponse(MarketAccountSettingsUpdate):
    id: UUID
    market_account_id: UUID
    model_config = ConfigDict(from_attributes=True)
```

Modify `services/marketplace/main.py` startup:

```python
from database import Base, engine
import models  # noqa: F401


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 5: Verify tests**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_security.py tests/test_models.py tests/test_health.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/marketplace
git commit -m "feat(marketplace): add owned listing persistence models"
```

### Task 3: Implement Authenticated Marketplace Account And Settings APIs

**Files:**
- Create: `services/marketplace/auth.py`
- Modify: `services/marketplace/main.py`
- Modify: `services/marketplace/schemas.py`
- Create: `services/marketplace/tests/test_accounts.py`

- [ ] **Step 1: Write failing API ownership and secret-safety tests**

Create `services/marketplace/tests/test_accounts.py` using dependency overrides for `get_current_user` and `get_db`. Cover these exact cases:

```python
@pytest.mark.asyncio
async def test_create_account_encrypts_credentials_and_never_returns_them():
    response = await client.post(
        "/accounts",
        json={
            "market_code": "smartstore",
            "display_name": "내 스토어",
            "credentials": {"client_id": "id", "client_secret": "secret"},
        },
    )
    assert response.status_code == 200
    assert "credentials" not in response.json()
    assert "credentials_encrypted" not in response.json()
    assert saved_account.credentials_encrypted != "secret"


@pytest.mark.asyncio
async def test_update_settings_rejects_another_users_account():
    response = await client.put(
        f"/accounts/{other_users_account_id}/settings",
        json={"fulfillment_config": {"outboundLocationId": "OUT-1"}},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_accounts.py -v
```

Expected: FAIL because authenticated account routes do not exist.

- [ ] **Step 3: Implement user dependency and account routes**

Create `services/marketplace/auth.py` following the processor's JWT behavior:

```python
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


async def get_current_user(request: Request, token: str | None = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("access_token") or token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    result = await db.execute(text("SELECT id, username, is_admin FROM users WHERE username = :username"), {"username": username})
    user = result.fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


async def require_internal_service_token(x_internal_service_token: str | None = Header(default=None)):
    if x_internal_service_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal service token")
```

Add these routes to `services/marketplace/main.py`:

```python
@app.post("/accounts", response_model=MarketAccountResponse)
async def create_account(payload: MarketAccountCreate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = MarketAccount(
        user_id=current_user["id"],
        market_code=payload.market_code,
        display_name=payload.display_name,
        credentials_encrypted=encrypt_credentials(payload.credentials),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@app.get("/accounts", response_model=list[MarketAccountResponse])
async def list_accounts(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MarketAccount).where(MarketAccount.user_id == current_user["id"]))
    return result.scalars().all()


@app.put("/accounts/{account_id}/settings", response_model=MarketAccountSettingsResponse)
async def upsert_account_settings(account_id: UUID, payload: MarketAccountSettingsUpdate, current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await owned_account_or_404(db, account_id, current_user["id"])
    settings_row = account.settings or MarketAccountSettings(market_account_id=account.id)
    for field, value in payload.model_dump().items():
        setattr(settings_row, field, value)
    db.add(settings_row)
    await db.commit()
    await db.refresh(settings_row)
    return settings_row
```

Implement `owned_account_or_404()` as a single query filtered on both account id and `user_id`.

- [ ] **Step 4: Run account tests and the marketplace suite**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_accounts.py tests/test_security.py tests/test_health.py -v
```

Expected: PASS, including proof that returned account data has no credentials.

- [ ] **Step 5: Commit**

```bash
git add services/marketplace
git commit -m "feat(marketplace): add market account settings API"
```

### Task 4: Expose Processor Marketplace Snapshot Contract

**Files:**
- Modify: `services/processor/config.py`
- Modify: `services/processor/schemas.py`
- Modify: `services/processor/main.py`
- Create: `services/processor/tests/test_marketplace_snapshot.py`

- [ ] **Step 1: Write failing snapshot contract tests**

Create `services/processor/tests/test_marketplace_snapshot.py`. Use a fake DB result and internal-token header to test:

```python
@pytest.mark.asyncio
async def test_marketplace_snapshot_returns_normalized_registration_ingredients():
    response = await client.get(
        f"/internal/products/{product.id}/marketplace-snapshot",
        params={"user_id": str(product.user_id)},
        headers={"X-Internal-Service-Token": "internal-test-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == str(product.id)
    assert payload["origin"] == "해외|아시아|중국"
    assert payload["images"]["list"] == ["https://img/main.jpg"]
    assert payload["images"]["detail_content"] == "<img src='detail.jpg'>"
    assert payload["options"][0]["name"] == "블랙"
    assert payload["market_categories"]["smartstore"]["category_id"] == "50001"
    assert payload["market_categories"]["coupang"]["category_id"] == "70001"


@pytest.mark.asyncio
async def test_marketplace_snapshot_requires_internal_token_and_matching_owner():
    unauthorized = await client.get(snapshot_url)
    wrong_owner = await client.get(snapshot_url, params={"user_id": str(uuid.uuid4())}, headers=internal_headers)
    assert unauthorized.status_code == 401
    assert wrong_owner.status_code == 404
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd services/processor
PYTHONPATH=. pytest tests/test_marketplace_snapshot.py -v
```

Expected: FAIL because the endpoint and schemas are absent.

- [ ] **Step 3: Add internal token setting and snapshot schemas**

Add to `services/processor/config.py`:

```python
    MARKETPLACE_BASE_URL: str = "http://marketplace:8003"
    INTERNAL_SERVICE_TOKEN: str = "change-in-production"
```

Add response DTOs to `services/processor/schemas.py`:

```python
class MarketplaceSnapshotCategory(BaseModel):
    category_id: Optional[str] = None
    category_path: Optional[str] = None


class MarketplaceSnapshotResponse(BaseModel):
    product_id: UUID
    version: str
    product_code: Optional[str] = None
    wholesale_product_id: Optional[str] = None
    refined_name: Optional[str] = None
    brand_name: Optional[str] = None
    keywords: List[str] = []
    origin: Optional[str] = None
    price: Dict
    images: Dict
    options: List = []
    market_categories: Dict[str, MarketplaceSnapshotCategory]
```

- [ ] **Step 4: Implement internal snapshot endpoint**

In `services/processor/main.py`, add internal-token validation and a query that eagerly loads `Product.platform_mappings`, filters by product id and requested owner, and returns:

```python
{
    "product_id": product.id,
    "version": product.updated_at.isoformat(),
    "product_code": product.product_code,
    "wholesale_product_id": product.wholesale_product_id,
    "refined_name": product.refined_name,
    "brand_name": product.brand_name,
    "keywords": product.keywords or [],
    "origin": product.origin,
    "price": {
        "wholesale": product.price_wholesale,
        "retail": product.price_retail,
        "minimum_selling": product.price_min_selling,
    },
    "images": {
        "list": product.images_list or [],
        "detail_content": product.image_detail,
    },
    "options": product.option_variants or [],
    "market_categories": {
        mapping.platform_name: {
            "category_id": mapping.category_id,
            "category_path": mapping.category_path,
        }
        for mapping in product.platform_mappings
        if mapping.platform_name in {"naver", "smartstore", "coupang"}
    },
}
```

Normalize legacy `naver` mapping to response key `smartstore`, so marketplace adapters do not carry the processor's historical naming inconsistency.

- [ ] **Step 5: Verify processor tests**

Run:

```bash
cd services/processor
PYTHONPATH=. pytest tests/test_marketplace_snapshot.py tests/test_product_processor_graph.py tests/test_tasks.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/processor
git commit -m "feat(processor): expose marketplace product snapshot"
```

### Task 5: Implement Marketplace-Specific Pricing Policies And Margin Calculation

**Files:**
- Create: `services/marketplace/services/__init__.py`
- Create: `services/marketplace/services/pricing.py`
- Create: `services/marketplace/tests/test_pricing.py`

- [ ] **Step 1: Write failing pricing policy tests**

Create `services/marketplace/tests/test_pricing.py`:

```python
import pytest

from services.pricing import PricingPolicyError, calculate_proposed_price


def test_calculates_sale_price_and_achieved_margin_from_account_policy():
    policy = {
        "version": "smartstore-pricing:v1",
        "shippingCost": {"type": "fixed", "amount": 3000},
        "marketplaceFee": {"type": "percent_of_sale_price", "rate": 5.0},
        "advertisingCost": {"type": "percent_of_sale_price", "rate": 3.0},
        "otherCost": {"type": "fixed", "amount": 500},
        "targetMargin": {"type": "percent_of_sale_price", "rate": 25.0},
        "rounding": {"unit": 100, "mode": "ceil"},
    }

    result = calculate_proposed_price(cost_price=8000, policy=policy)

    assert result["policyVersion"] == "smartstore-pricing:v1"
    assert result["costPrice"] == 8000
    assert result["proposedSalePrice"] == 17200
    assert result["marketplaceFee"] == 860
    assert result["advertisingCost"] == 516
    assert result["expectedProfit"] == 4324
    assert round(result["expectedMarginRate"], 2) == 25.14


def test_missing_or_invalid_pricing_policy_blocks_draft_generation():
    with pytest.raises(PricingPolicyError, match="pricing policy is required"):
        calculate_proposed_price(cost_price=8000, policy=None)

    invalid = {
        "version": "coupang-pricing:v1",
        "marketplaceFee": {"type": "percent_of_sale_price", "rate": 60},
        "advertisingCost": {"type": "percent_of_sale_price", "rate": 20},
        "targetMargin": {"type": "percent_of_sale_price", "rate": 30},
    }
    with pytest.raises(PricingPolicyError, match="percentage rates must total less than 100"):
        calculate_proposed_price(cost_price=8000, policy=invalid)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_pricing.py -v
```

Expected: FAIL because the pricing service does not exist.

- [ ] **Step 3: Implement the deterministic pricing calculation**

Create `services/marketplace/services/__init__.py`:

```python
"""Marketplace domain services."""
```

Create `services/marketplace/services/pricing.py`:

```python
import math


class PricingPolicyError(ValueError):
    pass


def _fixed_amount(component: dict | None) -> int:
    if component and component.get("type") == "fixed":
        return int(component.get("amount", 0))
    return 0


def _percent_rate(component: dict | None) -> float:
    if component and component.get("type") == "percent_of_sale_price":
        return float(component.get("rate", 0)) / 100
    return 0.0


def calculate_proposed_price(cost_price: int | None, policy: dict | None) -> dict:
    if policy is None:
        raise PricingPolicyError("pricing policy is required")
    if cost_price is None:
        raise PricingPolicyError("cost price is required")

    shipping_cost = _fixed_amount(policy.get("shippingCost"))
    other_fixed = _fixed_amount(policy.get("otherCost"))
    marketplace_rate = _percent_rate(policy.get("marketplaceFee"))
    advertising_rate = _percent_rate(policy.get("advertisingCost"))
    other_rate = _percent_rate(policy.get("otherCost"))
    target_rate = _percent_rate(policy.get("targetMargin"))
    rate_total = marketplace_rate + advertising_rate + other_rate + target_rate
    if rate_total >= 1:
        raise PricingPolicyError("percentage rates must total less than 100")

    raw_price = (cost_price + shipping_cost + other_fixed) / (1 - rate_total)
    rounding = policy.get("rounding") or {"unit": 1, "mode": "ceil"}
    unit = int(rounding.get("unit", 1))
    proposed_price = int(math.ceil(raw_price / unit) * unit)
    marketplace_fee = round(proposed_price * marketplace_rate)
    advertising_cost = round(proposed_price * advertising_rate)
    other_cost = other_fixed + round(proposed_price * other_rate)
    expected_profit = proposed_price - cost_price - shipping_cost - marketplace_fee - advertising_cost - other_cost

    return {
        "policyVersion": policy.get("version", "pricing:v1"),
        "costPrice": cost_price,
        "proposedSalePrice": proposed_price,
        "shippingCost": shipping_cost,
        "marketplaceFee": marketplace_fee,
        "advertisingCost": advertising_cost,
        "otherCost": other_cost,
        "expectedProfit": expected_profit,
        "expectedMarginRate": expected_profit / proposed_price * 100,
    }
```

The calculation solves for the requested target margin before rounding. Rounding upward may produce a slightly higher achieved margin; the draft stores and later UI displays the achieved value.

- [ ] **Step 4: Run pricing tests**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_pricing.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/marketplace/services services/marketplace/tests/test_pricing.py
git commit -m "feat(marketplace): calculate account-specific draft pricing"
```

### Task 6: Implement Versioned Smart Store And Coupang Draft Adapters

**Files:**
- Create: `services/marketplace/adapters/__init__.py`
- Create: `services/marketplace/adapters/base.py`
- Create: `services/marketplace/adapters/smartstore.py`
- Create: `services/marketplace/adapters/coupang.py`
- Modify: `services/marketplace/schemas.py`
- Create: `services/marketplace/tests/test_adapters.py`

- [ ] **Step 1: Write failing adapter conversion and validation tests**

Create `services/marketplace/tests/test_adapters.py` with a normalized snapshot and deliberately separate per-market pricing policies:

```python
from copy import deepcopy

from adapters.coupang import CoupangAdapter
from adapters.smartstore import SmartstoreAdapter

snapshot = {
    "refined_name": "스테인리스 텀블러",
    "brand_name": "우리브랜드",
    "keywords": ["보온", "대용량"],
    "origin": "해외|아시아|중국",
    "price": {"wholesale": 8000, "retail": 15900, "minimum_selling": 12000},
    "images": {"list": ["https://img/main.jpg", "https://img/sub.jpg"], "detail_content": "<img src='detail.jpg'>"},
    "options": [{"name": "블랙", "price_wholesale": 8000, "position": 1}],
    "market_categories": {
        "smartstore": {"category_id": "50001", "category_path": "생활/주방 > 컵"},
        "coupang": {"category_id": "70001", "category_path": None},
    },
}
smartstore_settings = {
    "listing_defaults": {"naverShoppingRegistration": True},
    "generation_rules": {
        "pricingPolicy": {
            "version": "smartstore-pricing:v1",
            "shippingCost": {"type": "fixed", "amount": 3000},
            "marketplaceFee": {"type": "percent_of_sale_price", "rate": 5.0},
            "advertisingCost": {"type": "percent_of_sale_price", "rate": 3.0},
            "otherCost": {"type": "fixed", "amount": 500},
            "targetMargin": {"type": "percent_of_sale_price", "rate": 25.0},
            "rounding": {"unit": 100, "mode": "ceil"},
        }
    },
}
coupang_settings = {
    "generation_rules": {
        "pricingPolicy": {
            "version": "coupang-pricing:v1",
            "shippingCost": {"type": "fixed", "amount": 3000},
            "marketplaceFee": {"type": "percent_of_sale_price", "rate": 10.0},
            "advertisingCost": {"type": "percent_of_sale_price", "rate": 0.0},
            "otherCost": {"type": "fixed", "amount": 500},
            "targetMargin": {"type": "percent_of_sale_price", "rate": 25.0},
            "rounding": {"unit": 100, "mode": "ceil"},
        }
    },
}


def test_smartstore_adapter_generates_expandable_payload_and_title_recipe():
    result = SmartstoreAdapter().generate_draft(snapshot, smartstore_settings)
    origin = result.generated_payload["originProduct"]
    assert origin["name"] == "우리브랜드 스테인리스 텀블러 보온"
    assert origin["images"]["representativeImage"]["url"] == "https://img/main.jpg"
    assert origin["detailContent"] == "<img src='detail.jpg'>"
    assert origin["detailAttribute"]["originAreaInfo"]["rawOrigin"] == "해외|아시아|중국"
    assert result.recipe_versions["title"] == "smartstore-title:v1"
    assert result.sale_price == 17200
    assert result.cost_price == 8000
    assert result.expected_profit == 4324


def test_coupang_adapter_generates_items_from_option_variants():
    result = CoupangAdapter().generate_draft(snapshot, coupang_settings)
    assert result.generated_payload["displayCategoryCode"] == "70001"
    assert result.generated_payload["items"][0]["itemName"] == "블랙"
    assert result.generated_payload["items"][0]["images"][0]["imageType"] == "REPRESENTATION"
    assert result.recipe_versions["title"] == "coupang-title:v1"


def test_adapter_validation_blocks_missing_category_and_image():
    snapshot_without_category_or_image = deepcopy(snapshot)
    snapshot_without_category_or_image["market_categories"]["smartstore"]["category_id"] = None
    snapshot_without_category_or_image["images"]["list"] = []
    result = SmartstoreAdapter().generate_draft(snapshot_without_category_or_image, smartstore_settings)
    assert result.validation_result["status"] == "blocked"
    assert {item["code"] for item in result.validation_result["errors"]} == {
        "SMARTSTORE_MISSING_CATEGORY",
        "SMARTSTORE_MISSING_PRIMARY_IMAGE",
    }


def test_coupang_adapter_blocks_missing_market_specific_pricing_policy():
    settings_without_pricing_policy = {"generation_rules": {}}
    result = CoupangAdapter().generate_draft(snapshot, settings_without_pricing_policy)
    assert "COUPANG_MISSING_PRICING_POLICY" in {
        item["code"] for item in result.validation_result["errors"]
    }
```

- [ ] **Step 2: Run test to confirm failure**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_adapters.py -v
```

Expected: FAIL because adapters are absent.

- [ ] **Step 3: Define adapter result and common contract**

Extend `services/marketplace/schemas.py`:

```python
class DraftResult(BaseModel):
    display_title: str
    category_id: str | None
    sale_price: int | None
    cost_price: int | None
    expected_profit: int | None
    expected_margin_rate: float | None
    primary_image_url: str | None
    generated_payload: dict[str, Any]
    validation_result: dict[str, Any]
    adapter_version: str
    recipe_versions: dict[str, str]
```

Create `services/marketplace/adapters/base.py`:

```python
from abc import ABC, abstractmethod

from schemas import DraftResult


class MarketplaceAdapter(ABC):
    market_code: str

    @abstractmethod
    def generate_draft(self, snapshot: dict, account_settings: dict) -> DraftResult:
        raise NotImplementedError


def validation_result(errors: list[dict], warnings: list[dict] | None = None) -> dict:
    return {
        "status": "blocked" if errors else ("warning" if warnings else "valid"),
        "errors": errors,
        "warnings": warnings or [],
    }
```

- [ ] **Step 4: Implement deterministic Smart Store adapter v1**

Implement `SmartstoreAdapter` with:

```python
market_code = "smartstore"
adapter_version = "smartstore-adapter:v1"
title_recipe_version = "smartstore-title:v1"
```

Its v1 title uses non-empty `brand_name`, `refined_name`, and at most one existing approved keyword in that order, de-duplicated. It creates:

```python
{
    "originProduct": {
        "name": title,
        "leafCategoryId": category_id,
        "salePrice": sale_price,
        "images": {
            "representativeImage": {"url": primary_image},
            "optionalImages": [{"url": url} for url in extra_images],
        },
        "detailContent": detail_content,
        "detailAttribute": {
            "originAreaInfo": {"rawOrigin": snapshot.get("origin")},
            "optionInfo": {"optionCombinations": option_combinations},
        },
    },
    "smartstoreChannelProduct": settings.get("listing_defaults", {}),
}
```

Before building the payload, call `calculate_proposed_price(snapshot["price"]["wholesale"], settings["generation_rules"]["pricingPolicy"])`. Persist the result under `generated_payload["pricing"]`, and use `proposedSalePrice` for `originProduct.salePrice` and `DraftResult.sale_price`. On `PricingPolicyError`, leave sale price empty and add a blocking `SMARTSTORE_MISSING_PRICING_POLICY` or `SMARTSTORE_INVALID_PRICING_POLICY` error.

For this phase, `rawOrigin` deliberately preserves the input for review; conversion to an official origin code is an adapter extension once the origin-code mapping contract is implemented.

Validation blocks missing category, title, primary image, sale price, origin, or detail content using `SMARTSTORE_MISSING_*` error codes.

- [ ] **Step 5: Implement deterministic Coupang adapter v1**

Implement `CoupangAdapter` with:

```python
market_code = "coupang"
adapter_version = "coupang-adapter:v1"
title_recipe_version = "coupang-title:v1"
```

It creates a channel-native draft:

```python
{
    "displayCategoryCode": category_id,
    "displayProductName": title,
    "sellerProductName": title,
    "items": [
        {
            "itemName": option["name"],
            "salePrice": sale_price,
            "images": image_payload,
            "attributes": [{"attributeTypeName": "옵션", "attributeValueName": option["name"]}],
            "contents": [{"contentsType": "HTML", "contentDetails": [{"content": detail_content, "detailType": "TEXT"}]}],
        }
        for option in normalized_options
    ],
}
```

If no options exist, generate one `items[]` entry named from the title. Validation blocks missing category, title, image, sale price, or detail content using `COUPANG_MISSING_*` codes.

Use only the Coupang account's `generation_rules.pricingPolicy` with `calculate_proposed_price()`, save the calculation under `generated_payload["pricing"]`, and assign its proposed sale price to `items[].salePrice`. A Smart Store policy must never be reused for a Coupang draft.

- [ ] **Step 6: Run adapter tests**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_adapters.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/marketplace/adapters services/marketplace/schemas.py services/marketplace/tests/test_adapters.py
git commit -m "feat(marketplace): add smartstore and coupang draft adapters"
```

### Task 7: Generate Idempotent Drafts For Connected Accounts

**Files:**
- Create: `services/marketplace/clients/__init__.py`
- Create: `services/marketplace/clients/processor_client.py`
- Modify: `services/marketplace/services/__init__.py`
- Create: `services/marketplace/services/draft_generation.py`
- Create: `services/marketplace/tests/test_draft_generation.py`

- [ ] **Step 1: Write failing service tests**

Test the orchestration function independently of Celery and external HTTP:

```python
@pytest.mark.asyncio
async def test_generation_creates_drafts_only_for_connected_accounts():
    await generate_drafts_for_job(job, db, FakeProcessorClient(snapshot), registry)
    assert saved_market_codes == {"smartstore", "coupang"}
    assert "unconnected_market" not in saved_market_codes


@pytest.mark.asyncio
async def test_same_product_and_account_regenerates_unsubmitted_draft_in_place():
    first_id = await generate_with_version("v1")
    second_id = await generate_with_version("v2")
    assert first_id == second_id
    assert stored_draft.source_product_version == "v2"
    assert stored_draft.status == "needs_review"


@pytest.mark.asyncio
async def test_generation_preserves_storage_for_future_overrides():
    draft.override_patch = {"originProduct": {"name": "수동 상품명"}}
    await regenerate(draft)
    assert draft.override_patch == {"originProduct": {"name": "수동 상품명"}}
    assert draft.status == "needs_review"


@pytest.mark.asyncio
async def test_generation_persists_price_and_margin_summary_columns():
    await generate_drafts_for_job(job, db, FakeProcessorClient(snapshot), registry)
    assert stored_draft.cost_price == 8000
    assert stored_draft.sale_price == 17200
    assert stored_draft.expected_profit == 4324
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_draft_generation.py -v
```

Expected: FAIL because the client/service modules do not exist.

- [ ] **Step 3: Implement processor client**

Create `services/marketplace/clients/processor_client.py`:

```python
import httpx

from config import settings


class ProcessorClient:
    async def get_marketplace_snapshot(self, product_id: str, user_id: str) -> dict:
        async with httpx.AsyncClient(base_url=settings.PROCESSOR_BASE_URL, timeout=10.0) as client:
            response = await client.get(
                f"/internal/products/{product_id}/marketplace-snapshot",
                params={"user_id": user_id},
                headers={"X-Internal-Service-Token": settings.INTERNAL_SERVICE_TOKEN},
            )
            response.raise_for_status()
            return response.json()
```

- [ ] **Step 4: Implement adapter registry and draft orchestration**

In `services/marketplace/adapters/__init__.py`, expose:

```python
ADAPTERS = {
    "smartstore": SmartstoreAdapter(),
    "coupang": CoupangAdapter(),
}
```

Create `services/marketplace/services/draft_generation.py` with:

```python
async def generate_drafts_for_job(job, db, processor_client, adapters=ADAPTERS):
    job.status = "processing"
    snapshot = await processor_client.get_marketplace_snapshot(str(job.source_product_id), str(job.user_id))
    job.generated_source_version = snapshot["version"]

    accounts = await connected_accounts(db, job.user_id)
    for account in accounts:
        adapter = adapters.get(account.market_code)
        if adapter is None:
            continue
        settings_payload = serialize_settings(account.settings)
        result = adapter.generate_draft(snapshot, settings_payload)
        draft = await active_draft_for_account(db, job.source_product_id, account.id)
        if draft is None:
            draft = MarketListingDraft(source_product_id=job.source_product_id, market_account_id=account.id, market_code=account.market_code)
        apply_result_to_draft(draft, snapshot, result)
        draft.status = "needs_review"
        db.add(draft)

    job.status = "completed"
    job.completed_at = datetime.utcnow()
    await db.commit()
```

`apply_result_to_draft()` sets snapshot/version, title/category/image and pricing summary columns, `generated_payload`, validation, adapter version, and recipe versions; it must not delete `override_patch`.

Wrap this work in exception handling that sets:

```python
job.status = "failed"
job.error = {"message": str(error), "type": error.__class__.__name__}
```

before committing and re-raising for Celery visibility.

- [ ] **Step 5: Run generation and adapter tests**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_draft_generation.py tests/test_adapters.py -v
```

Expected: PASS, with the second generation updating the prior unsubmitted draft rather than inserting another and every generated draft awaiting seller review.

- [ ] **Step 6: Commit**

```bash
git add services/marketplace/clients services/marketplace/services services/marketplace/adapters services/marketplace/tests/test_draft_generation.py
git commit -m "feat(marketplace): generate versioned listing drafts"
```

### Task 8: Queue Internal Draft Generation And Expose Draft Query APIs

**Files:**
- Create: `services/marketplace/celery_app.py`
- Create: `services/marketplace/tasks.py`
- Modify: `services/marketplace/schemas.py`
- Modify: `services/marketplace/main.py`
- Create: `services/marketplace/tests/test_generation_api.py`
- Create: `services/marketplace/tests/test_drafts_api.py`

- [ ] **Step 1: Write failing internal generation and query tests**

Cover internal auth, queued job creation, and user-owned draft reads:

```python
@pytest.mark.asyncio
async def test_internal_generation_endpoint_requires_service_token():
    response = await client.post("/internal/draft-generation-jobs", json=generation_payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_internal_generation_endpoint_creates_job_and_queues_task():
    response = await client.post(
        "/internal/draft-generation-jobs",
        json=generation_payload,
        headers={"X-Internal-Service-Token": "internal-test-token"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    mock_delay.assert_called_once_with(response.json()["id"])


@pytest.mark.asyncio
async def test_list_drafts_returns_only_authenticated_users_drafts():
    response = await client.get("/drafts", params={"market_code": "smartstore", "status": "needs_review"})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(owned_draft.id)]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests/test_generation_api.py tests/test_drafts_api.py -v
```

Expected: FAIL because queue and draft routes are absent.

- [ ] **Step 3: Implement Celery wrapper**

Create `services/marketplace/celery_app.py`:

```python
from celery import Celery
from config import settings

celery_app = Celery("marketplace", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="Asia/Seoul", enable_utc=True)
```

Create `services/marketplace/tasks.py`:

```python
import asyncio
import uuid

from sqlalchemy import select

from celery_app import celery_app
from clients.processor_client import ProcessorClient
from database import SessionLocal
from models import MarketDraftGenerationJob
from services.draft_generation import generate_drafts_for_job


@celery_app.task(name="generate_market_listing_drafts")
def generate_market_listing_drafts(job_id: str):
    return asyncio.run(_run_generation_job(job_id))


async def _run_generation_job(job_id: str):
    async with SessionLocal() as db:
        result = await db.execute(select(MarketDraftGenerationJob).where(MarketDraftGenerationJob.id == uuid.UUID(job_id)))
        job = result.scalar_one()
        await generate_drafts_for_job(job, db, ProcessorClient())
        return {"job_id": job_id, "status": job.status}
```

- [ ] **Step 4: Implement internal generation and user draft API schemas/routes**

Add schemas:

```python
class DraftGenerationRequest(BaseModel):
    source_product_id: UUID
    source_product_updated_at: datetime
    source_user_id: UUID
    reason: str = "processing_completed"


class DraftGenerationJobResponse(BaseModel):
    id: UUID
    status: str
    model_config = ConfigDict(from_attributes=True)


class MarketListingDraftResponse(BaseModel):
    id: UUID
    market_code: str
    status: str
    display_title: str | None
    category_id: str | None
    sale_price: int | None
    cost_price: int | None
    expected_profit: int | None
    expected_margin_rate: float | None
    primary_image_url: str | None
    validation_result: dict[str, Any]
    generated_payload: dict[str, Any]
    recipe_versions: dict[str, str]
    model_config = ConfigDict(from_attributes=True)
```

Implement routes in `main.py`:

```python
@app.post("/internal/draft-generation-jobs", response_model=DraftGenerationJobResponse, status_code=202, dependencies=[Depends(require_internal_service_token)])
async def enqueue_generation(payload: DraftGenerationRequest, db: AsyncSession = Depends(get_db)):
    job = MarketDraftGenerationJob(
        user_id=payload.source_user_id,
        source_product_id=payload.source_product_id,
        requested_source_version=payload.source_product_updated_at.isoformat(),
        reason=payload.reason,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    generate_market_listing_drafts.delay(str(job.id))
    return job
```

Add authenticated `GET /drafts` and `GET /drafts/{draft_id}` queries by joining through `MarketAccount.user_id`; optional `market_code` and `status` filters are applied before ordering by newest update.

- [ ] **Step 5: Run marketplace suite**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/marketplace
git commit -m "feat(marketplace): queue generation and expose drafts"
```

### Task 9: Notify Marketplace After Successful Product Processing

**Files:**
- Create: `services/processor/clients/marketplace_client.py`
- Modify: `services/processor/graphs/product_processor.py`
- Modify: `services/processor/tasks.py`
- Modify: `services/processor/tests/test_product_processor_graph.py`
- Modify: `services/processor/tests/test_tasks.py`

- [ ] **Step 1: Write failing notification tests**

Extend graph tests with a notifier mock:

```python
@pytest.mark.asyncio
async def test_successful_processing_requests_marketplace_draft_generation():
    marketplace_client = AsyncMock()
    context = make_context(marketplace_client=marketplace_client)
    await process_product_with_graph(context)
    marketplace_client.request_draft_generation.assert_awaited_once_with(context.product)


@pytest.mark.asyncio
async def test_generation_notification_failure_does_not_fail_processed_product():
    marketplace_client = AsyncMock()
    marketplace_client.request_draft_generation.side_effect = RuntimeError("marketplace unavailable")
    context = make_context(marketplace_client=marketplace_client)
    state = await process_product_with_graph(context)
    assert context.product.status == "completed"
    assert "marketplace_generation" in context.product.warnings
    assert "error" not in state
```

Update the task delegation test to assert a `MarketplaceClient` instance is passed into `ProductProcessingContext`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd services/processor
PYTHONPATH=. pytest tests/test_product_processor_graph.py tests/test_tasks.py -v
```

Expected: FAIL because no marketplace notifier dependency exists.

- [ ] **Step 3: Implement marketplace notification client**

Create `services/processor/clients/marketplace_client.py`:

```python
import httpx

from config import settings


class MarketplaceClient:
    async def request_draft_generation(self, product) -> None:
        payload = {
            "source_product_id": str(product.id),
            "source_product_updated_at": product.updated_at.isoformat(),
            "source_user_id": str(product.user_id),
            "reason": "processing_completed",
        }
        async with httpx.AsyncClient(base_url=settings.MARKETPLACE_BASE_URL, timeout=5.0) as client:
            response = await client.post(
                "/internal/draft-generation-jobs",
                json=payload,
                headers={"X-Internal-Service-Token": settings.INTERNAL_SERVICE_TOKEN},
            )
            response.raise_for_status()
```

- [ ] **Step 4: Wire notifier at the success boundary**

Add `marketplace_client: Any | None = None` to `ProductProcessingContext`. In `persist_success`, commit the completed product and mappings first, then invoke:

```python
    await runtime.context.db.refresh(product)
    if runtime.context.marketplace_client:
        try:
            await runtime.context.marketplace_client.request_draft_generation(product)
        except Exception as error:
            product.warnings = merge_product_warnings(
                product.warnings,
                [{"stage": "marketplace_generation", "message": str(error)}],
            )
            await runtime.context.db.commit()
```

Do not re-raise notification errors. The processor success count and product completion status remain intact.

In `services/processor/tasks.py`, instantiate `MarketplaceClient()` once per DB pipeline and pass it into every `ProductProcessingContext`.

- [ ] **Step 5: Verify processor integration**

Run:

```bash
cd services/processor
PYTHONPATH=. pytest tests/test_product_processor_graph.py tests/test_tasks.py tests/test_marketplace_snapshot.py -v
```

Expected: PASS, including non-fatal notification failure behavior.

- [ ] **Step 6: Commit**

```bash
git add services/processor
git commit -m "feat(processor): request marketplace drafts after processing"
```

### Task 10: Run Cross-Service Verification And Document Phase-One Boundary

**Files:**
- Modify: `docs/superpowers/current_state.md`
- Modify: `TODO.md`
- Test: `services/marketplace/tests/*`
- Test: `services/processor/tests/test_marketplace_snapshot.py`
- Test: `services/processor/tests/test_product_processor_graph.py`
- Test: `services/processor/tests/test_tasks.py`

- [ ] **Step 1: Update project status documents**

Add to `docs/superpowers/current_state.md` after the processor backend summary:

```markdown
### Marketplace Listing Service (Port 8003)

- Dedicated marketplace API/worker boundary for listing preparation.
- Market-account and marketplace-specific settings storage.
- Smart Store and Coupang adapter-based draft generation from processor snapshots.
- Marketplace-specific pricing policy calculation with cost, proposed sale price, expected profit, and achieved margin summaries.
- Versioned draft payloads and structured validation for future UI review.
- External submission and registration UI are intentionally deferred.
```

Add an active marketplace section to `TODO.md`:

```markdown
## Phase 7: Marketplace Listing
- [x] Marketplace draft foundation: service boundary, snapshot contract, account settings, Smart Store/Coupang initial draft adapters.
- [ ] Unified registration inbox and per-market settings/editing UI.
- [ ] External Smart Store/Coupang submission jobs, retry behavior, and registration history.
- [ ] Recipe extensions for SEO titles and category-specific attributes.
- [ ] Margin calculator UI, bulk price-policy application, and per-product price-override preview.
```

- [ ] **Step 2: Run backend regression tests**

Run:

```bash
cd services/marketplace
PYTHONPATH=. pytest tests -q
cd ../processor
PYTHONPATH=. pytest tests/test_marketplace_snapshot.py tests/test_product_processor_graph.py tests/test_tasks.py tests/test_wholesale_upload.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 3: Verify deployment configuration**

Run:

```bash
cd ../..
docker compose config --quiet
docker compose build marketplace marketplace-worker processor worker gateway
```

Expected: Compose config validates and all changed service images build successfully.

- [ ] **Step 4: Perform an API smoke check**

Run:

```bash
docker compose up -d db redis marketplace processor gateway
curl -f http://localhost/api/marketplace/health
curl -f http://localhost/api/processor/health
```

Expected responses contain healthy service statuses. Shut down only containers started for this smoke check using:

```bash
docker compose stop gateway marketplace processor redis db
```

- [ ] **Step 5: Commit**

```bash
git add TODO.md docs/superpowers/current_state.md
git commit -m "docs: record marketplace draft foundation status"
```

## Completion Criteria

Phase one is complete when:

- `marketplace` and `marketplace-worker` run as distinct containers and gateway health routing works.
- A seller can create a connected Smart Store or Coupang account and store marketplace-specific setting JSON without receiving credentials back from the API.
- `processor` exposes a protected product snapshot containing product-specific registration ingredients.
- Completing product processing attempts a non-fatal draft-generation notification.
- The marketplace worker retrieves a processor snapshot and creates or regenerates one draft per connected supported account.
- Smart Store and Coupang generated payloads remain channel-native JSON documents with adapter and recipe versions.
- Each account's pricing policy produces reviewable cost, proposed sale price, expected profit, and achieved-margin values without sharing another marketplace's settings.
- Draft validation surfaces blocking missing fields while leaving future fields extensible through JSON payloads and new adapter recipes.
- No frontend or external marketplace product-registration API is accidentally included in this phase.

## Subsequent Plans

After this foundation is merged and verified, write separate plans for:

1. `marketplace-review-ui`: unified registration inbox, market-specific setting tabs, margin calculator and bulk recalculation UI, draft editing/override API, validation acknowledgement, and ready transitions.
2. `marketplace-submission`: external Smart Store/Coupang clients, submission jobs/attempts, individual and bulk execution, failure retry, and ambiguous remote-result reconciliation.
