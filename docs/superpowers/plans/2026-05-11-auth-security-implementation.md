# Auth Service Security & API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement password hashing, JWT authentication, and API key encryption for the Auth Service.

**Architecture:** Logic is centralized in `security.py`. FastAPI endpoints in `main.py` use these utilities and dependency injection for authentication. API keys use granular Fernet encryption.

**Tech Stack:** FastAPI, SQLAlchemy (Async), passlib (bcrypt), python-jose, cryptography (Fernet).

---

### Task 1: Password Hashing Utilities

**Files:**
- Create: `services/auth/security.py`
- Test: `services/auth/tests/test_security.py`

- [ ] **Step 1: Write failing test for password hashing**

```python
from security import get_password_hash, verify_password

def test_password_hashing():
    password = "secretpassword"
    hashed = get_password_hash(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_security.py`
Expected: FAIL (Module not found)

- [ ] **Step 3: Implement password hashing logic**

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_security.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/security.py services/auth/tests/test_security.py
git commit -m "feat(auth): add password hashing utilities"
```

### Task 2: JWT Token Management

**Files:**
- Modify: `services/auth/security.py`
- Modify: `services/auth/tests/test_security.py`

- [ ] **Step 1: Write failing test for JWT**

```python
from security import create_access_token, decode_access_token
from datetime import timedelta

def test_jwt_token_creation_and_decoding():
    data = {"sub": "testuser"}
    token = create_access_token(data, expires_delta=timedelta(minutes=15))
    assert token is not None
    
    decoded_data = decode_access_token(token)
    assert decoded_data["sub"] == "testuser"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_security.py`
Expected: FAIL (create_access_token not found)

- [ ] **Step 3: Implement JWT logic**

```python
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_security.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/security.py services/auth/tests/test_security.py
git commit -m "feat(auth): add JWT token management"
```

### Task 3: API Key Encryption Utilities

**Files:**
- Modify: `services/auth/security.py`
- Modify: `services/auth/tests/test_security.py`

- [ ] **Step 1: Write failing test for Encryption**

```python
from security import encrypt_value, decrypt_value

def test_value_encryption_decryption():
    original_value = "my-api-key-123"
    encrypted = encrypt_value(original_value)
    assert encrypted != original_value
    
    decrypted = decrypt_value(encrypted)
    assert decrypted == original_value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_security.py`
Expected: FAIL (encrypt_value not found)

- [ ] **Step 3: Implement Fernet logic**

```python
from cryptography.fernet import Fernet
from config import settings

fernet = Fernet(settings.ENCRYPTION_KEY.encode())

def encrypt_value(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(encrypted_value: str) -> str:
    return fernet.decrypt(encrypted_value.encode()).decode()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_security.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/security.py services/auth/tests/test_security.py
git commit -m "feat(auth): add API key encryption utilities"
```

### Task 4: Update Schemas

**Files:**
- Modify: `services/auth/schemas.py`

- [ ] **Step 1: Add Token and TokenData schemas**

```python
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add services/auth/schemas.py
git commit -m "feat(auth): add Token schemas"
```

### Task 5: User Registration Endpoint

**Files:**
- Modify: `services/auth/main.py`
- Create: `services/auth/tests/test_main.py`

- [ ] **Step 1: Write failing test for registration**

```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_register_user():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/register",
            json={"username": "testuser", "password": "testpassword"}
        )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"
    assert "id" in response.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_main.py`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement /register endpoint**

```python
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import User
from schemas import UserCreate, UserResponse
from security import get_password_hash

@app.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user_in.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password)
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_main.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/main.py services/auth/tests/test_main.py
git commit -m "feat(auth): implement registration endpoint"
```

### Task 6: Login and Token Generation

**Files:**
- Modify: `services/auth/main.py`
- Modify: `services/auth/tests/test_main.py`

- [ ] **Step 1: Write failing test for login**

```python
@pytest.mark.asyncio
async def test_login():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Assumes testuser was created in previous test or setup
        response = await ac.post(
            "/token",
            data={"username": "testuser", "password": "testpassword"}
        )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_main.py`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement /token endpoint**

```python
from fastapi.security import OAuth2PasswordRequestForm
from schemas import Token
from security import verify_password, create_access_token

@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_main.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/main.py services/auth/tests/test_main.py
git commit -m "feat(auth): implement login endpoint"
```

### Task 7: Protected Current User Route

**Files:**
- Modify: `services/auth/main.py`
- Modify: `services/auth/tests/test_main.py`

- [ ] **Step 1: Write failing test for /me**

```python
@pytest.mark.asyncio
async def test_get_me():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Login first to get token
        login_res = await ac.post("/token", data={"username": "testuser", "password": "testpassword"})
        token = login_res.json()["access_token"]
        
        response = await ac.get("/me", headers={"Authorization": f"Bearer {token}"})
        
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/auth/tests/test_main.py`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement get_current_user dependency and /me endpoint**

```python
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from schemas import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db)):
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

@app.get("/me", response_model=UserResponse)
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/auth/tests/test_main.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/auth/main.py services/auth/tests/test_main.py
git commit -m "feat(auth): implement /me protected endpoint"
```
