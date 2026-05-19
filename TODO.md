# Auto-Selp Project TODO

## Phase 2: Frontend & Processing Integration (Completed)
- [x] Zustand AuthStore & persistent state
- [x] Login/Register pages & Route protection
- [x] Multi-step Processing UI (Upload -> Map -> Process)
- [x] Platform-specific category column mapping (Naver vs Coupang)
- [x] Shared Docker volumes for Worker file access
- [x] Naver AD API signature & encoding fix
- [x] Final E2E Integration test with `doto_sample.xlsx`

## Phase 3: Advanced Features & Refinement (In Progress)
- [x] **Secure Authentication Upgrade**: OAuth2 (Google, Naver) & Admin secret verification.
- [x] **Auth UI Redesign**: Premium Glassmorphism & Animated Mesh Gradient background for Login/Register.
- [x] **User Profile**: Nickname support and multi-provider storage.
- [x] **Command Center Dashboard**: 3-tier workspace layout (KPIs, Process Monitor, Action Queue).
- [x] **KIPRIS API 호출 최적화**: LLM 배치 브랜드 분류 → brand_suspected만 KIPRIS 검증. 상품당 KIPRIS 호출 99% 절감 (20회→avg 0.2회). 월 1,000회 한도 내 약 5,000개 처리 가능.
- [x] **KIPRIS 사용자 설정 On/Off**: 설정 페이지 토글 추가. Off 시 LLM 추측 기반으로 브랜드 의심 키워드 자동 제외, 결과 모달에서 🔴 KIPRIS 확인 / 🟡 LLM 추측 두 섹션으로 분리 표시.
- [ ] **Batch Processing Optimizations**: Parallel LLM calls for larger datasets.
- [ ] **User API Key Management**: UI for users to input their own Naver/Coupang keys.
- [ ] **Mobile Responsive UI**: Adjust frontend for tablets and phones.
- [ ] **CI/CD Pipeline**: Github Actions for automated testing and deployment.

## Phase 4: Intelligence Capsule & Background Processing
- [x] **Global Task Store**: Create `taskStore` with Zustand persistence.
- [x] **Background Polling**: Implement global `useTaskPolling` hook.
- [x] **Intelligence Capsule UI (v1)**: Implement Siri-glow animated capsule component.
- [x] **Process Page Refactoring**: Integrate global store and remove local polling.
- [x] **Intelligence Capsule 전면 재설계 (v2)**:
  - 위치: 우측 하단 고정 (`right: 24px; bottom: 24px`)
  - 작업 중: Apple Watch 스타일 ambient conic-gradient 회전 glow
  - 드로어: 작업 목록 → 클릭 시 풀스크린 모달 전환
  - 풀스크린 모달: LangGraph Trace 스타일 트리 뷰 (accordion + shimmer)
- [x] **Backend 단계별 타이밍 & 상세 데이터 수집**:
  - `completed_rows`에 `refined_name`, `keywords`, `filtered`, `naver_category`, `coupang_category` 포함
  - `result`에도 `completed_rows` + `total` 포함 → 완료 후 상세 열람 가능
- [x] **.xls 파일 처리 버그 수정**: `re.sub(.xlsx?$ → _processed.xlsx)` + `engine='openpyxl'`
- [x] **상표권 검증 모달 제거**: TrademarkModal 컴포넌트 및 관련 코드 정리
- [x] **모달 스크롤 수정**: `min-height: 0` + 명시적 height 설정
- [x] **Docker 이미지 리빌드**: `docker compose build worker` 워크플로우 확립

## Phase 5: 다음 세션 예정 (Next Session)
- [ ] **KIPRIS 저작권 로직 정리**: KIPRIS On/Off에 따른 UX 처리 방식 재기획
  - 상표권 의심 키워드를 트레이스 뷰 내에서 인라인으로 표시하는 방식 검토
- [ ] **상품 DB 마이그레이션**: 엑셀 업/다운로드 방식 → PostgreSQL 기반 상품 관리로 전환
  - 상품 테이블 스키마 설계
  - 가공 결과를 DB에 직접 저장
  - 상품 목록 페이지 구현 (검색/필터/수정)

