# Design Specification: Auth Service Security & API

## 1. Goal
Implement JWT-based authentication, password hashing, and AES-256 encryption for API keys in the Auth Service.

## 2. Components

### 2.1 Security Utilities (`security.py`)
- **Technology**: `passlib` (bcrypt), `python-jose` (JWT), `cryptography` (Fernet/AES-256).
- **Functions**:
    - `get_password_hash(password: str) -> str`: Hashes plain password.
    - `verify_password(plain_password: str, hashed_password: str) -> bool`: Verifies hash.
    - `create_access_token(data: dict, expires_delta: timedelta | None = None) -> str`: Creates JWT.
    - `get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db)) -> User`: Dependency for protected routes.
    - `encrypt_value(value: str) -> str`: Encrypts value using `ENCRYPTION_KEY`.
    - `decrypt_value(encrypted_value: str) -> str`: Decrypts value.

### 2.2 API Endpoints (`main.py`)
- **`POST /register`**:
    - Input: `UserCreate` schema.
    - Action: Check if user exists, hash password, create User in DB.
    - Output: `UserResponse`.
- **`POST /login`**:
    - Input: `OAuth2PasswordRequestForm`.
    - Action: Verify user, return JWT.
    - Output: `Token` schema.
- **`GET /me`**:
    - Protection: Requires valid JWT.
    - Output: `UserResponse`.

### 2.3 Schemas (`schemas.py`)
- Ensure `Token` and `TokenData` are defined.
- `UserCreate` and `UserResponse` are already present.

## 3. Data Storage
- **Passwords**: Stored as bcrypt hashes in `hashed_password` column.
- **API Keys**: Stored in `encrypted_api_keys` (JSON) as `{"key_name": "encrypted_base64_string"}`.

## 4. Testing Strategy (TDD)
- **Security Tests (`tests/test_security.py`)**:
    - Test password hashing/verification.
    - Test JWT creation/decoding.
    - Test value encryption/decryption.
- **API Tests (`tests/test_main.py`)**:
    - Test successful registration.
    - Test registration with existing username (error).
    - Test login and token generation.
    - Test protected `/me` endpoint with and without token.
