---
title: Marketplace Review UI and Submission Foundation
date: 2026-05-28
category: docs/solutions/design-patterns
module: marketplace-listing
problem_type: design_pattern
component: marketplace-ui
severity: medium
applies_when:
  - "Marketplace draft generation exists but sellers still need a review inbox before registration"
  - "Smart Store and Coupang drafts share lifecycle behavior but require channel-specific details"
  - "External submission is not ready, but the product needs submission jobs and attempts as a stable integration point"
tags: [marketplace, smartstore, coupang, nextjs, fastapi, submission, review-ui]
related_issues:
  - "https://github.com/YoonJae00/auto-selp-ver2/issues/52"
---

# Marketplace Review UI and Submission Foundation

## Context

The marketplace backend already generated reviewable Smart Store and Coupang listing drafts from processor snapshots, but the seller-facing workflow was still missing. The product needed a unified registration inbox, marketplace-specific account settings, draft override controls, and a submission boundary that could later call external marketplace APIs.

The first backend phase intentionally stopped before frontend screens and real marketplace submission calls. That made the next slice broader than a pure frontend task: the UI needed `PATCH /drafts/{draft_id}` for overrides and ready transitions, plus `POST /submissions` and submission attempt storage so selected drafts can move into a submission workflow without inventing the persistence model later.

## Guidance

Use `/marketplaces` as one unified registration inbox rather than separate disconnected Smart Store and Coupang pages.

The page should:

- Filter drafts by marketplace and lifecycle status.
- Show a dense summary table with marketplace, title, category, price, validation status, submission state, and update time.
- Load a selected draft into a detail panel for seller review.
- Surface shared editable draft fields such as title, sale price, category, origin, images, detail content, and options.
- Reserve channel-specific sections for Smart Store title/pricing outputs and Coupang SKU/content/attribute outputs.
- Allow sellers to save an `override_patch` and mark a draft `ready`.
- Submit selected drafts by partitioning them by `market_account_id` and `market_code`.

Use `/marketplaces/accounts` for account-scoped settings:

- Render Smart Store and Coupang as marketplace-specific tabs.
- Create connected accounts with encrypted credentials.
- Read and update account-specific settings JSON, including pricing policy under `generation_rules.pricingPolicy`.
- Keep shipping, claim, certification, and listing defaults in account settings rather than repeating them as per-product edit fields.

On the backend, introduce submission tables before external clients:

- `market_submission_jobs` tracks a batch for one account and marketplace.
- `market_submission_attempts` records each draft's exact effective payload and future response/error metadata.
- `POST /submissions` rejects blocked drafts before any external call can happen.
- Valid selected drafts move to `submitting` and receive queued attempts.

This creates a durable seam for a later marketplace-worker implementation without changing the UI contract again.

## Why This Matters

Registration workflows are high-risk because sellers need to know exactly what will be sent to each marketplace. If the UI jumps directly from generated data to an external call, there is no place to review validation messages, adjust channel-specific values, or audit what was submitted.

Separating review, ready transition, submission job creation, and external API execution keeps the workflow observable:

- Draft generation remains idempotent and non-fatal to product processing.
- Seller overrides are stored separately from generated payloads.
- Submission attempts preserve the exact request payload for support and retry decisions.
- Smart Store and Coupang can evolve independently behind the same lifecycle model.

## When to Apply

Apply this pattern when adding a marketplace or channel integration that has different payload rules but shares the same seller review lifecycle.

Do not use it for one-off exports where no submission lifecycle, retry, or audit history is needed.

## Current Implementation

Frontend:

- `frontend/src/app/(ai-mall)/marketplaces/page.tsx`
- `frontend/src/app/(ai-mall)/marketplaces/marketplaces.module.css`
- `frontend/src/app/(ai-mall)/marketplaces/accounts/page.tsx`
- `frontend/src/app/(ai-mall)/marketplaces/accounts/accounts.module.css`
- `frontend/src/app/(ai-mall)/layout.tsx`
- `frontend/src/lib/api.ts`

Backend:

- `services/marketplace/models.py`
- `services/marketplace/schemas.py`
- `services/marketplace/main.py`
- `services/marketplace/tests/test_submission_api.py`
- `services/marketplace/tests/test_drafts_api.py`
- `services/marketplace/tests/test_models.py`

Verification:

- `PYTHONPATH=. pytest tests -q` in `services/marketplace`
- `npm run lint` in `frontend`
- `npm run build` in `frontend`

## Follow-Up

Track the external submission layer in GitHub issue #52:

- Smart Store external submission client.
- Coupang external submission client.
- marketplace-worker execution for queued submission jobs.
- Remote result reconciliation and retry behavior.
- UI submission history, failure details, and retry controls.

## Related

- `docs/superpowers/specs/2026-05-27-marketplace-listing-service-design.md`
- `docs/superpowers/plans/2026-05-27-marketplace-draft-foundation.md`
- `docs/solutions/design-patterns/seller-operations-console-layout-2026-05-22.md`
- `https://github.com/YoonJae00/auto-selp-ver2/issues/52`
