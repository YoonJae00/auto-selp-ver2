# Wholesale Product Upload Rename & Excel Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename "도매처 & 업로드 설정" to "도매처 상품 업로드" across the layout and page titles, and implement a collapsible 5-row Excel data preview table on the upload screen to simplify visual column mapping.

**Architecture:** Frontend enhancement within Next.js components. Introducing `isPreviewOpen` state to control the visibility of a tabular visual layout representing rows fetched during spreadsheet parses, along with custom CSS styles mapping standard horizontal scrolls and cell limits.

**Tech Stack:** Next.js (App Router), TypeScript, Vanilla CSS (CSS Modules).

---

## Technical File Map
- **Modify:** `frontend/src/app/(ai-mall)/layout.tsx` (Updates sidebar label)
- **Modify:** `frontend/src/app/(ai-mall)/upload/page.tsx` (Updates header title, introduces toggle state, displays 5-row preview)
- **Modify:** `frontend/src/app/(ai-mall)/upload/upload.module.css` (Adds styles for the collapsible container and scrolled preview grid)

---

## Tasks

### Task 1: Rename Sidebar Label
Rename the main navigation label in the App Layout to "도매처 상품 업로드".

**Files:**
- Modify: `frontend/src/app/(ai-mall)/layout.tsx`

- [ ] **Step 1: Modify layout.tsx**

Replace line 14 matching `도매처 & 업로드 설정` with `도매처 상품 업로드`.

Code change:
```diff
-  { href: '/upload', label: '도매처 & 업로드 설정', railLabel: 'UP' },
+  { href: '/upload', label: '도매처 상품 업로드', railLabel: 'UP' },
```

- [ ] **Step 2: Verify Sidebar Title change**
Check the sidebar to ensure the path label has changed to "도매처 상품 업로드".

- [ ] **Step 3: Commit the layout change**
```bash
git add frontend/src/app/\(ai-mall\)/layout.tsx
git commit -m "chore: rename sidebar upload settings to wholesale product upload"
```


### Task 2: Rename Page Header & Setup Toggle State
Modify the page header of the upload component and initialize state variables for the collapsible preview component.

**Files:**
- Modify: `frontend/src/app/(ai-mall)/upload/page.tsx`

- [ ] **Step 1: Rename Main Title in page.tsx**
Find `<h1 className={styles.title}>도매처 & 업로드 설정</h1>` (around L256) and update to `도매처 상품 업로드`.

Code change:
```diff
-        <h1 className={styles.title}>도매처 & 업로드 설정</h1>
+        <h1 className={styles.title}>도매처 상품 업로드</h1>
```

- [ ] **Step 2: Declare Toggle State in UploadPage**
Locate existing state hooks (around L71-73) and insert `isPreviewOpen` initialized to `true`.

Code change:
```typescript
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(true); // Added for accordion toggle
```

- [ ] **Step 3: Commit the base upload page modifications**
```bash
git add frontend/src/app/\(ai-mall\)/upload/page.tsx
git commit -m "feat: rename page header and add isPreviewOpen state in upload page"
```


### Task 3: Implement Collapsible Excel Data Preview Component
Embed the interactive accordion top-header and tabular spreadsheet preview rendering logic in `/upload/page.tsx`.

**Files:**
- Modify: `frontend/src/app/(ai-mall)/upload/page.tsx`

- [ ] **Step 1: Embed Table Preview Code**
Locate `{uploadData && (` inside `page.tsx` (around L341) and place the preview block above the "Visual Column Mapper" headers.

