---
title: Seller Operations Console Layout for Wide Product Workflows
date: 2026-05-22
category: docs/solutions/design-patterns
module: frontend-ai-mall
problem_type: design_pattern
component: rails_view
severity: medium
applies_when:
  - "Admin screens need spreadsheet-like horizontal room for product operations"
  - "A fixed sidebar and centered max-width layout make dense tables feel cramped"
  - "Seller workflows require both friendly commerce navigation and high-density catalog controls"
tags: [frontend, layout, sidebar, product-table, seller-console, nextjs]
---

# Seller Operations Console Layout for Wide Product Workflows

## Context

The AI Mall UI originally followed a broad Apple-inspired dashboard direction with a fixed 260px sidebar, generous main padding, and centered content containers. That worked for overview pages, but it fought the product management workflow where sellers need an Excel-like surface for search, filters, category mapping, status badges, selection, and export actions.

Related prior docs:

- `docs/solutions/architecture-patterns/wholesale-management-smart-upsert.md` describes why upload templates and product management filters are central to seller workflows.
- `docs/solutions/database-issues/product-db-migration-2026-05-20.md` introduced the product DB page and custom Excel exports, which increased the importance of table density.

## Guidance

Use a "Seller Operations Console" shell for dense AI Mall workspaces:

- Keep the left navigation recognizable, but make it collapsible into a narrow rail.
- Default dense routes such as `/products`, `/upload`, and `/process` to the collapsed rail unless the user has set a sidebar preference.
- Reduce main padding on dense routes so the workspace, not chrome, owns the viewport.
- Avoid centered `max-width` wrappers on product tables. Let operational tables use the available width and rely on horizontal overflow only when the viewport is genuinely too narrow.
- Turn large dashboard stat cards into a compact metrics strip for table-first pages.
- Keep state color minimal and semantic: primary blue for actions, orange for price changes, red for stock/failure, green for complete states.

In this implementation, the shell change lives in:

- `frontend/src/app/(ai-mall)/layout.tsx`
- `frontend/src/app/(ai-mall)/ai-mall.module.css`
- `frontend/src/styles/tokens.css`

The product management density pass lives in:

- `frontend/src/app/(ai-mall)/products/page.tsx`
- `frontend/src/app/(ai-mall)/products/products.module.css`

## Why This Matters

Seller catalog work is not a marketing dashboard. A product operator scans rows, compares status, filters batches, exports selections, and checks change badges repeatedly. Wide, stable tables make that work faster and reduce visual fatigue. Collapsing navigation preserves orientation without permanently taxing horizontal space.

## When to Apply

- Use this pattern for table-heavy admin routes.
- Keep more generous spacing for home, settings, and other low-density pages.
- Apply visual polish through surface hierarchy and compact controls before adding decorative cards or large hero-like sections.

## Examples

Before:

- Sidebar always consumed 260px.
- Main content used `padding: 60px 80px`.
- Product page was centered with `max-width: 1200px`.
- Stats and filters used rounded card-heavy surfaces that reduced table priority.

After:

- Dense routes use a 64px collapsed navigation rail by default.
- Dense main content uses tighter padding.
- Product page removes the width cap and turns stats into a compact operations strip.
- Product rows, badges, filters, and pagination are tuned for scanning rather than presentation.

## Related

- `docs/superpowers/specs/2026-05-22-seller-operations-console-design.md`
- `docs/solutions/architecture-patterns/wholesale-management-smart-upsert.md`
- `docs/solutions/database-issues/product-db-migration-2026-05-20.md`
