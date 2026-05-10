# Auto-Selp Phase 1: 기반 인프라 및 인증 서비스 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Docker Compose를 이용한 MSA 기반 인프라(DB, Redis, Gateway)를 구축하고, 사용자 인증 및 API 키 관리를 담당하는 Auth Service를 구현합니다.

**Architecture:** Nginx를 API Gateway로 사용하며, Auth Service는 FastAPI로 구현하여 PostgreSQL에 사용자 정보와 암호화된 API 키를 저장합니다.

**Tech Stack:** Docker, Docker Compose, Python 3.12, FastAPI, PostgreSQL, SQLAlchemy, JWT, Cryptography(AES-256).

---

### Task 1: Docker 인프라 및 프로젝트 구조 설정

**Files:**
- Create: `docker-compose.yml`
- Create: `nginx/nginx.conf`
- Create: `nginx/Dockerfile`
- Create: `.env.example`

- [ ] **Step 1: 루트 프로젝트 구조 생성**
- [ ] **Step 2: 공통 환경 변수 파일 작성 (.env.example)**
- [ ] **Step 3: Docker Compose 구성**
- [ ] **Step 4: Nginx Gateway 설정 (nginx/nginx.conf)**
- [ ] **Step 5: Commit**

---

### Task 2: Auth Service 기본 구조 및 DB 모델링 (TDD)

**Files:**
- Create: `services/auth/main.py`
- Create: `services/auth/models.py`
- Create: `services/auth/database.py`
- Create: `services/auth/schemas.py`
- Create: `services/auth/tests/test_models.py`

- [ ] **Step 1: 모델 및 DB 연결 테스트 작성 (failing test)**
- [ ] **Step 2: SQLAlchemy 모델 및 DB 연결 구현**
- [ ] **Step 3: Pydantic 스키마 정의**
- [ ] **Step 4: FastAPI 기본 앱 및 헬스체크 구현**
- [ ] **Step 5: 모든 테스트 통과 확인 및 Commit**

---

### Task 3: 사용자 인증 및 API 키 암호화 로직 (TDD)

**Files:**
- Create: `services/auth/security.py`
- Create: `services/auth/tests/test_security.py`
- Modify: `services/auth/main.py`

- [ ] **Step 1: JWT 및 암호화 로직 테스트 작성 (failing test)**
- [ ] **Step 2: JWT, 패스워드 해싱, API 키 AES-256 암호화 구현**
- [ ] **Step 3: 회원가입 및 로그인 API 구현 (TDD 방식)**
- [ ] **Step 4: 통합 테스트 실행**
- [ ] **Step 5: Commit**