Code change:
```tsx
          {/* Visual Column Mapper */}
          {uploadData && (
            <div className={styles.mappingWrapper}>
              {/* Excel Data Preview Section */}
              <div className={styles.previewWrapper}>
                <button 
                  type="button" 
                  className={styles.accordionHeader} 
                  onClick={() => setIsPreviewOpen(!isPreviewOpen)}
                >
                  <span className={styles.accordionTitle}>
                    📊 업로드 파일 데이터 미리보기 (상위 5개 행)
                  </span>
                  <span className={styles.accordionIcon}>
                    {isPreviewOpen ? '🔼 접기' : '🔽 펼치기'}
                  </span>
                </button>
                
                {isPreviewOpen && (
                  <div className={styles.previewTableContainer}>
                    <table className={styles.previewTable}>
                      <thead>
                        <tr>
                          <th className={styles.rowNumber}>No.</th>
                          {uploadData.columns.map((col) => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {uploadData.preview.map((row, idx) => (
                          <tr key={idx}>
                            <td className={styles.rowNumber}>{idx + 1}</td>
                            {uploadData.columns.map((col) => (
                              <td key={col} title={row[col] !== undefined ? String(row[col]) : ''}>
                                {row[col] !== undefined ? String(row[col]) : ''}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className={styles.sectionHeader}>
                <h2>Visual Column Mapper (컬럼 매핑 대입)</h2>
                <p>도매처 엑셀 열 항목과 시스템의 표준 저장 필드를 시각적으로 연결합니다. 처음 한번만 설정하면 저장되어 계속 재사용 가능합니다.</p>
              </div>
```

- [ ] **Step 2: Commit the preview rendering component**
```bash
git add frontend/src/app/\(ai-mall\)/upload/page.tsx
git commit -m "feat: implement 5-row excel table preview component on upload page"
```


### Task 4: Add Premium Collapsible CSS Styling
Integrate dynamic grid spacing, transition hover effects, smooth horizontal scrolling, and neat character ellipses rules for Excel rows into the style sheet.

**Files:**
- Modify: `frontend/src/app/(ai-mall)/upload/upload.module.css`

- [ ] **Step 1: Append styles to upload.module.css**
Append the entire CSS rules outlined in the design spec to the bottom of the style file.

Code content to append:
```css

/* --- Preview Accordion UI Styles --- */
.previewWrapper {
  margin-top: 32px;
  background: var(--canvas);
  border: 1px solid var(--hairline);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.01);
}

.accordionHeader {
  width: 100%;
  padding: 18px 24px;
  background: var(--canvas-parchment, rgba(0, 0, 0, 0.02));
  border: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  outline: none;
  transition: background 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  color: var(--ink);
}

.accordionHeader:hover {
  background: rgba(0, 0, 0, 0.04);
}

.accordionTitle {
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.accordionIcon {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-muted-48);
  background: var(--canvas);
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid var(--hairline);
  transition: all 0.2s;
}

.previewTableContainer {
  padding: 0;
  overflow-x: auto;
  border-top: 1px solid var(--hairline);
  max-width: 100%;
}

.previewTable {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  text-align: left;
}

.previewTable th {
  background: var(--canvas);
  color: var(--ink-muted-80);
  font-weight: 600;
  padding: 14px 16px;
  border-bottom: 1px solid var(--hairline);
  white-space: nowrap;
  position: sticky;
  top: 0;
}

.previewTable td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--hairline);
  color: var(--ink);
  white-space: nowrap;
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.previewTable tr:last-child td {
  border-bottom: none;
}

.previewTable tr:hover {
  background: rgba(var(--primary-rgb), 0.01);
}

.rowNumber {
  font-weight: 600;
  color: var(--primary);
  text-align: center;
  width: 60px;
  background: var(--canvas-parchment, rgba(0, 0, 0, 0.01));
}
```

- [ ] **Step 2: Commit the CSS style sheet additions**
```bash
git add frontend/src/app/\(ai-mall\)/upload/upload.module.css
git commit -m "style: add responsive layout and apple aesthetics styles for excel preview"
```


### Task 5: End-to-End System Validation
Ensure compilation resolves correctly and all interactive functions operate as planned.

**Files:**
- Test: E2E manual verify through standard browser flows.

- [ ] **Step 1: Verify Dev Server status**
Ensure Next.js executes cleanly without compiling anomalies.

- [ ] **Step 2: Test File Upload & Preview Rendering**
1. Select any wholesale site card (e.g. 온채널, 도매꾹).
2. Upload a sample excel file.
3. Validate that:
   - "📊 업로드 파일 데이터 미리보기 (상위 5개 행)" accordion pops up properly.
   - Expanding it shows exactly 5 rows of data mapping each individual excel header correctly.
   - Long details exhibit '...' ellipsis.
   - Toggle button folds and unfolds nicely.
   - Sidebar item and main title correctly reflect "도매처 상품 업로드".
4. Modify dropdown visual mapper select boxes and verify template saves correctly.
5. Verify DB saving continues to complete successfully.
