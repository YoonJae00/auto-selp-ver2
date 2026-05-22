# Product Processing UX Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate the 'Process Selected' button to the table toolbar, implement a bottom-center floating glassmorphic action bar when products are selected, and add a product name search input and secondary pagination to the top filter bar.

**Architecture:** Frontend-only state and style optimization. Connects to the existing FastAPI `/api/processor/products` search support by adding `search` to the query params.

**Tech Stack:** Next.js (React), TypeScript, Vanilla CSS.

---

## Proposed File Changes

### Task 1: Update process styles (`process.module.css`)
**Files:**
- Modify: `frontend/src/app/(ai-mall)/process/process.module.css`

- [ ] **Step 1: Add new styles for search input, toolbar actions, top pagination, and floating action bar**

  Add the following classes to `frontend/src/app/(ai-mall)/process/process.module.css`. Show the exact changes to be inserted:

  ```css
  /* Toolbar Actions Wrapper */
  .toolbarActions {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  /* Filter Bar Left/Right Layout */
  .filterBar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
  }

  .filterLeft {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }

  .filterRight {
    display: flex;
    align-items: center;
  }

  /* Search Input Group */
  .searchGroup {
    display: inline-flex;
    align-items: center;
    position: relative;
    background: var(--canvas);
    border: 1px solid var(--hairline);
    border-radius: 10px;
    padding: 0 10px 0 34px;
    height: 36px;
    min-width: 220px;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .searchGroup:focus-within {
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(var(--primary-rgb), 0.15);
  }

  .searchGroup::before {
    content: "🔍";
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 14px;
    color: var(--ink-muted-48);
  }

  .searchInput {
    border: none;
    background: transparent;
    height: 100%;
    width: 100%;
    font-size: 13px;
    color: var(--ink);
    outline: none;
  }

  .searchInput::placeholder {
    color: var(--ink-muted-48);
  }

  .clearSearchButton {
    background: transparent;
    border: none;
    color: var(--ink-muted-48);
    font-size: 12px;
    cursor: pointer;
    padding: 4px;
    margin-left: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: background 0.2s;
  }

  .clearSearchButton:hover {
    background: rgba(0, 0, 0, 0.05);
    color: var(--ink);
  }

  /* Top Pagination Component */
  .topPagination {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-muted-80);
  }

  .topPagination button {
    border: 1px solid var(--hairline);
    border-radius: 8px;
    background: var(--canvas);
    color: var(--ink);
    padding: 0 8px;
    height: 28px;
    font-size: 12px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 48px;
    transition: border-color 0.2s, background-color 0.2s;
  }

  .topPagination button:hover:not(:disabled) {
    border-color: var(--primary);
    background: rgba(var(--primary-rgb), 0.04);
  }

  .topPagination button:disabled {
    cursor: not-allowed;
    color: var(--ink-muted-48);
    background: var(--canvas-parchment);
    opacity: 0.6;
  }

  .topPagination span {
    font-variant-numeric: tabular-nums;
  }

  /* Floating Action Bar */
  .floatingActionBar {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 100;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(16px) saturate(120%);
    -webkit-backdrop-filter: blur(16px) saturate(120%);
    border: 1px solid rgba(0, 0, 0, 0.08);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12);
    border-radius: 20px;
    padding: 12px 24px;
    animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    max-width: 90%;
    width: auto;
    display: flex;
    align-items: center;
  }

  .floatingContent {
    display: flex;
    align-items: center;
    gap: 20px;
    white-space: nowrap;
  }

  .floatingText {
    font-size: 14px;
    color: var(--ink-muted-80);
  }

  .floatingText strong {
    color: var(--primary);
    font-weight: 700;
  }

  .floatingButtons {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .floatingCancelButton {
    background: transparent;
    border: 1px solid var(--hairline);
    border-radius: 999px;
    height: 36px;
    padding: 0 16px;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink-muted-80);
    cursor: pointer;
    transition: background-color 0.2s, border-color 0.2s;
  }

  .floatingCancelButton:hover {
    background: rgba(0, 0, 0, 0.04);
    border-color: var(--ink-muted-48);
  }

  @keyframes slideUp {
    from {
      transform: translate(-50%, 100px);
      opacity: 0;
    }
    to {
      transform: translate(-50%, 0);
      opacity: 1;
    }
  }

  @media (max-width: 760px) {
    .filterBar {
      flex-direction: column;
      align-items: stretch;
    }
    .filterLeft {
      flex-direction: column;
      align-items: stretch;
    }
    .searchGroup {
      width: 100%;
    }
    .filterRight {
      justify-content: flex-end;
    }
    .floatingActionBar {
      width: calc(100% - 32px);
      bottom: 16px;
    }
    .floatingContent {
      flex-direction: column;
      gap: 12px;
      width: 100%;
      align-items: stretch;
      text-align: center;
    }
    .floatingButtons {
      justify-content: center;
    }
  }
  ```

