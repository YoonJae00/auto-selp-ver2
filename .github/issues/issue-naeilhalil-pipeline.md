---
name: Feature Request
about: Support Naeil-Halil wholesale site for Naver/Coupang registration forms and integrate with AI processing pipeline.
title: "[Feat] 내일할일 도매처 Naver/Coupang 등록 양식 대응 및 AI 가공 파이프라인 연계"
labels: feat
assignees: ''

---

##  Overview
도매 배송 대행 플랫폼인 **'내일할일'**의 상품 목록 엑셀 데이터 형식을 시스템에 업로드하여 분석하고, 국내 주요 커머스 채널인 **네이버 스마트스토어** 및 **쿠팡 위윙(Wing)**의 대량 등록 엑셀 양식 규격에 완벽히 호환되도록 데이터를 변환 및 수출(Export)하는 기능을 개발합니다. 

이 과정에서 네이버와 쿠팡의 노출 가이드라인(상품명 글자수 제한, 검색 카테고리 매칭, 검색 태그 추출 및 블랙리스트 제거)에 최적화된 **맞춤형 AI 가공 파이프라인**을 추가하여 판매자의 상품 등록 프로세스를 극대화하여 자동화합니다.

## 🎯 Goals
- [ ] **내일할일 도매처 컬럼 매핑 프리셋 등록**: `WholesaleSite` 테이블 및 시드 데이터에 내일할일의 기본 엑셀 구조 매핑 JSONB 정의
- [ ] **네이버/쿠팡 대량 등록용 엑셀 내보내기 템플릿 개발**: `/products/export` API를 고도화하여 네이버 스마트스토어 일괄 등록 엑셀 형식 및 쿠팡 엑셀 일괄 등록 형식 다운로드 구현
- [ ] **채널 맞춤형 AI 가공 파이프라인 구축**:
  - **네이버 규격**: 상품명 50자 내외 최적화, 네이버 카테고리 자동 추천, 검색 태그(최대 10개) 추출 및 유효 태그 필터링
  - **쿠팡 규격**: 검색 최적화형 상품 명명 규칙 적용, 쿠팡 카테고리 ID 매핑, 상표권 및 노출 금지 키워드 필터링 강화
- [ ] **상품 관리 UI 연동**: `/products` 페이지의 선택/전체 상품 액션 툴바에 '네이버 양식 다운로드', '쿠팡 양식 다운로드' 버튼 추가 및 UI/UX 강화

## 🎨 Design Considerations
*Referencing `design.md` where applicable.*
- **UI/UX**: 
  - `/products` 테이블 액션 툴바에 Apple-inspired 유리 모티프(Glassmorphism) 세그먼트 컨트롤 또는 드롭다운 버튼을 배치하여 네이버/쿠팡 전용 다운로드 액션을 깔끔하게 제공합니다.
  - 다운로드 파일 생성 및 가공 시 Siri-glow 또는 Shimmer 효과를 활용한 모달/토스트 안내로 사용자 피드백을 강화합니다.
- **Rhythm**: 
  - 액션 툴바 아이콘 및 텍스트 정렬을 미려하게 조정하고, 버튼 호버 시의 마이크로 애니메이션을 추가하여 화면의 시각적 활력을 높입니다.

## 🛠 Implementation Plan

### 1. Research
- `내일할일` 상품 대장 엑셀 파일의 기본 헤더 구성 및 데이터 형식(옵션 구분자, 이미지 리스트 등) 분석
- 네이버 스마트스토어 및 쿠팡 윙의 최신 일괄 등록 엑셀 템플릿 규격 분석 및 필수/선택 필드 요건 매핑

### 2. Strategy
- `services/processor/`에 채널별(Naver, Coupang) 가공 프로필을 분리하여 적용할 수 있도록 AI prompt 및 post-processing 유틸리티 구현
- `pandas` 및 `openpyxl`을 활용하여 메모리 스트리밍 방식으로 네이버/쿠팡 서식에 맞게 엑셀 행을 구성하는 `ProductExporter` 아키텍처 개발

### 3. Execution
- **Database / Backend**:
  - `wholesale_sites` 테이블에 내일할일 기본 매핑 템플릿 Seed 데이터 추가
  - `ProductPlatformMapping` 상태 관리에 네이버/쿠팡 연동 상태 유기적 결합
  - `/api/products/export/naver`, `/api/products/export/coupang` 라우트 구현
- **AI Pipeline (LangGraph / Celery)**:
  - 네이버 스마트스토어 최적화 프롬프트 설계 (50자 글자수 제한 엄수, 브랜드 중복 제거, 검색 태그 추출)
  - 쿠팡 윙 최적화 프롬프트 설계 (검색 키워드 나열 및 옵션 정보 명료화)
  - DB 저장 시 플랫폼별 `mapped_attributes` 및 `category_id` 자동 바인딩
- **Frontend (Next.js)**:
  - `/products` 페이지 상단 Floating Toolbar에 쇼핑몰별 엑셀 내보내기 인터페이스 구현

### 4. Verification
- `test_wholesale.py`에 내일할일 템플릿 테스트 케이스 추가
- 가공 완료된 네이버/쿠팡 엑셀 다운로드 데이터를 공식 셀러 센터 양식 업로더를 통해 양식 유효성 및 업로드 무결성 자동/수동 검증

## 📝 Additional Context
- 내일할일 도매처는 대형 배송 대행 도매 사이트 중 하나로, 수천 개의 상품 정보를 제공하므로 메모리 누수 방지 및 병렬 LLM 처리(GitHub #32) 기능과의 안정적인 결합이 필수적입니다.
