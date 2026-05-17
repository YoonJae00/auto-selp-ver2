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
- [ ] **KIPRIS Actual Integration**: Replace mock trademark check with real API.
- [ ] **Batch Processing Optimizations**: Parallel LLM calls for larger datasets.
- [ ] **User API Key Management**: UI for users to input their own Naver/Coupang keys.
- [ ] **Mobile Responsive UI**: Adjust frontend for tablets and phones.
- [ ] **CI/CD Pipeline**: Github Actions for automated testing and deployment.

## Phase 4: Intelligence Capsule & Background Processing
- [x] **Global Task Store**: Create `taskStore` with Zustand persistence.
- [x] **Background Polling**: Implement global `useTaskPolling` hook.
- [ ] **Intelligence Capsule UI**: Implement Siri-glow animated capsule component.
- [ ] **Process Page Refactoring**: Integrate global store and remove local polling.
