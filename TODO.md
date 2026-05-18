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
- [x] **Intelligence Capsule UI**: Implement Siri-glow animated capsule component.
- [x] **Process Page Refactoring**: Integrate global store and remove local polling.
