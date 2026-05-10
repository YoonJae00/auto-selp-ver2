# Auth Service Base Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the base structure and database modeling for the Auth Service.

**Architecture:** FastAPI with asynchronous SQLAlchemy and Pydantic schemas. The service uses a shared PostgreSQL database.

**Tech Stack:** FastAPI, SQLAlchemy (Async), PostgreSQL (asyncpg), Pydantic, Pytest.

---

### Task 1: Project Setup and Health Check

**Files:**
- Modify: `services/auth/main.py`
- Create: `services/auth/tests/test_main.py`

- [ ] **Step 1: Write failing test for health check**

```python
from fastapi.testclient import TestClient
from services.auth.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_main.py`
Expected: FAIL (404 Not Found or app not configured)

- [ ] **Step 3: Implement minimal health check**

```python
from fastapi import FastAPI

app = FastAPI(title="Auto-Selp Auth Service")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_main.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/main.py services/auth/tests/test_main.py
git commit -m "feat: add health check endpoint"
```

### Task 2: Database Configuration

**Files:**
- Create: `services/auth/database.py`
- Create: `services/auth/config.py`

- [ ] **Step 1: Implement configuration management**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
```

- [ ] **Step 2: Implement database connectivity**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from services.auth.config import settings

engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 3: Commit**

```bash
git add services/auth/database.py services/auth/config.py
git commit -m "feat: set up database and config"
```

### Task 3: User Model and TDD

**Files:**
- Create: `services/auth/models.py`
- Create: `services/auth/tests/test_models.py`

- [ ] **Step 1: Write failing test for User model**

```python
import pytest
from sqlalchemy import select
from services.auth.models import User
from services.auth.database import Base, engine, SessionLocal
import uuid

@pytest.mark.asyncio
async def test_create_user():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with SessionLocal() as session:
        user = User(
            username="testuser",
            hashed_password="hashedpassword",
            is_admin=False
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        assert user.username == "testuser"
        assert isinstance(user.id, uuid.UUID)
        
        result = await session.execute(select(User).where(User.username == "testuser"))
        db_user = result.scalar_one()
        assert db_user.username == "testuser"

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_models.py`
Expected: FAIL (ImportError: cannot import name 'User')

- [ ] **Step 3: Implement User model**

```python
from sqlalchemy import String, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from services.auth.database import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    encrypted_api_keys: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_models.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/models.py services/auth/tests/test_models.py
git commit -m "feat: implement User model with TDD"
```

### Task 4: Pydantic Schemas

**Files:**
- Create: `services/auth/schemas.py`

- [ ] **Step 1: Implement schemas**

```python
from pydantic import BaseModel, ConfigDict
import uuid

class UserBase(BaseModel):
    username: str
    is_admin: bool = False

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: uuid.UUID
    
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add services/auth/schemas.py
git commit -m "feat: add Pydantic schemas for user and token"
```