- [ ] **Step 2: Commit CSS Changes**

  Run: `git commit -am "style: add new layouts, top pagination, search input, and floating selection bar styles to process page"`

---

### Task 2: Modify React page (`page.tsx`)
**Files:**
- Modify: `frontend/src/app/(ai-mall)/process/page.tsx`

- [ ] **Step 1: Add state and parameter support for `searchQuery`**

  Locate state definitions (around lines 70-80). Add:
  ```typescript
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearchQuery, setActiveSearchQuery] = useState('');
  ```

  Inside `fetchProducts` callback (around lines 107-143), update params:
  ```typescript
  const params = new URLSearchParams({
    page: String(page),
    size: String(pageSize),
    wholesale_site_id: activeSiteId,
  });
  if (activeSearchQuery.trim()) {
    params.append('search', activeSearchQuery.trim());
  }
  ```
  Ensure `activeSearchQuery` is added to the callback dependencies:
  ```typescript
  }, [activeSiteId, page, statusFilter, completedOnly, sortMode, activeSearchQuery]);
  ```

  Also update the state resetting hook (around lines 149-152) to reset on wholesale site selection, but preserve on search:
  ```typescript
  useEffect(() => {
    setSelectedIds(new Set());
    setPage(1);
    setSearchQuery('');
    setActiveSearchQuery('');
  }, [activeSiteId]);

  useEffect(() => {
    setSelectedIds(new Set());
    setPage(1);
  }, [statusFilter, completedOnly, sortMode, activeSearchQuery]);
  ```

- [ ] **Step 2: Relocate the Main Action Button from Page Header to Table Toolbar**

  In `page.tsx` header (around lines 268-283):
  Remove `PillButton` from `styles.pageHeader` so it looks like:
  ```tsx
        <div className={styles.pageHeader}>
          <div>
            <h1 className={styles.title}>상품 가공</h1>
            <p className={styles.subtitle}>도매처를 선택한 뒤 DB에 저장된 상품 중 필요한 것만 골라 가공합니다.</p>
          </div>
        </div>
  ```

  In `tableToolbar` (around lines 309-322), place it inside a `.toolbarActions` div along with the checkbox:
  ```tsx
            <div className={styles.tableToolbar}>
              <div>
                <h2 className={styles.sectionTitle}>{activeSite.name} 상품 목록</h2>
                <p className={styles.sectionDesc}>총 {total.toLocaleString('ko-KR')}개 중 현재 페이지 {products.length}개 표시</p>
              </div>
              <div className={styles.toolbarActions}>
                <label className={styles.selectAllControl}>
                  <input
                    type="checkbox"
                    checked={isAllSelected}
                    onChange={(event) => togglePage(event.target.checked)}
                  />
                  현재 페이지 전체 선택
                </label>
                <PillButton
                  variant="primary"
                  onClick={handleStartSelectedProcessing}
                  disabled={selectedIds.size === 0 || isStarting}
                  type="button"
                >
                  {isStarting ? '가공 시작 중...' : `선택 상품 가공 (${selectedIds.size})`}
                </PillButton>
              </div>
            </div>
  ```

