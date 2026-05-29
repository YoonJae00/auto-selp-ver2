# Auto-Selp Project TODO

Last updated: 2026-05-28

Authoritative task sources:
- GitHub open issues: #32, #33, #34, #35, #43, #45
- GitHub completed issues: #42, #46
- This file: product/engineering backlog snapshot
- `docs/superpowers/current_state.md`: implementation state snapshot

Note: older files under `docs/superpowers/plans/` are historical implementation plans. Their unchecked boxes do not necessarily mean the work is still pending.

## Phase 2: Frontend & Processing Integration (Completed)
- [x] Zustand AuthStore & persistent state
- [x] Login/Register pages & Route protection
- [x] Multi-step Processing UI (Upload -> Map -> Process)
- [x] Platform-specific category column mapping (Naver vs Coupang)
- [x] Shared Docker volumes for Worker file access
- [x] Naver AD API signature & encoding fix
- [x] Final E2E Integration test with `doto_sample.xlsx`

## Phase 3: Advanced Features & Refinement (In Progress)
- [/] **Product Columns Visibility & Reordering**: Custom column visibility toggle and native drag-and-drop column reordering persisted in localStorage. (Task 1: CSS 스타일 구현 완료)
- [x] **Secure Authentication Upgrade**: OAuth2 (Google, Naver) & Admin secret verification.
- [x] **Auth UI Redesign**: Premium Glassmorphism & Animated Mesh Gradient background for Login/Register.
- [x] **User Profile**: Nickname support and multi-provider storage.
- [x] **Command Center Dashboard**: 3-tier workspace layout (KPIs, Process Monitor, Action Queue).
- [x] **KIPRIS API 호출 최적화**: LLM 배치 브랜드 분류 → brand_suspected만 KIPRIS 검증. 상품당 KIPRIS 호출 99% 절감 (20회→avg 0.2회). 월 1,000회 한도 내 약 5,000개 처리 가능.
- [x] **KIPRIS 사용자 설정 On/Off**: 설정 페이지 토글 추가. Off 시 LLM 추측 기반으로 브랜드 의심 키워드 자동 제외.
- [ ] **Batch Processing Optimizations**: Parallel LLM calls for larger datasets. GitHub #32
- [ ] **User API Key Management**: UI for users to input their own Naver/Coupang keys. GitHub #33
- [ ] **Mobile Responsive UI**: Adjust frontend for tablets and phones. GitHub #34
- [x] **Product Processing Page UX/UI Improvement**: Relocate processing button to table toolbar, implement floating bar, top pagination, name search, dynamic page sizing (10/30/50/100/200), and table-header checkbox select-all control.
- [x] **Premium Landing Page Redesign**: Complete Apple-inspired minimalist redesign with high-fidelity responsive sections, a frosted-glass header, and an interactive **Live Task Graph** demonstrating Auto-Selp's 5-stage AI processing pipeline in real-time.
- [ ] **CI/CD Pipeline**: Github Actions for automated testing and deployment. GitHub #35


## Phase 4: Intelligence Capsule & Background Processing
- [x] **Global Task Store**: Create `taskStore` with Zustand persistence.
- [x] **Background Polling**: Implement global `useTaskPolling` hook.
- [x] **Intelligence Capsule UI (v1)**: Implement Siri-glow animated capsule component.
- [x] **Process Page Refactoring**: Integrate global store and remove local polling.
- [x] **Real-time Product List Syncing**: Dynamically map global `taskStore` completed rows and active row status directly to the products list in real-time, with a single DB refetch once completed.
- [x] **Intelligence Capsule 전면 재설계 (v2)**:
  - 위치: AI Mall layout 좌측 하단 고정 (`left: calc(var(--sidebar-width) + 24px); bottom: 24px`)
  - 작업 중: Apple Watch 스타일 ambient conic-gradient 회전 glow
  - 드로어: 작업 목록 → 클릭 시 상세 트리 뷰 전환
  - 상세 뷰: LangGraph Trace 스타일 트리 뷰 (accordion + shimmer)
- [x] **Backend 단계별 타이밍 & 상세 데이터 수집**:
  - `completed_rows`에 `refined_name`, `keywords`, `filtered`, `naver_category`, `coupang_category` 포함
  - `result`에도 `completed_rows` + `total` 포함 → 완료 후 상세 열람 가능
- [x] **.xls 파일 처리 버그 수정**: `re.sub(.xlsx?$ → _processed.xlsx)` + `engine='openpyxl'`
- [x] **상표권 검증 모달 호출 제거**: 트레이스 뷰 중심 UX로 이동. Legacy `TrademarkModal.tsx` 파일과 관련 CSS 정리는 Phase 5 #43에서 함께 처리.
- [x] **모달 스크롤 수정**: `min-height: 0` + 명시적 height 설정
- [x] **Docker 이미지 리빌드**: `docker compose build worker` 워크플로우 확립
- [x] **Sidebar Clickability, Layout Alignment, & Automatic Collapsing Fix**: Resolved sidebar unclickability and icon misalignment issues on dense pages (such as `/process`) by adding a stacking context (`z-index: 100`) to `.sidebar` and setting `display: none` on `.sidebarCollapsed .navLabel`. Also resolved the ultimate root cause of UI unresponsiveness: fixed a critical React infinite rendering loop in `ProcessPage`'s task synchronization hook by replacing a state-driven previous task tracker with `useRef`. Additionally, fixed the automatic sidebar collapse regression for dense workspaces (`/process`, `/products`, `/upload`) by implementing workspace-aware separate localStorage preferences (`autoselp.sidebarCollapsed.dense` and `autoselp.sidebarCollapsed.normal`) to prevent a global user toggle preference from permanently disabling the automatic page-specific collapse behavior.


