# Seller Operations Console Design

## Goal

Upgrade the AI Mall frontend from a basic Apple-inspired dashboard into a seller operations console that preserves friendly commerce-admin ergonomics while giving product tables the horizontal room and density of an Excel-like workflow.

## Visual Direction

The interface should sit between Shopify Admin and a lightweight professional spreadsheet tool: calm, bright, operational, and information-dense. Navigation should stay recognizable, but the primary workspace must prioritize search, filters, selection, export, sync status, and wide product tables.

## Layout

- Use a collapsible left navigation rail.
- Default the rail to collapsed on workspace-heavy pages: `/products`, `/upload`, and `/process`.
- Keep broader pages such as `/home` and `/settings` comfortable with the expanded sidebar by default.
- Shrink the main workspace padding on dense pages and allow product surfaces to use the full available width.

## Product Management

- Remove the narrow centered layout from the product page.
- Convert stats from large card blocks into a compact operations strip.
- Keep filters in a single toolbar-like surface above the table.
- Tighten table row spacing while preserving readable product names, keyword badges, category mapping, status, and timestamps.

## Interaction

- Provide a visible sidebar toggle button with accessible labels.
- Persist the user's collapsed sidebar preference in local storage.
- Use smooth width transitions, clear hover states, and focus-visible outlines.

## Scope

This first pass changes the global AI Mall layout and the product management surface. Upload and process pages benefit from the wider shell immediately, but their internal visual redesign can happen in a later pass.