- [ ] **Step 3: Update `filterBar` to include the search input and top pagination**

  Replace the `<div className={styles.filterBar} ...>` block with:
  ```tsx
            <div className={styles.filterBar} aria-label="상품 필터">
              <div className={styles.filterLeft}>
                <div className={styles.searchGroup}>
                  <input
                    type="text"
                    className={styles.searchInput}
                    placeholder="상품명으로 검색..."
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        setActiveSearchQuery(searchQuery);
                      }
                    }}
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      className={styles.clearSearchButton}
                      onClick={() => {
                        setSearchQuery('');
                        setActiveSearchQuery('');
                      }}
                      title="검색어 지우기"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <label className={styles.filterGroup}>
                  <span>가공 상태</span>
                  <select
                    value={statusFilter}
                    onChange={(event) => {
                      setStatusFilter(event.target.value);
                      setCompletedOnly(event.target.value === 'completed');
                    }}
                  >
                    <option value="">전체 상태</option>
                    <option value="pending">대기</option>
                    <option value="processing">가공 중</option>
                    <option value="completed">완료</option>
                    <option value="failed">실패</option>
                  </select>
                </label>

                <label className={styles.filterGroup}>
                  <span>정렬</span>
                  <select
                    value={sortMode}
                    onChange={(event) => setSortMode(event.target.value)}
                  >
                    <option value="">기본순</option>
                    <option value="price_asc">낮은 도매가순</option>
                    <option value="price_desc">높은 도매가순</option>
                    <option value="option_count_desc">옵션 많은 순</option>
                  </select>
                </label>

                <label className={`${styles.filterToggle} ${completedOnly ? styles.activeFilterToggle : ''}`}>
                  <input
                    type="checkbox"
                    checked={completedOnly}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setCompletedOnly(checked);
                      setStatusFilter(checked ? 'completed' : '');
                    }}
                  />
                  가공 완료만 보기
                </label>
              </div>

              <div className={styles.filterRight}>
                <div className={styles.topPagination}>
                  <button
                    type="button"
                    onClick={() => setPage((value) => Math.max(1, value - 1))}
                    disabled={page <= 1 || isLoadingProducts}
                  >
                    이전
                  </button>
                  <span>{page} / {totalPages}</span>
                  <button
                    type="button"
                    onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                    disabled={page >= totalPages || isLoadingProducts}
                  >
                    다음
                  </button>
                </div>
              </div>
            </div>
  ```

- [ ] **Step 4: Implement Floating Selection Action Bar**

  Add the floating selection bar render block at the bottom of the JSX tree, right before the final closing div tag:
  ```tsx
        {/* Floating Action Bar */}
        {selectedIds.size > 0 && (
          <div className={styles.floatingActionBar}>
            <div className={styles.floatingContent}>
              <span className={styles.floatingText}>
                ✨ 현재 <strong>{selectedIds.size}</strong>개의 상품이 선택되었습니다.
              </span>
              <div className={styles.floatingButtons}>
                <PillButton
                  variant="primary"
                  onClick={handleStartSelectedProcessing}
                  disabled={isStarting}
                  type="button"
                >
                  {isStarting ? '가공 시작 중...' : '선택 상품 가공'}
                </PillButton>
                <button
                  type="button"
                  className={styles.floatingCancelButton}
                  onClick={() => setSelectedIds(new Set())}
                >
                  선택 취소
                </button>
              </div>
            </div>
          </div>
        )}
  ```

- [ ] **Step 5: Commit React page modifications**

  Run: `git commit -am "feat: implement product search, toolbar action relocation, top pagination, and floating action bar in process page"`

---

## Verification Plan

### Automated Verification
Since there is no frontend testing library configured (like Jest or Playwright) for this layout, verification will rely on static type checking and build compilation checks.

- [ ] Run typescript checks:
  `cd frontend && npm run build` (or `npx tsc --noEmit`) to verify there are no compilation errors.

### Manual Verification Instructions
1. Open the dev server: `npm run dev` in the frontend directory.
2. Navigate to **상품 가공** tab.
3. Choose a Supplier from the horizontal rail.
4. Verify that:
   - The top header has **no** "선택 상품 가공" button.
   - The table toolbar has a disabled "선택 상품 가공 (0)" button to the right of "현재 페이지 전체 선택".
   - The Filter Bar has a search input `상품명으로 검색...` with a search icon and an `✕` reset button.
   - The Filter Bar has compact pagination on the far right.
5. Select a few products using the checkboxes on the left:
   - Check if the table toolbar button updates its counter (e.g. `선택 상품 가공 (2)`).
   - Check if a beautiful floating bar slides up at the bottom showing `✨ 현재 2개의 상품이 선택되었습니다. [선택 상품 가공] [선택 취소]`.
6. Click `선택 취소` on the floating bar:
   - Check if all checkboxes are unchecked, the floating bar slides down/disappears, and the toolbar button is disabled again.
7. Type a search query in the search bar (e.g., a common term in the supplier's products) and press **Enter**:
   - Check if the product list updates and only displays matching products.
   - Check if the search input shows a clear button `✕`.
   - Click `✕` to clear and verify all products are restored.
8. Test the top-right pagination:
   - Click `다음` on the top pagination and verify the table changes page and bottom pagination stays fully synchronized.
