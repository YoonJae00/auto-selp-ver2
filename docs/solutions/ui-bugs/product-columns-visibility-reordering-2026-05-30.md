---
title: "Product Columns Visibility and Native Drag-and-Drop Reordering"
date: "2026-05-30"
category: "ui-bugs"
module: "Product Management Catalog Grid"
problem_type: "ui_bug"
component: "tooling"
symptoms:
  - "Product columns are hardcoded, preventing user customization"
  - "Hidden metadata columns occupy excessive table real estate"
root_cause: "incomplete_setup"
resolution_type: "code_fix"
severity: "medium"
tags:
  - "react"
  - "drag-and-drop"
  - "localstorage"
  - "column-visibility"
  - "ssr-hydration"
---

# Product Columns Visibility and Native Drag-and-Drop Reordering

## Problem
In the product catalog grid, columns were static and hardcoded. As the schema grew to 17 fields, rendering all of them concurrently severely degraded usability. We needed a customizable columns popover and dynamic drag-and-drop reordering that persists in `localStorage` without triggering SSR hydration mismatches.

## Symptoms
- Extreme horizontal scrolling inside the products management dashboard.
- Inability for users to toggle visibility of non-essential metadata columns like brand, origin, wholesale status, and wholesale registered date.
- Lack of customizable column ordering.

## What Didn't Work
- Reading configurations from `localStorage` directly in `useState` initialization: triggered server-client mismatches (hydration errors) since server initial HTML differs from the hydrated client state.

## Solution
Implemented:
1. **Dynamic column state registry and order**: Constants defining `COLUMNS_REGISTRY`, `DEFAULT_ORDER`, and `DEFAULT_VISIBILITY` are configured outside the React lifecycle.
2. **Local Storage Synchronization**: Used a `useEffect` running strictly on client mount to load preferences from `localStorage` under `autoselp_product_columns_config`, merging new schemas seamlessly.
3. **Dynamic Headers & Rows**: Mapped `<thead>` and `<tbody>` cells over `columnOrder` and `columnVisibility` enlisting a solid switch-case rendering block for all 17 fields.
4. **HTML5 Drag-and-Drop**: Leveraged `draggable`, `onDragStart`, `onDragOver`, `onDrop`, and `onDragEnd` applying gorgeous Apple-inspired vertical line drop indicator borders based on `dragOverColKey` and `dragDirection`.
5. **Dismissible Gear Popover**: Mounted a `PillButton` popover at the end of the `filterBar` with an outside-click handler.

## Why This Works
- Client-side-only settings loaded in `useEffect` fully side-step Next.js hydration issues.
- Native drag-and-drop handles performance extremely well compared to heavy libraries.
- Standard class overlay (`.dragIndicatorLeft` and `.dragIndicatorRight`) handles borders inside absolute space, conforming to modern Apple aesthetic design principles.

## Prevention
- Standardize grid tables to map cells dynamically rather than hardcoding.
- Always use a client-side `useEffect` mount hook before reading `localStorage` or `window` variables in Next.js/SSR environments.

## Related Issues
- Phase 3 TODO: Product Columns Visibility & Reordering
