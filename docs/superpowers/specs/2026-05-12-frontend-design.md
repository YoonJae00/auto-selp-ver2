# 설계서: Auto-Selp 프론트엔드 (AI Mall & Landing)

## 1. 개요 (Overview)
Auto-Selp의 사용자 인터페이스는 Apple의 디자인 철학을 계승한 미니멀리즘과 강력한 기능을 결합합니다. 사용자는 화려한 랜딩 페이지를 통해 서비스에 진입하며, 로그인 후에는 AI가 관리하는 자신만의 쇼핑몰 관리 환경(`AI Mall`)에서 작업을 수행합니다.

## 2. 기술 스택 (Tech Stack)
- **프레임워크**: Next.js 14+ (App Router)
- **스타일링**: Vanilla CSS / CSS Modules (Apple 디자인 지침의 정밀한 구현을 위함)
- **상태 관리**: Zustand (경량 전역 상태 관리)
- **데이터 페칭**: SWR 또는 TanStack Query (실시간 대시보드 업데이트용)
- **통신**: API Gateway (Nginx)를 통한 백엔드 서비스 연동

## 3. 라우팅 및 레이아웃 구조
Next.js의 Route Groups를 사용하여 마케팅 영역과 서비스 영역을 물리적으로 분리합니다.

### 3.1 `(marketing)` 그룹
- **경로**: `/` (루트)
- **용도**: 비로그인 사용자용 서비스 소개 및 랜딩 페이지
- **디자인 특징**: 
    - Full-bleed Tiles (White, Parchment, Near-Black 교차)
    - 대담한 헤드라인과 고해상도 제품 이미지 중심
    - `SF Pro` 느낌의 정교한 타이포그래피

### 3.2 `(ai-mall)` 그룹
- **경로**: `/home`, `/products`, `/settings` 등
- **용도**: 로그인 사용자용 핵심 서비스 대시보드
- **디자인 특징**:
    - 고정 사이드바 (`Auto-Selp AI Mall` 브랜드 노출)
    - `Glassmorphism` (Frosted Glass) 효과가 적용된 상단 내비게이션
    - 데이터 시각화 중심의 깨끗한 화이트 캔버스

## 4. 디자인 시스템 (Apple Style Guidelines)
`design.md`에 명시된 지침을 엄격히 준수합니다.

- **Color**:
    - `Action Blue` (#0066cc): 모든 클릭 가능한 요소의 표준 색상
    - `Parchment` (#f5f5f7): 보조 배경 및 섹션 구분
    - `Near-Black` (#1d1d1f): 텍스트 및 다크 섹션 배경
- **Typography**:
    - 본문 17px 기준, 행간 1.47
    - 제목: Negative Letter-spacing (-0.02em) 적용으로 'Apple Tight' 느낌 구현
- **Components**:
    - `Pill Button`: 완전한 둥근 형태의 버튼 (Pill shape)
    - `Active Scale`: 모든 버튼 클릭 시 `scale(0.95)` 마이크로 인터랙션 적용
    - `No Shadows`: UI 요소(카드, 버튼)에 그림자 배제 (단, 제품 이미지에는 부드러운 그림자 허용)

## 5. 주요 페이지 상세
1. **랜딩 페이지 (`/`)**: 서비스의 가치 제안 및 핵심 기능 요약.
2. **AI 쇼핑몰 홈 (`/home`)**: 오늘의 매출, 가공 대기 현황 등 주요 지표 요약 대시보드.
3. **상품 가공 (`/products`)**: 엑셀 업로드 인터페이스 및 AI 가공 프로세스 트래킹.
4. **설정 (`/settings`)**: 플랫폼 연동 API 키 관리 및 사용자 프로필 설정.

## 6. 보안 및 데이터 흐름
- **인증**: Next.js Middleware를 통한 세션 체크 및 비로그인 시 `/login` 리다이렉트.
- **보안**: 민감한 정보는 Server Actions를 통해 처리하여 클라이언트 노출 최소화.
- **성능**: 이미지 최적화(`next/image`) 및 정적 섹션의 ISR(Incremental Static Regeneration) 활용.
