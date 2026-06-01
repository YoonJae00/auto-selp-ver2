---
title: Wholesale Product Upload Visual Column Mapping with Excel Row Preview
date: 2026-05-31
category: docs/solutions/ui-bugs/
module: Wholesale Upload Management
problem_type: ui_bug
component: frontend_stimulus
symptoms:
  - "도매처의 다양한 엑셀 대장 원본 컬럼 구조로 인해 표준 시스템 필드와의 맵핑 작업 시 실제 원본 데이터를 대조해 볼 수 없어 맵핑 난이도가 매우 높음"
root_cause: missing_workflow_step
resolution_type: code_fix
severity: medium
tags:
  - wholesale
  - excel-upload
  - visual-mapper
  - row-preview
  - frontend
---

# Wholesale Product Upload Visual Column Mapping with Excel Row Preview

## Problem
In the wholesale upload settings page, sellers had to map dynamic columns of raw excel sheets (often with arbitrary, non-standard, or English header names like `prod_nm` or `prc_net`) to standard system fields. However, the visual mapper did not provide any view of the actual content within those columns. This made mapping extremely difficult and error-prone as sellers could not verify what type of data resided in each sheet column before selecting it.

In addition, the page name "도매처 & 업로드 설정" (Wholesale & Upload Settings) was ambiguous and did not clearly reflect its role as the entry point for importing raw supplier products.

## Symptoms
- Difficulty in matching obscure column names to standard fields (e.g., matching "판매상태" to `wholesale_status` or "제품번호" to `wholesale_product_id` without knowing if the values are IDs or text).
- Sellers choosing incorrect mappings, leading to subsequent parser errors or silent data mismatch in downstream processing.
- Ambiguity about the purpose of the `/upload` screen due to the generic header "도매처 & 업로드 설정".

## What Didn't Work
- Relying solely on the backend's "smart fallback auto-matching" logic. While the backend did match obvious column names, unique or custom columns from minor suppliers consistently failed matching, forcing sellers into manual guesswork without a content reference.
- Opening the raw Excel sheet in a separate window/Excel viewer on their local machine, which added operational friction and context switching.

## Solution
1. **Collapsible 5-Row Data Preview**:
   Introduced a highly polished, Apple-inspired collapsible accordion preview table (`previewTable`) directly above the Visual Column Mapper on the upload page (`frontend/src/app/(ai-mall)/upload/page.tsx`).
   - The table dynamically maps out all physical headers (`columns`) of the parsed spreadsheet and lists the top 5 item rows.
   - Designed to support horizontal scrolling (`overflow-x: auto`) for wide datasets, smooth toggle animations, and sticky headers (`position: sticky`).
   - Limits excessively long cell contents safely using CSS ellipses (`text-overflow: ellipsis`) and adds tooltips to present complete fields on hover.

2. **Refined Component Robustness**:
   - Integrated unique composite keying in React (`key={`${col}-${idx}`}`) to eliminate warnings when duplicate column headers exist.
   - Implemented loose null/undefined safety validations (`row[col] != null`) in the cell renderer to prevent explicit null entries from rendering as `"null"` strings.

3. **Global Screen Renaming**:
   - Changed global layout navigation paths in `layout.tsx` from "도매처 & 업로드 설정" to **"도매처 상품 업로드"**.
   - Updated primary `<h1>` headers inside `upload/page.tsx` accordingly.

## Why This Works
Providing an immediate, read-only preview of the exact raw excel structure right above the dropdown selections closes the visual loop. Sellers can easily look up the top 5 values under any column to instantly verify its data format (e.g., verifying if a column has image URLs, prices, or serial codes) and select the correct system mapping field directly. 

Consistent page titles clearly explain the workflow step ("Wholesale Product Upload"), improving navigational clarity.

## Prevention
- **UI Design Rule**: Always couple dynamic or custom-configurable schema mapping screens with immediate visual previews of the source datasets.
- **Robust Client Mapping**: When mapping tabular spreadsheets of foreign schemas inside custom map configurations, always protect the frontend with composite uniqueness keys and loose null-safeguards to prevent runtime crashes when custom sheets contain invalid cells.

## Related Issues
- GitHub Issue #46 (Wholesale Management & Smart Upsert integration)
- GitHub Issue #45 (Playauto Column Mapper high-fidelity configurations)
