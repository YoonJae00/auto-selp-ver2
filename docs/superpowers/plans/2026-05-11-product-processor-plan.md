# Auto-Selp Phase 2: Product Processor (상품 가공 서비스) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 엑셀 업로드, 유연한 컬럼 매핑, 3단계 가공 파이프라인(정제->키워드->카테고리), KIPRIS MCP 연동, 그리고 Celery 기반 비동기 처리를 구현합니다.

**Architecture:** 
- **Product Processor Service**: FastAPI 기반 엔진.
- **KIPRIS MCP Server**: 상표권 조회를 위한 별도 컨테이너.
- **Worker**: Celery를 통한 병렬 처리.

---

### Task 1: 데이터 에셋 및 설정 확장

- [ ] **Step 1: 로컬 에셋 생성**
    - `services/processor/assets/trademark_blacklist.py` (유명 브랜드명 리스트).
    - `services/processor/assets/keyword_stop_words.py` (불용어 리스트).
- [ ] **Step 2: Config 업데이트**
    - `services/processor/config.py`: Naver, Coupang, Gemini, KIPRIS 키 설정 추가.

### Task 2: 외부 API 클라이언트 및 인증 모듈 (TDD)

- [ ] **Step 1: 네이버 검색광고 API 클라이언트**
    - HMAC-SHA256 시그니처 생성 및 `keywordstool` 호출 로직.
- [ ] **Step 2: 네이버 쇼핑 검색 API 클라이언트**
    - `shop.json` 호출 및 카테고리 경로 추출.
- [ ] **Step 3: 쿠팡 Open API (Category Predict) 클라이언트**
    - CEA 알고리즘 기반 인증 헤더 생성 및 호출.
- [ ] **Step 4: 지수 백오프(Exponential Backoff) 유틸리티**
    - 429 에러 발생 시 재시도하는 공통 데코레이터/유틸리티 작성.

### Task 3: Stage 1 - 상품명 정제 엔진 (LLM)

- [ ] **Step 1: Gemini 클라이언트 및 3단계 재시도 로직**
    - 실패 시 프롬프트를 변경하며 최대 3회 시도하는 로직 구현.
- [ ] **Step 2: 정제 프롬프트 설계**
    - JSON 응답(`{"refined_name": "..."}`) 강제 및 수량 표준화 규칙 포함.

### Task 4: Stage 2 - 키워드 큐레이션 (3-Phase)

- [ ] **Step 1: Phase 1 - 시드 수집 및 동의어 확장**
    - 네이버/쿠팡 API 호출 + LLM 유의어 생성 추가 검색.
- [ ] **Step 2: Phase 2 - 품질 점수 필터링 알고리즘**
    - 경쟁도, 길이, 롱테일 보너스, 수량 패턴 제거 로직 구현.
- [ ] **Step 3: Phase 3 - 상표권 검증 (LLM & KIPRIS MCP 하이브리드)**
    - LLM이 '모르는 단어'나 '의심되는 브랜드'를 식별하면, 해당 단어만 KIPRIS MCP로 정밀 조회하여 사용 여부 결정.

### Task 4: Stage 3 - 카테고리 매칭 (네이버/쿠팡)

- [ ] **Step 1: 네이버 로컬 매핑 및 부분 일치 로직**
    - `naver_category_mapping.xls`를 이용한 경로 -> ID 변환.
- [ ] **Step 2: 쿠팡 Predict API 결과 연동**

### Task 5: 비동기 파이프라인 및 엑셀 핸들링

- [ ] **Step 1: 유연한 컬럼 매핑 로직**
    - 사용자가 지정한 {원본, 상품명, 키워드, 카테고리} 역할을 실제 엑셀 열에 매핑.
- [ ] **Step 2: Celery Task 정의 및 상태 추적**
    - 전체 파이프라인을 하나의 Celery 작업으로 묶고, Redis에 진행률(%) 저장.
- [ ] **Step 3: 최종 결과 엑셀 생성 및 다운로드 API**

---

## 자체 검토 (Self-Review)
1. **Spec 반영 확인**: `product.md`에 명시된 3단계 재시도, HMAC/CEA 인증, 3-Phase 키워드 큐레이션이 모두 반영됨.
2. **KIPRIS MCP**: 별도 컨테이너로 운영하며 API 키를 환경 변수로 전달하는 구조 확인.
3. **유연성**: 사용자 지정 컬럼 매핑 요구사항 반영됨.
