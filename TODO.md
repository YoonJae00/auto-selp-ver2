# Auto-Selp Project TODO

Last updated: 2026-05-20

Authoritative task sources:
- GitHub open issues: #32, #33, #34, #35, #42, #43
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
- [x] **Secure Authentication Upgrade**: OAuth2 (Google, Naver) & Admin secret verification.
- [x] **Auth UI Redesign**: Premium Glassmorphism & Animated Mesh Gradient background for Login/Register.
- [x] **User Profile**: Nickname support and multi-provider storage.
- [x] **Command Center Dashboard**: 3-tier workspace layout (KPIs, Process Monitor, Action Queue).
- [x] **KIPRIS API 호출 최적화**: LLM 배치 브랜드 분류 → brand_suspected만 KIPRIS 검증. 상품당 KIPRIS 호출 99% 절감 (20회→avg 0.2회). 월 1,000회 한도 내 약 5,000개 처리 가능.
- [x] **KIPRIS 사용자 설정 On/Off**: 설정 페이지 토글 추가. Off 시 LLM 추측 기반으로 브랜드 의심 키워드 자동 제외.
- [ ] **Batch Processing Optimizations**: Parallel LLM calls for larger datasets. GitHub #32
- [ ] **User API Key Management**: UI for users to input their own Naver/Coupang keys. GitHub #33
- [ ] **Mobile Responsive UI**: Adjust frontend for tablets and phones. GitHub #34
- [ ] **CI/CD Pipeline**: Github Actions for automated testing and deployment. GitHub #35

## Phase 4: Intelligence Capsule & Background Processing
- [x] **Global Task Store**: Create `taskStore` with Zustand persistence.
- [x] **Background Polling**: Implement global `useTaskPolling` hook.
- [x] **Intelligence Capsule UI (v1)**: Implement Siri-glow animated capsule component.
- [x] **Process Page Refactoring**: Integrate global store and remove local polling.
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

## Phase 5: Continuous Improvement & Knowledge Compounding (Completed)
- [x] **Install Compound Engineering Skill**: Integrate `ce-compound` and related skills from `EveryInc/compound-engineering-plugin`.
- [x] **Workflow Integration**: Add "Compound" stage to Superpowers final step (review end).
- [x] **Solution Documentation**: Start documenting major fixes and architectural decisions in `docs/solutions/`.

## Phase 6: 다음 세션 예정 (Next Session)
- [ ] **KIPRIS 저작권 로직 정리**: KIPRIS On/Off에 따른 UX 처리 방식 재기획. GitHub #43
  - KIPRIS On: 키워드 단계에 `상표 의심` 인라인 표시
  - KIPRIS Off: `LLM 추측 제외` 인라인 표시
  - 의심 키워드 없음: `상표권 이슈 없음` 표시
  - `filtered` 데이터를 KIPRIS 확인/LLM 추측으로 구분
  - Legacy `TrademarkModal.tsx`와 미사용 CSS 정리
- [ ] **상품 DB 마이그레이션**: 엑셀 업/다운로드 방식 → PostgreSQL 기반 상품 관리로 전환. GitHub #42
  - 상품 테이블 스키마 설계
  - 가공 결과를 DB에 직접 저장
  - 상품 목록 페이지 구현 (검색/필터/수정)
  - 선택/전체 엑셀 내보내기
