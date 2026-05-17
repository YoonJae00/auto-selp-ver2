# 2026-05-17-dashboard-command-center-design

## 1. 개요 (Overview)
본 문서는 Auto-Selp 서비스의 메인 작업 화면인 `/home` 대시보드 디자인 사양을 정의한다. 기존의 미니멀한 Apple 스타일에서 벗어나, 다수 쇼핑몰을 운영하는 사용자의 생산성을 극대화하기 위한 '커맨드 센터(Command Center)' 컨셉의 대시보드를 구축한다.

## 2. 디자인 원칙 (Design Principles)
- **가시성(Visibility)**: 비즈니스 지표와 시스템 상태를 1초 이내에 파악할 수 있도록 한다.
- **몰입성(Focus)**: 사용자가 즉시 처리해야 할 업무(Action Items)를 명확히 제시한다.
- **연결성(Connectivity)**: 시스템(AI 엔진)과 사용자 간의 상호작용을 실시간으로 시각화한다.

## 3. 레이아웃 구조 (Layout Structure)
화면을 수직 방향으로 3개의 밴드(Band)로 구분하며, 12컬럼 그리드 시스템을 적용한다.

### Tier 1: KPI 대시보드 (Top Section)
- **목적**: 통합 매출 및 쇼핑몰별 상태 요약 파악
- **구성 요소**:
    - **통합 메트릭 카드**: 오늘의 총 매출, 전일 대비 증감(%), 이번 달 누적 매출.
    - **쇼핑몰별 상태 칩 (Store Chips)**: 등록 상품 수, 판매 상품 수를 각 몰별(쿠팡, 네이버 등)로 요약하여 가로 스크롤 형태로 배치.
    - **디자인**: 굵은 타이포그래피, 증감 추이를 보여주는 스파크라인(Sparkline) 포함.

### Tier 2: 프로세스 모니터 (Middle Section)
- **목적**: AI 엔진의 가공 작업 실시간 모니터링
- **구성 요소**:
    - **진행 중인 작업 (Active Tasks)**: 파일명, 진행 단계(분석/가공/업로드), 실시간 프로그레스 바(%), 펄스 애니메이션.
    - **최근 히스토리**: 완료된 최근 작업 3~5개, '결과 보기' 및 '다운로드' 퀵 버튼.
- **디자인**: 진행 상태에 따른 컬러 코딩 (진행: Blue, 완료: Green, 오류: Red).

### Tier 3: 할 일 목록 (Bottom Section)
- **목적**: 즉시 처리가 필요한 업무 큐(Queue) 관리
- **구성 요소**:
    - **확인 필요 리스트**: 카테고리 매핑 미확정 건, 이미지 누락 건, 가공 오류 건 등.
    - **퀵 액션**: 리스트 우측에 '수정', '재가공', '확인' 등 즉시 실행 버튼 배치.
- **디자인**: 정보 밀도가 높은 컴팩트 리스트 스타일, 시급도에 따른 뱃지(Badge) 적용.

## 4. 디자인 사양 (Design Specifications)

### 폰트 및 컬러
- **폰트**: Inter (Negative Letter-spacing 적용)
- **헤드라인**: SF Pro Display 스타일 (34px, Weight 600, -0.022em)
- **데이터 숫자**: 볼드체 강조 (28px~32px)
- **컬러**: 
    - `--primary`: #0066cc (Apple Blue)
    - `--success`: #34c759 (Green)
    - `--warning`: #ff9500 (Orange)
    - `--error`: #ff3b30 (Red)

### 컴포넌트
- **Card**: `--canvas` 배경, `--hairline` 보더, `border-radius: 18px`.
- **Progress Bar**: `height: 8px`, `border-radius: 4px`, 배경색 대조 강조.
- **Store Chip**: `border-radius: 12px`, 아이콘 + 텍스트 조합.

## 5. 데이터 흐름 (Data Flow)
1. 사용자가 접속 시 `/api/auth/me`를 통해 소속된 쇼핑몰 정보를 가져옴.
2. `/api/processor/status/all` 등을 통해 현재 진행 중인 모든 태스크 정보를 폴링(Polling)하거나 웹소켓으로 수신.
3. 지표 데이터는 주기적으로 백엔드에서 집계된 캐시 데이터를 로드.

## 6. 예외 처리 (Error Handling)
- **데이터 없음**: "아직 등록된 쇼핑몰이 없습니다" 또는 "진행 중인 작업이 없습니다" 등의 빈 상태(Empty State) 디자인 적용.
- **가공 실패**: Tier 2에서 오류 발생 시 Tier 3로 즉시 해당 항목이 이동하며 알림 뱃지 활성화.
