# Design Specification: Auth Service Base Structure & Modeling

## 1. Goal
Implement the foundational structure for the Auth Service, including asynchronous database connectivity, the User model, Pydantic schemas, and a basic FastAPI application.

## 2. Components

### 2.1 Database Layer (`database.py`)
- **Technology**: SQLAlchemy 2.0 (Async), `asyncpg`.
- **Engine**: Asynchronous engine using `create_async_engine`.
- **Session**: `async_sessionmaker` for creating database sessions.
- **Base**: `DeclarativeBase` for model definitions.
- **Dependency**: `get_db` function for FastAPI dependency injection.

### 2.2 Models (`models.py`)
- **User Model**:
    - `id`: UUID (Primary Key)
    - `username`: String (Unique, Indexed)
    - `hashed_password`: String
    - `is_admin`: Boolean (Default: False)
    - `encrypted_api_keys`: JSON or String (to store Naver/Coupang keys securely later)

### 2.3 Schemas (`schemas.py`)
- **UserCreate**: For user registration (username, password).
- **UserResponse**: For returning user data (id, username, is_admin).
- **Token**: For future JWT implementation.

### 2.4 API (`main.py`)
- FastAPI app instance.
- Health check endpoint (`GET /health`).

### 2.5 Tests (`tests/test_models.py`)
- TDD-based tests for model creation.
- Uses `pytest` and `pytest-asyncio`.
- Uses an asynchronous database session for testing.

## 3. Data Flow
1. API request comes into `main.py`.
2. Controller (future) interacts with models via SQLAlchemy sessions from `database.py`.
3. Pydantic schemas in `schemas.py` validate input and format output.

## 4. Security
- API keys will be stored in `encrypted_api_keys`.
- Passwords will be hashed using `passlib` (bcrypt).
