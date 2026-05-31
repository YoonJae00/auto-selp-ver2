# Design Spec: Wholesale Product Upload Screen Rename and Excel Data Preview

This specification outlines the updates for changing the name of "도매처 & 업로드 설정" (Wholesale & Upload Settings) to "도매처 상품 업로드" (Wholesale Product Upload) and introducing a collapsible top-level table component to preview the first 5 rows of uploaded Excel files. This enhancement directly addresses the user's difficulty with mapping complex supplier Excel column formats.

---

## 1. Objectives & Requirements

- **Page Rename**:
  - Rename the navigation label in the sidebar layout from "도매처 & 업로드 설정" to "도매처 상품 업로드".
  - Rename the main page title (`h1`) inside `/upload` from "도매처 & 업로드 설정" to "도매처 상품 업로드".
- **Collapsible Data Preview (5 rows)**:
  - Add a collapsible accordion component above the "Visual Column Mapper" section on the `/upload` page.
  - The component is only visible when an Excel file has been successfully uploaded (i.e. `uploadData` exists).
  - It displays the first 5 rows of the Excel sheet returned from the server's `/api/processor/upload` response (`uploadData.preview`).
  - Columns within the table reflect the exact physical headers of the uploaded Excel (`uploadData.columns`), enabling users to compare column names with actual cell contents.
  - Style with a horizontal scroll constraint (`overflow-x: auto`), subtle hover states, text ellipses for long fields, and a clean toggle button for opening/closing.

---

## 2. Technical Scope

### A. Frontend Changes

1. **`frontend/src/app/(ai-mall)/layout.tsx`**
   - Update navigation path item label:
     ```diff
     -  { href: '/upload', label: '도매처 & 업로드 설정', railLabel: 'UP' },
     +  { href: '/upload', label: '도매처 상품 업로드', railLabel: 'UP' },
     ```

2. **`frontend/src/app/(ai-mall)/upload/page.tsx`**
   - Update title:
     ```diff
     -  <h1 className={styles.title}>도매처 & 업로드 설정</h1>
     +  <h1 className={styles.title}>도매처 상품 업로드</h1>
     ```
   - Introduce state variable `isPreviewOpen` (default: `true`):
     ```typescript
     const [isPreviewOpen, setIsPreviewOpen] = useState(true);
     ```
   - Render the collapsible preview component:
     - Place it directly inside `{uploadData && ( ... )}` before the Visual Column Mapper section.
     - Show headers (`uploadData.columns`) and body data rows (`uploadData.preview`).
     - Render an index column (e.g. `No. 1` to `No. 5`) on the far left.

3. **`frontend/src/app/(ai-mall)/upload/upload.module.css`**
   - Add styling rules for `.previewWrapper`, `.accordionHeader`, `.accordionTitle`, `.accordionIcon`, `.previewTableContainer`, `.previewTable`, and `.rowNumber`.
   - Maintain modern, high-fidelity Apple-style guidelines: premium shadows, subtle gradients, border-radius, hairline borders, and fluid hover states.
   - Enforce `text-overflow: ellipsis` for long strings inside data cells to preserve UI layout and compact height.

### B. Backend Compliance

- The FastAPI backend endpoint `/api/processor/upload` already returns the first 5 rows of the spreadsheet inside the `preview` key:
  ```python
  df = pd.read_excel(file_path, nrows=5)
  df = df.fillna("")
  columns = df.columns.tolist()
  preview = df.to_dict(orient="records")
  return {
      "file_id": file_id,
      "filename": file.filename,
      "columns": columns,
      "preview": preview
  }
  ```
- Thus, **no backend modifications are required**. This update is purely visual/frontend enhancement.

---

## 3. UI/UX Detail Spec

### Accordion Top-Header
- **Style**: Lightweight banner using variable `--canvas-parchment` or slightly tinted gray background, standard border-radius, flex row spacing.
- **Labels**: "📊 업로드 파일 데이터 미리보기 (상위 5개 행)"
- **Interactive State**: Clicking anywhere on the banner toggles `isPreviewOpen`. The indicator dynamically changes between `🔼 접기` and `🔽 펼치기`.

### Preview Table Grid
- **Columns**: Dynamic mapping of `uploadData.columns`.
- **Rows**: Dynamic mapping of `uploadData.preview` (up to 5 items).
- **Cell Styling**:
  - `white-space: nowrap` + `max-width: 250px` + `overflow: hidden` + `text-overflow: ellipsis` ensures neat wrapping.
  - Sticky table headers stay at the top.
  - Horizontal scrollbar is visible only when required and uses a thin, elegant track.

---

## 4. Verification & Criteria
- Navigation and titles display "도매처 상품 업로드" instead of "도매처 & 업로드 설정".
- Selecting any wholesale site and uploading a sample Excel file correctly pops up the Collapsible Preview block.
- Expanding the block shows exact tabular representation of the top 5 Excel items.
- Shrinking it hides the table block without resetting the user's current column mapping values.
- Saving templates and importing products function flawlessly alongside the preview window.