## Phase 5: Continuous Improvement & Knowledge Compounding (Completed)
- [x] **Install Compound Engineering Skill**: Integrate `ce-compound` and related skills from `EveryInc/compound-engineering-plugin`.
- [x] **Workflow Integration**: Add "Compound" stage to Superpowers final step (review end).
- [x] **Solution Documentation**: Start documenting major fixes and architectural decisions in `docs/solutions/`.

## Phase 6: 다음 세션 예정 (Next Session)
- [ ] **플레이오토 내보내기 및 컬럼 매핑 고도화**: GitHub #45
  - [ ] '플레이오토' 상품 등록 솔루션 전용 규격 양식(엑셀 일괄 등록용 서식) 정의 및 맵핑 로직 설계
  - [ ] 가공 및 저장 완료된 상품 데이터를 플레이오토 규격 양식의 엑셀 대장 파일로 생성 및 다운로드(내보내기)하는 기능 추가
  - [ ] 도매처별 Visual Column Mapper를 활용한 플레이오토 필드 대응 및 매핑 로직 수정
- [ ] **KIPRIS 저작권 로직 정리**: KIPRIS On/Off에 따른 UX 처리 방식 재기획. GitHub #43
  - KIPRIS On: 키워드 단계에 `상표 의심` 인라인 표시
  - KIPRIS Off: `LLM 추측 제외` 인라인 표시
  - 의심 키워드 없음: `상표권 이슈 없음` 표시
  - `filtered` 데이터를 KIPRIS 확인/LLM 추측으로 구분
  - Legacy `TrademarkModal.tsx`와 미사용 CSS 정리
- [/] **내일할일 도매처 Naver/Coupang 등록 양식 대응 및 AI 가공 파이프라인 연계**: GitHub #47
  - [ ] '내일할일' 도매처 전용 엑셀 업로드 기본 컬럼 매핑 설계 및 DB Seed 등록
  - [x] Naver Smart Store 및 Coupang Wing 엑셀 일괄 등록 서식 분석 및 DB 매핑 기획 완료 ([analysis_results.md](file:///Users/yoonjae/.gemini/antigravity-cli/brain/cadf0c75-03bf-4464-817c-0d707c7389c4/analysis_results.md))
  - [ ] Naver Smart Store 및 Coupang Wing 엑셀 일괄 등록 서식 전용 익스포트 기능 개발
  - [ ] 각 쇼핑몰 가이드라인(상품명 길이, 검색 키워드 태그, 카테고리 매핑)에 맞춘 특화 AI 가공 파이프라인 구현
  - [ ] 상품 목록 페이지(`/products`)에 Naver/Coupang 대장 다운로드(내보내기) UI 및 액션 툴바 연동
- [x] **상품 DB 마이그레이션**: 엑셀 업/다운로드 방식 → PostgreSQL 기반 상품 관리로 전환. GitHub #42
  - [x] **설계 완료**: [2026-05-20-product-db-migration.md](file:///home/yoonjae/auto-selp-ver2/docs/superpowers/plans/2026-05-20-product-db-migration.md) 스키마 상세 참조
  - [x] 상품 테이블 스키마 생성 및 적용 (확장형 Core/Platform 분리 구조)
  - [x] 가공 결과를 DB에 직접 저장
  - [x] 상품 목록 페이지 구현 (검색/필터/수정)
  - [x] 선택/전체 엑셀 내보내기
- [x] **도매처 관리 및 스마트 갱신 시스템 (Wholesale Management & Smart Upsert)**: GitHub #46
  - [x] `WholesaleSite` 테이블 및 모델 구현 (도매처 메타 및 컬럼 매핑 JSONB)
  - [x] `Product` 및 `ProductPlatformMapping`에 대조/갱신용 상세 컬럼 및 트래킹 컬럼 추가 (`price_changed`, `stock_changed`, `last_synced_price` 등)
  - [x] SMART UPSERT change-tracking 로직 구현 (Excel 데이터와 기존 DB/동기화 값 비교 후 `pending_update` 상태 전이 및 변동 플래그 설정)
  - [x] `/wholesale-sites` CRUD API 및 `/process-db` 업그레이드 (도매처별 커스텀 템플릿 매핑 및 스마트 갱신 적용)
  - [x] Next.js `/upload` 도매처 관리 & Visual Column Mapper 드래그 앤 드롭 업로드 화면 개발
  - [x] `/products` 상품 목록에 도매처 필터, 업데이트 대기 필터, 변동 상태(가격/품절) 뱃지, disabled 쇼핑몰 동기화 버튼 추가

## Phase 7: Marketplace Listing
- [x] Marketplace draft foundation: service boundary, snapshot contract, account settings, Smart Store/Coupang initial draft adapters, draft generation jobs, and processor success notification.
- [x] Unified registration inbox and per-market settings/editing UI.
- [ ] External Smart Store/Coupang submission jobs, retry behavior, and registration history. ([GitHub #52](https://github.com/YoonJae00/auto-selp-ver2/issues/52))
- [x] **Naver Attribute Schema Provider**: Fetch, cache, and model Naver attribute schemas using Redis caching.
- [x] **Coupang Attribute Schema Provider**: Fetch, cache, and model Coupang attribute schemas using Redis caching.
- [x] **Attribute Mappers**: Implement Naver and Coupang attribute mappers translating market-neutral extracted specifications into market-specific formats.
- [x] **extract_attributes Node in LangGraph**: Integrated the attribute extraction node into the product processing LangGraph to run after category mapping and before persistence.
- [x] **Consume mapped_attributes in Adapters**: Smart Store and Coupang adapters now consume mapped category attributes during draft generation (Task 6).
- [ ] Recipe extensions for SEO titles and category-specific attributes.
- [ ] Margin calculator UI, bulk price-policy application, and per-product price-override preview.
