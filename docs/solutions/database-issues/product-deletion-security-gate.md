---
title: Multi-Tenant Data Protection and Safe Cascading Product Deletion
date: 2026-05-30
category: docs/solutions/database-issues
module: products
problem_type: security_issue
component: authentication
symptoms:
  - "Unauthorized deletion of other users' products via API endpoints"
  - "Accidental deletion of active, market-synced products without user consent"
  - "Orphaned mapping records and database integrity violations due to missing cascade assertions"
root_cause: missing_permission
resolution_type: code_fix
severity: critical
tags:
  - "multi-tenancy"
  - "data-isolation"
  - "cascade-delete"
  - "dependency-override"
  - "pytest-mocking"
  - "apple-styling"
---

# Multi-Tenant Data Protection and Safe Cascading Product Deletion

## Problem
In multi-tenant SaaS environments, ensuring strict data isolation is critical to prevent malicious or accidental unauthorized cross-tenant data mutation. Prior to this implementation, the system lacked explicit user ownership checks on product deletion routes, presenting a security vulnerability where a tenant could delete another tenant's imported products by predicting or brute-forcing UUIDs. Additionally, deleting products that were already synchronized to external marketplaces (like Naver SmartStore or Coupang) without warnings could result in orphaned external listings that are no longer manageable.

## Symptoms
- **Symptom 1**: A tenant sends a POST request to `/products/delete` with `product_ids` belonging to a different tenant, and the database successfully deletes the records, causing unauthorized data loss.
- **Symptom 2**: Products that are marked as `"synced"` in `ProductPlatformMapping` are silently deleted, leaving stale, active listings on external channels with no way to synchronize price or stock updates.
- **Symptom 3**: When deleting a product, related database records (e.g. `ProductPlatformMapping`) are left orphaned or trigger database foreign key constraint violations if cascade delete rules are not properly validated.

## What Didn't Work
- **Attempt 1: Deletion without Owner Identification Gates**: Early attempts to handle bulk deletion relied entirely on matching the incoming list of IDs against the database without scoping the query by the authenticated user's ID. This successfully deleted the requested products but failed security reviews and automated multi-tenant safety assertions because it did not check `Product.user_id == current_user["id"]`.
- **Attempt 2: Missing Cascade-Deletion Assertions**: Relying purely on ORM-level relationships for cascades without writing integration tests that explicitly queried secondary tables (like `ProductPlatformMapping`) led to fragile code. Early tests passed because the primary entity was removed, but subsequent database integrity sweeps revealed orphaned child rows since the tests did not assert `len(mappings) == 0`.
- **Attempt 3: Synchronous Modal Transition without Blur/Aesthetic Polish**: Initial UI prototypes for the deletion modal used standard browser dialog alerts or generic rectangular cards. These felt jarring to the user, lacked clean ARIA hooks for accessibility, and didn't support proper "Escape" key listeners to safely dismiss the modal without executing the deletion process.

## Solution

### 1. Backend Security and Authorization Gate
The FastAPI endpoint `/products/delete` was secured by introducing `Depends(get_current_user)` to authenticate the request, and a strict ownership clause `Product.user_id == current_user["id"]` was added to all target identification queries:

