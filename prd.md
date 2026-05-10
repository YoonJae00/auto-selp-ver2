# Product Requirements Document (PRD): Auto-Selp

## 1. 프로젝트 개요 (Overview)
Auto-Selp는 이커머스 셀러들이 상품을 등록하기 전, 상품 데이터를 자동으로 가공하고 최적화하는 솔루션입니다. 엑셀 파일 형식의 원본 데이터를 입력받아 LLM(대규모 언어 모델)과 주요 플랫폼(네이버, 쿠팡)의 API를 활용하여 상품명 정제, SEO 키워드 추출, 카테고리 매칭을 수행합니다.

### 핵심 목표
- **상품명 최적화**: 검색 노출에 불리한 브랜드명이나 특수문자를 제거하고 가독성을 높임.
- **데이터 기반 키워드**: 실제 검색량과 경쟁도를 분석하여 최적의 롱테일 키워드 제공.
- **자동 카테고리 매칭**: 플랫폼별 최적의 카테고리 코드를 자동으로 할당하여 등록 오차 감소.
- **상표권 보호**: 블랙리스트와 AI 검증을 통해 상표권 위반 위험 키워드를 사전에 차단.

---

## 2. 핵심 기능 및 가공 로직 (Core Logic)

시스템의 핵심은 **3단계 파이프라인(상품명 -> 키워드 -> 카테고리)**입니다.

### 2.1 상품명 정제 (Product Name Refinement)
- **목적**: 원본 상품명에서 불필요한 요소를 제거하고 검색에 최적화된 이름으로 변환.
- **로직**:
    1. LLM을 사용하여 브랜드명, 특수문자, 중복 단어 제거.
    2. 수량 및 단위 표준화 (예: `10p` -> `10개`, 의미 없는 `1p` 제거).
    3. 결과값에서 JSON 형식이나 따옴표 등 불필요한 래핑 제거.
- **입력**: 원본 상품명, 사용자 정의 프롬프트(옵션).
- **출력**: 정제된 상품명.

### 2.2 키워드 생성 워크플로우 (Keyword Curation)
3단계(Phase) 프로세스를 거쳐 상위 10개의 최적 키워드를 선정합니다.

#### Phase 1: 다각도 시드(Seed) 수집
- **네이버**: 네이버 검색광고 API의 `keywordstool`을 사용하여 연관 키워드, 월간 검색량, 경쟁도 데이터를 수집.
- **쿠팡**: 쿠팡 검색 인터페이스(Web Adapter)를 통해 연관 검색어 수집.
- **변형**: LLM을 통해 상품명의 동의어/약칭을 생성하여 추가 검색 수행 (검색 범위 확장).

#### Phase 2: 경쟁도 및 품질 필터링
- **경쟁도 필터**: 경쟁도가 "높음"인 키워드 제거 (소상공인 진입 장벽 고려).
- **길이 필터**: 너무 짧거나(1글자) 의미 없는 단어 제거.
- **롱테일 우선**: 2단어 이상의 조합형 키워드에 가점 부여.
- **불용어 제거**: "랜덤", "배송비", "무료배송" 등 SEO에 부적합한 단어 리스트(Stop Words) 대조 제거.

#### Phase 3: 상표권 검증 및 최종 선별
- **1차 검증**: 로컬 상표권 블랙리스트 파일과 대조하여 즉시 제거.
- **2차 검증**: LLM을 통해 문맥상 브랜드명이 포함되어 있는지 최종 판별.
- **최종 선별**: 검색량과 품질 점수가 높은 순으로 최대 10개 추출.

### 2.3 카테고리 매칭 (Category Mapping)
#### 네이버 카테고리
1. 네이버 쇼핑 검색 API로 상품명을 검색하여 현재 매칭된 카테고리 경로(`대>중>소>세`)를 획득.
2. 획득한 경로를 로컬 매핑 데이터(`naver_category_mapping.xls`)와 대조하여 고유 카테고리 번호 추출.
3. 완전 일치 실패 시, 세분류 명칭 기반의 부분 일치 로직 적용.

