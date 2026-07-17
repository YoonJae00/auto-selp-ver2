---
title: "상품 DB 마이그레이션 및 확장형 스키마 연동"
date: "2026-05-20"
category: "docs/solutions/database-issues"
module: "product"
problem_type: "database_issue"
component: "database"
symptoms:
  - "Excel file-based product upload/download bottleneck"
  - "Scalability limitation with thousands of products per account"
root_cause: "incomplete_setup"
resolution_type: "migration"
severity: "high"
tags:
  - "postgresql"
  - "database-migration"
  - "extensible-schema"
  - "celery-async-task"
  - "nextjs-dashboard"
---

# 상품 DB 마이그레이션 및 확장형 스키마 연동

## Problem
기존의 상품 가공 프로세스는 단발성 엑셀 파일 업로드-가공-다운로드 흐름으로 설계되어 있었습니다. 그러나 사용자의 상품 등록량이 수천/수만 개 단위로 급증함에 따라 파일 반복 업/다운로드에 따른 불필요한 IO 비용 발생 및 데이터 연속성 부재로 가공 이력과 실시간 진척도 관리가 매우 어려워지는 확장성 병목에 직면했습니다.

## Symptoms
- 엑셀 업로드 후 가공 시 전체 파일을 처음부터 다시 로드해야 함
- 대량의 상품을 한 번에 가공할 때 실시간 진행률(%) 표기가 누락되거나 이력 추적이 불가능함
- 판매처별 고유 속성(네이버 카테고리 ID, 쿠팡 카테고리 ID 등)이 엑셀 열 레이아웃 구조에 강하게 묶여 컬럼 확장 및 커스텀 가공 결과의 보관이 매우 까다로움

## What Didn't Work
- 단순 엑셀 임시 파일 공유 볼륨 및 Redis Task 상태 관리 방식 유지: 가공 결과가 로컬 디스크의 임시 엑셀 파일 형태로 남아 다른 독립된 컨테이너나 다른 백엔드 서비스(예: 마켓 등록 모듈)에서 상품 정보를 재사용하기가 물리적으로 곤란했음.
- 단순 비정형 JSON 테이블 하나로 전체 상품을 저장하는 구조: 향후 카테고리 매핑이나 동기화 상태 조회가 빈번히 일어나 성능 저하와 쿼리 복잡성 증가가 우려됨.

## Solution
Core(공통) 상품 정보와 Platform(플랫폼별) 속성을 분리(1:N)하고 PostgreSQL JSONB를 적극 도입하여, Alter Table(DDL 변경) 없이 행 삽입만으로 유연하게 오픈마켓 채널을 추가할 수 있는 데이터 아키텍처 및 대시보드 UI를 통합 구축했습니다.

### 1. Extensible DB Schema (`models.py`)
```python
class ProductImport(Base):
    __tablename__ = "product_imports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    status = Column(String, default="pending") # pending, processing, completed, failed
    total_count = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    import_id = Column(UUID(as_uuid=True), ForeignKey("product_imports.id", ondelete="CASCADE"), nullable=False)
    original_name = Column(String, nullable=False)
    refined_name = Column(String, nullable=True)
    keywords = Column(JSON, nullable=True)  # List[str]
    status = Column(String, default="pending")
    warnings = Column(JSONB, nullable=True)  # Sparse warnings dict
    raw_metadata = Column(JSONB, nullable=True)  # Original row payload
    created_at = Column(DateTime, default=datetime.utcnow)
    
    platform_mappings = relationship("ProductPlatformMapping", back_populates="product", cascade="all, delete-orphan")

class ProductPlatformMapping(Base):
    __tablename__ = "product_platform_mappings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    platform_name = Column(String, nullable=False)  # 'naver', 'coupang', etc.
    category_id = Column(String, nullable=True)
    category_path = Column(String, nullable=True)
    sync_status = Column(String, default="pending")
    sync_error = Column(String, nullable=True)
    mapped_attributes = Column(JSONB, nullable=True)  # Extensible openmarket metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="platform_mappings")
```

### 2. Celery Async Task 개편 (`tasks.py`)
Celery Task가 가동될 때 Excel을 읽어서 한 건씩 DB에 upsert하고, 실시간 가공 진행 상태 및 warnings를 DB 레코드에 direct 반영하도록 전면 수정하였습니다.
```python
@shared_task(bind=True)
def process_db_products_task(self, import_id: str, column_mapping: dict, llm_provider: str):
    # Loop over pending products for this import_id and process them row-by-row
    # Update product status to 'processing' -> 'completed'/'failed'
    # Core-Platform Mapping insert
```

### 3. REST API 구현 (`main.py`)
- `POST /process-db`: 엑셀 데이터를 pending으로 즉시 적재하고 비동기 Celery 태스크 트리거.
- `GET /products`: debounced 검색, 가공 상태, 업로드 배치 ID 별 조회 기능 및 Pagination 지원.
- `POST /products/export`: 사용자가 체크박스로 다중 선택한 상품 ID를 바탕으로 커스텀 가공 엑셀 파일(`.xlsx`) 생성 및 스트리밍.

### 4. Apple 스타일 프리미엄 대시보드 UI 연동 (`products/page.tsx`)
- multi-checkbox 체크, debounced 검색바, 업로드 배치 드롭다운 필터 적용.
- `PillButton` 컴포넌트의 `disabled` 속성을 이용해 중복 엑셀 내보내기 요청 방지.
- Zustand 전역 Task 상태 및 실시간 Intelligence Capsule Drawer 와의 완벽한 결합을 통한 실시간 진행률 추적.

## Why This Works
- **완벽한 데이터 격리 및 확장**: 네이버, 쿠팡 등 플랫폼마다 상이한 속성을 고정 컬럼이 아닌 `JSONB` 기반 `ProductPlatformMapping` 테이블에 저장하므로, 추후 11번가나 G마켓, 해외 쇼핑몰이 추가되더라도 DB 스키마 DDL 수정 없이 로직과 데이터 행 삽입만으로 즉시 확장 가능합니다.
- **성능 최적화**: 엑셀 업로드 시 비차단(Non-blocking)으로 바로 응답을 주고, Celery 워커가 백그라운드에서 실시간으로 DB를 업데이트하므로 클라이언트는 병목 없이 실시간 진행률을 확인하고 필요한 상품만 선택해 엑셀로 기민하게 추출할 수 있습니다.

## Prevention
- **비동기 Mock Test 강화**: 비동기 API 및 Celery 태스크와 연동된 테스트가 동기식 Mock 호출로 인해 테스트 대기(hanging)나 `TypeError`를 발생시키지 않도록 `pytest` 내 모든 비동기 호출을 `AsyncMock`으로 통일성 있게 격리하여 레그레션 테스트 스위트를 견고히 유지합니다 (`test_tasks.py`, `test_keyword_engine.py`, `test_backoff.py`).
- **PillButton UI 가드**: 중복된 내보내기/요청을 차단하기 위해 UI 상에서 `disabled` 제어를 엄격하게 통제하여 불필요한 중복 파일 생성 IO 자원 낭비를 원천 차단합니다.

## Related Issues
- GitHub #42 (Product DB Migration)