```python
# services/processor/main.py
@app.post("/products/delete", response_model=ProductDeleteResponse)
async def delete_products(
    req: ProductDeleteRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not req.product_ids and not req.wholesale_site_id:
        return ProductDeleteResponse(
            success=False,
            deleted_count=0,
            message="삭제 대상(product_ids 또는 wholesale_site_id)을 입력해주세요."
        )

    # 1. Resolve product targets belonging ONLY to current user
    target_stmt = select(Product.id).where(Product.user_id == current_user["id"])
    if req.product_ids:
        target_stmt = target_stmt.where(Product.id.in_(req.product_ids))
    elif req.wholesale_site_id:
        target_stmt = target_stmt.where(Product.wholesale_site_id == req.wholesale_site_id)

    res = await db.execute(target_stmt)
    target_ids = [row[0] for row in res.all()]

    if not target_ids:
        return ProductDeleteResponse(
            success=True,
            deleted_count=0,
            message="삭제할 상품이 존재하지 않습니다."
        )

    # 2. Check for synced platform mappings
    sync_stmt = select(ProductPlatformMapping.product_id).where(
        and_(
            ProductPlatformMapping.product_id.in_(target_ids),
            ProductPlatformMapping.sync_status == "synced"
        )
    )
    sync_res = await db.execute(sync_stmt)
    synced_ids = [row[0] for row in sync_res.all()]
    synced_count = len(synced_ids)

    # 3. Warnings intercept if force is False
    if synced_count > 0 and not req.force:
        return ProductDeleteResponse(
            success=False,
            deleted_count=0,
            warning_synced_count=synced_count,
            message="이미 마켓에 연동(동기화) 완료된 상품이 포함되어 있어 삭제를 진행하지 않았습니다."
        )

    # 4. Perform cascade deletion (Postgres cascade configured in relationships)
    del_stmt = delete(Product).where(
        and_(
            Product.id.in_(target_ids),
            Product.user_id == current_user["id"]
        )
    )
    res_del = await db.execute(del_stmt)
    await db.commit()

    deleted_count = res_del.rowcount
    return ProductDeleteResponse(
        success=True,
        deleted_count=deleted_count,
        message=f"성공적으로 {deleted_count}개의 상품이 삭제되었습니다."
    )
```

### 2. Premium ARIA-Compliant Frosted-Glass UI Modal
The Next.js/React frontend features a premium, Apple-inspired modal dialog (`DeleteConfirmModal.tsx`) with dynamic warnings for synchronized products, fully keyboard-accessible (Escape key triggers), and styled with frosted-glass filters and micro-animations:

```tsx
// frontend/src/components/UI/DeleteConfirmModal/DeleteConfirmModal.tsx
'use client';

import React, { useEffect } from 'react';
import styles from './DeleteConfirmModal.module.css';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (force: boolean) => void;
  count: number;
  warningSyncedCount: number;
  isDeleting: boolean;
  error: string | null;
}

export default function DeleteConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  count,
  warningSyncedCount,
  isDeleting,
  error
}: DeleteConfirmModalProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isDeleting) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, isDeleting, onClose]);

  if (!isOpen) return null;

  const hasWarnings = warningSyncedCount > 0;

  return (
    <div className={styles.overlay} onClick={!isDeleting ? onClose : undefined}>
      <div
        className={styles.modalCard}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-modal-title"
        aria-describedby="delete-modal-description"
      >
        <div className={styles.iconContainer}>
          {hasWarnings ? (
            <div className={`${styles.icon} ${styles.alertIcon}`}>⚠️</div>
          ) : (
            <div className={`${styles.icon} ${styles.trashIcon}`}>🗑️</div>
          )}
        </div>

        <h2 className={styles.title} id="delete-modal-title">
          {hasWarnings ? '경고: 마켓 연동 상품 포함' : '상품 삭제'}
        </h2>

        <div className={styles.content} id="delete-modal-description">
          {hasWarnings ? (
            <p className={styles.warningMessage}>
              삭제 대상 중 이미 스마트스토어/쿠팡에 등록(동기화) 완료된 상품{' '}
              <strong className={styles.highlight}>{warningSyncedCount}개</strong>가 포함되어 있습니다!
              <br />
              <br />
              DB에서 제거 시 향후 가격/재고 스마트 갱신 및 관리가 완전히 불가능해집니다.
              정말로 연동 데이터를 포함해 모두 강제로 삭제하시겠습니까?
            </p>
          ) : (
            <p className={styles.normalMessage}>
              선택한 <strong className={styles.highlight}>{count}개</strong>의 상품을 데이터베이스에서 영구 삭제하시겠습니까?
              이 작업은 되돌릴 수 없습니다.
            </p>
          )}
        </div>

        {error && <div className={styles.errorAlert}>{error}</div>}

        <div className={styles.actions}>
          <button
            className={styles.cancelBtn}
            onClick={onClose}
            disabled={isDeleting}
          >
            {hasWarnings ? '아니오 (취소)' : '취소'}
          </button>
          <button
            className={hasWarnings ? styles.forceBtn : styles.dangerBtn}
            onClick={() => onConfirm(hasWarnings)}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <span className={styles.spinner}></span>
            ) : hasWarnings ? (
              '예, 강제로 삭제'
            ) : (
              '삭제하기'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 3. Premium Styling using CSS Modules and Backdrop-Filter:
```css
/* frontend/src/components/UI/DeleteConfirmModal/DeleteConfirmModal.module.css */
.overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.25s ease-out;
}