#### 쿠팡 카테고리
1. 쿠팡의 카테고리 예측 API(Categorization Predict)를 직접 호출.
2. 상품명, 브랜드 정보를 전달하여 쿠팡 시스템이 권장하는 카테고리 ID를 즉시 획득.

---

## 3. 외부 API 연동 규격 (External API Specifications)

### 3.1 네이버 검색 API (쇼핑)
- **용도**: 상품명 기반 카테고리 경로 조회.
- **Endpoint**: `GET https://openapi.naver.com/v1/search/shop.json`
- **인증**: `X-Naver-Client-Id`, `X-Naver-Client-Secret` 헤더 사용.
- **주요 파라미터**: `query` (상품명), `display=1`.
- **응답 활용**: `items[0]`의 `category1` ~ `category4` 계층 구조.

### 3.2 네이버 검색광고 API
- **용도**: 키워드별 검색량 및 경쟁도 데이터 획득.
- **Endpoint**: `GET https://api.searchad.naver.com/keywordstool`
- **인증 (HMAC)**:
    - `X-Timestamp`: 현재 밀리초 타임스탬프.
    - `X-Signature`: `timestamp + "." + method + "." + uri`를 Secret Key로 HMAC-SHA256 서명 후 Base64 인코딩.
    - `X-API-KEY`, `X-Customer`: 관리자 페이지 발급 키.
- **응답 활용**: `relKeyword`, `monthlyPcQcCnt`, `monthlyMobileQcCnt`, `compIdx` (높음/중간/낮음).

### 3.3 쿠팡 Open API (카테고리 예측)
- **용도**: 쿠팡 전용 카테고리 ID 자동 매칭.
- **Endpoint**: `POST https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v1/categorization/predict`
- **인증 (CEA)**: `Authorization` 헤더에 HmacSHA256 알고리즘 기반 서명 포함.
- **Request Body**:
    ```json
    {
      "productName": "정제된 상품명",
      "brand": "브랜드명(없을 시 빈값)",
      "attributes": {}
    }
    ```
- **응답 활용**: `data.predictedCategoryId`.

### 3.4 LLM API (Gemini/OpenAI)
- **용도**: 상품명 정제, 키워드 변형 생성, 상표권 최종 검증.
- **사용 모델**: Gemini 2.0 Flash (기본), OpenAI gpt-5-nano (선택).
- **특이사항**: 인코딩 오류 방지를 위해 UTF-8 처리 필수 및 API 할당량 초과 시 지수 백오프(Exponential Backoff) 재시도 로직 필요.

---

## 4. 데이터 에셋 (Data Assets)
시스템 구현 시 다음 정적 데이터 파일이 필요합니다.

1. **naver_category_mapping.xls**: 네이버 카테고리 경로와 번호 매핑 테이블.
2. **trademark_blacklist.py**: 상표권 위반 위험이 있는 브랜드명/키워드 리스트.
3. **keyword_stop_words.py**: 키워드 생성 시 제외해야 할 일반 명사 및 부적합 단어 리스트.

---

## 5. 사용자 설정 요구사항 (User Settings)
사용자는 다음 정보를 설정하고 시스템에 제공해야 합니다.
- **플랫폼 API 키**: 네이버 클라이언트 ID/Secret, 광고 API 키/Secret/고객 ID, 쿠팡 Access/Secret Key.
- **LLM API 키**: Gemini 또는 OpenAI API Key.
- **엑셀 컬럼 매핑**: 입력 파일의 어느 열에 상품명이 있고, 어느 열에 가공 결과를 저장할지 지정하는 기능.
- **가공 옵션**: 상품명 정제 여부, 키워드 생성 여부, 플랫폼별 카테고리 매칭 여부 선택 기능.