.modalCard {
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 18px;
  width: 90%;
  max-width: 440px;
  padding: 28px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
  text-align: center;
  transform: scale(0.95);
  animation: popUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.alertIcon {
  background: rgba(255, 59, 48, 0.08);
  animation: pulse 2s infinite;
}
```

## Why This Works
1. **Multi-Tenant Isolation at SQL Level**: Scoping the primary target selection by `Product.user_id == current_user["id"]` ensures that a tenant can never delete or even query other tenants' products, regardless of the input array. Even if an attacker injects foreign `product_ids`, they are automatically filtered out during the target resolution phase.
2. **Cascade Cascading**: The deletion executes a bulk operation `delete(Product).where(Product.id.in_(target_ids))` which is linked with ForeignKey constraints containing `ondelete="CASCADE"` at the PostgreSQL level. This guarantees that relational child data in tables such as `ProductPlatformMapping` are instantly and atomically expunged, preventing database drift and foreign key orphans.
3. **Optimistic Warnings & UX Friction**: By executing a cheap `select` on mapping tables first, the API returns a precise count of synchronized products instead of executing an irrevocable operation. The user is presented with intentional friction in the form of a dynamic secondary confirmation modal with visual alerts (pulsing yellow warning icon) which ensures safe operational behavior.

## Prevention
1. **Pytest Dependency Overrides**: Securely test authenticated state by overriding the FastAPI dependencies during the test setup:
   ```python
   @pytest.fixture(autouse=True)
   def mock_auth():
       from main import get_current_user
       app.dependency_overrides[get_current_user] = lambda: {"id": TEST_USER_ID, "username": "test_user", "is_admin": False}
       yield
       app.dependency_overrides.clear()
   ```
2. **Strict Multi-Tenant API Assertions**: Write rigorous isolation tests that explicitly insert records under a different user and assert that deletion requests return a `success` with `0` deleted records:
   ```python
   # Verify the product is still safe and NOT deleted in the database
   async with test_session() as session:
       prod_stmt = select(Product).where(Product.id == prod_id)
       prod_res = await session.execute(prod_stmt)
       prod_in_db = prod_res.scalar_one_or_none()
       assert prod_in_db is not None
   ```
3. **Database Cascade Assertions**: Always query child tables (like `ProductPlatformMapping`) after a parent record deletion test to verify that cascades occurred at the database layer rather than relying on manual cleanup.
4. **ARIA Compliance Checks**: Mandate standard ARIA dialog attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `aria-describedby`) and keyboard events (Escape keys) on all visual overlays to preserve standard-compliant access for screen readers and keyboard-only users.

## Related Issues
- [Product Column Reordering](file:///Users/yoonjae/Desktop/auto-selp-ver2/docs/superpowers/plans/2026-05-27-marketplace-draft-foundation.md)
- [Product Deletion Specifications](file:///Users/yoonjae/Desktop/auto-selp-ver2/docs/superpowers/specs/2026-05-30-product-deletion-design.md)
