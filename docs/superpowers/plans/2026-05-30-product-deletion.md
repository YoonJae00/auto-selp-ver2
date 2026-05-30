# Product Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a secure, multi-mode product deletion feature (by selected checkboxes and by wholesale site) in the Product Management tab with a warning gate for products synced to marketplaces.

**Architecture:** A unified REST API endpoint `/products/delete` handles validation and cascades deletion, while the Next.js React frontend employs an Apple-inspired glassmorphism alert modal to warn the user before completing the action.

**Tech Stack:** FastAPI (Python), SQLAlchemy, Next.js (TypeScript), Vanilla CSS modules.

---

## File Structure & Decomposition
1. **`services/processor/schemas.py`**: Add request/response Pydantic models for product deletion.
2. **`services/processor/tests/test_delete_api.py`**: Add comprehensive async integration tests for the deletion API endpoint, testing safe rejection and forced cascade deletion.
3. **`services/processor/main.py`**: Implement the `POST /products/delete` endpoint with the safety warning validation gate.
4. **`frontend/src/components/UI/DeleteConfirmModal/DeleteConfirmModal.tsx`**: Create the Apple-inspired Glassmorphism confirm warning modal.
5. **`frontend/src/components/UI/DeleteConfirmModal/DeleteConfirmModal.module.css`**: Create elegant vanilla CSS styling for the modal, supporting dynamic alert overlays.
6. **`frontend/src/app/(ai-mall)/products/page.tsx`**: Integrate delete handlers, action toolbar buttons, and hook the confirm modal to the React page state.

---

### Task 1: Backend Schemas

**Files:**
* Modify: `services/processor/schemas.py:150-157`

- [x] **Step 1: Add Deletion Schema classes**
  Append `ProductDeleteRequest` and `ProductDeleteResponse` classes to the end of the file.

  ```python
  class ProductDeleteRequest(BaseModel):
      product_ids: Optional[List[UUID]] = None
      wholesale_site_id: Optional[UUID] = None
      force: bool = False

  class ProductDeleteResponse(BaseModel):
      success: bool
      deleted_count: int
      warning_synced_count: int = 0
      message: str
  ```

- [x] **Step 2: Commit schemas modification**
  ```bash
  git add services/processor/schemas.py
  git commit -m "feat: add ProductDeleteRequest and ProductDeleteResponse schemas"
  ```

---

### Task 2: Backend Deletion Tests (TDD - Failing Test)

**Files:**
* Create: `services/processor/tests/test_delete_api.py`

- [ ] **Step 1: Write a failing integration test**
  Create `test_delete_api.py` with mock products and mock market sync records to test both warning gates and successful cascading deletion.

  ```python
  import pytest
  import uuid
  from sqlalchemy import select
  from httpx import AsyncClient
  from main import app
  from models import Product, ProductPlatformMapping, WholesaleSite
  from database import Base, engine
  from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

  @pytest.fixture(scope="module")
  def anyio_backend():
      return "asyncio"

  @pytest.fixture(scope="module")
  async def test_session():
      async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
      yield async_session

  @pytest.mark.anyio
  async def test_delete_endpoint_fails_due_to_sync_warning(test_session):
      async with test_session() as session:
          # 1. Create a dummy Wholesale Site
          site_id = uuid.uuid4()
          site = WholesaleSite(
              id=site_id,
              user_id=uuid.uuid4(),
              name="Test Site Deletion",
              homepage_url="http://test.com",
              column_mapping={}
          )
          session.add(site)

          # 2. Create products (one normal, one synced to market)
          prod1_id = uuid.uuid4()
          prod1 = Product(
              id=prod1_id,
              user_id=site.user_id,
              wholesale_site_id=site_id,
              original_name="Normal Product",
              status="completed"
          )
          prod2_id = uuid.uuid4()
          prod2 = Product(
              id=prod2_id,
              user_id=site.user_id,
              wholesale_site_id=site_id,
              original_name="Synced Product",
              status="completed"
          )
          session.add_all([prod1, prod2])

          # 3. Mark prod2 as synced in mappings
          mapping = ProductPlatformMapping(
              id=uuid.uuid4(),
              product_id=prod2_id,
              platform_name="naver",
              sync_status="synced"
          )
          session.add(mapping)
          await session.commit()

      # 4. Trigger DELETE api without force flag
      async with AsyncClient(app=app, base_url="http://test") as ac:
          headers = {"Authorization": "Bearer internal-test-token"}
          response = await ac.post(
              "/products/delete",
              json={"product_ids": [str(prod1_id), str(prod2_id)], "force": False},
              headers=headers
          )

      assert response.status_code == 200
      data = response.json()
      assert data["success"] is False
      assert data["warning_synced_count"] == 1
      assert data["deleted_count"] == 0

  @pytest.mark.anyio
  async def test_delete_endpoint_success_with_force(test_session):
      # Rely on data setup from previous steps
      async with AsyncClient(app=app, base_url="http://test") as ac:
          headers = {"Authorization": "Bearer internal-test-token"}
          
          # Find created IDs or use wholesale deletion with force
          # Let's delete wholesale site with force=true
          # Find the WholesaleSite created
          async with test_session() as session:
              stmt = select(WholesaleSite).where(WholesaleSite.name == "Test Site Deletion")
              res = await session.execute(stmt)
              site = res.scalar_one_or_none()
              site_id = site.id if site else None

          response = await ac.post(
              "/products/delete",
              json={"wholesale_site_id": str(site_id), "force": True},
              headers=headers
          )

      assert response.status_code == 200
      data = response.json()
      assert data["success"] is True
      assert data["deleted_count"] >= 2
  ```

- [ ] **Step 2: Run the test to ensure it fails**
  Run: `pytest services/processor/tests/test_delete_api.py -v`
  Expected: **FAIL** or **404 Not Found** (since `/products/delete` endpoint is not defined yet).

- [ ] **Step 3: Commit test file**
  ```bash
  git add services/processor/tests/test_delete_api.py
  git commit -m "test: add failing delete API integration tests"
  ```

---

### Task 3: Backend API Implementation (FastAPI Router)

**Files:**
* Modify: `services/processor/main.py:650-680` (Near product listings or export routes)

- [ ] **Step 1: Implement the `/products/delete` endpoint**
  Implement the deletion business logic in `services/processor/main.py`.

  ```python
  from schemas import ProductDeleteRequest, ProductDeleteResponse
  from models import Product, ProductPlatformMapping
  from sqlalchemy import and_, select, delete

  @app.post("/products/delete", response_model=ProductDeleteResponse)
  async def delete_products(
      req: ProductDeleteRequest,
      db: AsyncSession = Depends(get_db)
  ):
      if not req.product_ids and not req.wholesale_site_id:
          return ProductDeleteResponse(
              success=False,
              deleted_count=0,
              message="삭제 대상(product_ids 또는 wholesale_site_id)을 입력해주세요."
          )

      # 1. Resolve product targets
      target_stmt = select(Product.id)
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
      del_stmt = delete(Product).where(Product.id.in_(target_ids))
      res_del = await db.execute(del_stmt)
      await db.commit()

      deleted_count = res_del.rowcount
      return ProductDeleteResponse(
          success=True,
          deleted_count=deleted_count,
          message=f"성공적으로 {deleted_count}개의 상품이 삭제되었습니다."
      )
  ```

- [ ] **Step 2: Run the integration test to ensure it passes**
  Run: `pytest services/processor/tests/test_delete_api.py -v`
  Expected: **PASS**

- [ ] **Step 3: Commit implementation**
  ```bash
  git add services/processor/main.py
  git commit -m "feat: implement product deletion endpoint with safety gate"
  ```

---

### Task 4: Frontend Apple-Style Warning Modal Component

**Files:**
* Create: `frontend/src/components/UI/DeleteConfirmModal/DeleteConfirmModal.tsx`
* Create: `frontend/src/components/UI/DeleteConfirmModal/DeleteConfirmModal.module.css`

- [ ] **Step 1: Create the DeleteConfirmModal React Component**
  Create an interactive component utilizing premium glassmorphism.

  ```typescript
  // frontend/src/components/UI/DeleteConfirmModal/DeleteConfirmModal.tsx
  'use client';

  import React from 'react';
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
    if (!isOpen) return null;

    const hasWarnings = warningSyncedCount > 0;

    return (
      <div className={styles.overlay} onClick={!isDeleting ? onClose : undefined}>
        <div className={styles.modalCard} onClick={(e) => e.stopPropagation()}>
          <div className={styles.iconContainer}>
            {hasWarnings ? (
              <div className={`${styles.icon} ${styles.alertIcon}`}>⚠️</div>
            ) : (
              <div className={`${styles.icon} ${styles.trashIcon}`}>🗑️</div>
            )}
          </div>

          <h2 className={styles.title}>
            {hasWarnings ? '경고: 마켓 연동 상품 포함' : '상품 삭제'}
          </h2>

          <div className={styles.content}>
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

- [ ] **Step 2: Create elegant Vanilla CSS styling**
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

  .iconContainer {
    display: flex;
    justify-content: center;
    margin-bottom: 16px;
  }

  .icon {
    font-size: 38px;
    width: 72px;
    height: 72px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
  }

  .trashIcon {
    background: rgba(0, 122, 255, 0.08);
  }

  .alertIcon {
    background: rgba(255, 59, 48, 0.08);
    animation: pulse 2s infinite;
  }

  .title {
    font-size: 20px;
    font-weight: 600;
    color: #1c1c1e;
    margin: 0 0 14px 0;
  }

  .content p {
    font-size: 14.5px;
    line-height: 1.5;
    color: #48484a;
    margin: 0;
  }

  .highlight {
    color: #ff3b30;
    font-weight: 600;
  }

  .errorAlert {
    background: rgba(255, 59, 48, 0.08);
    border: 1px solid rgba(255, 59, 48, 0.15);
    color: #ff3b30;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 13px;
    margin-top: 16px;
    text-align: left;
  }

  .actions {
    display: flex;
    gap: 12px;
    margin-top: 24px;
  }

  .actions button {
    flex: 1;
    height: 44px;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    outline: none;
  }

  .cancelBtn {
    background: #e5e5ea;
    color: #1c1c1e;
  }

  .cancelBtn:hover {
    background: #d1d1d6;
  }

  .dangerBtn {
    background: #ff3b30;
    color: #ffffff;
  }

  .dangerBtn:hover {
    background: #e0352b;
  }

  .forceBtn {
    background: #ff453a;
    color: #ffffff;
    font-weight: 600;
  }

  .forceBtn:hover {
    background: #e03d32;
  }

  .spinner {
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 3px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: #ffffff;
    animation: spin 1s ease-in-out infinite;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes popUp {
    to { transform: scale(1); }
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
  }
  ```

- [ ] **Step 3: Commit modal component**
  ```bash
  git add frontend/src/components/UI/DeleteConfirmModal
  git commit -m "feat: add DeleteConfirmModal Apple-style React component and CSS styles"
  ```

---

### Task 5: Frontend Page Integration

**Files:**
* Modify: `frontend/src/app/(ai-mall)/products/page.tsx`

- [ ] **Step 1: Import modal and add States**
  Add state hooks to control the deletion flow.

  ```typescript
  // Import DeleteConfirmModal
  import DeleteConfirmModal from '@/components/UI/DeleteConfirmModal/DeleteConfirmModal';

  // Add inside ProductsPage function:
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteConfig, setDeleteConfig] = useState<{
    mode: 'selected' | 'wholesale';
    count: number;
    wholesaleSiteId?: string;
  } | null>(null);
  const [warningSyncedCount, setWarningSyncedCount] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  ```

- [ ] **Step 2: Add API deletion handler**
  ```typescript
  const handleDeleteProducts = useCallback(async (force = false) => {
    if (!deleteConfig) return;
    setIsDeleting(true);
    setDeleteError(null);

    try {
      const payload = {
        product_ids: deleteConfig.mode === 'selected' ? Array.from(selectedIds) : null,
        wholesale_site_id: deleteConfig.mode === 'wholesale' ? deleteConfig.wholesaleSiteId : null,
        force: force
      };

      const response = await api.post<{
        success: boolean;
        deleted_count: number;
        warning_synced_count: number;
        message: string;
      }>('/products/delete', payload);

      if (response.success) {
        setDeleteModalOpen(false);
        setDeleteConfig(null);
        setWarningSyncedCount(0);
        setSelectedIds(new Set());
        setPage(1); // Go back to page 1 to load updated products
        // Trigger page refresh
        window.location.reload(); // Simple refresh or call existing fetchProducts()
      } else {
        setWarningSyncedCount(response.warning_synced_count);
      }
    } catch (err: any) {
      setDeleteError(err.message || '상품 삭제를 처리하는 중 예외가 발생했습니다.');
    } finally {
      setIsDeleting(false);
    }
  }, [deleteConfig, selectedIds]);
  ```

- [ ] **Step 3: Integrate toolbar button triggers**
  * Find the table's toolbar area where `selectedIds.size > 0` actions are defined.
  * Add the **"선택 삭제"** button:
    ```typescript
    {selectedIds.size > 0 && (
      <button 
        className={styles.deleteSelectedBtn}
        onClick={() => {
          setDeleteConfig({ mode: 'selected', count: selectedIds.size });
          setWarningSyncedCount(0);
          setDeleteError(null);
          setDeleteModalOpen(true);
        }}
      >
        선택 삭제 ({selectedIds.size})
      </button>
    )}
    ```
  * Locate the wholesale filter or options panel and render the **"현재 도매처 상품 전체 삭제"** button (enabled when `wholesaleFilter` has a value).
    ```typescript
    {wholesaleFilter && (
      <button 
        className={styles.deleteWholesaleBtn}
        onClick={() => {
          const matchedSite = wholesaleSites.find(s => s.id === wholesaleFilter);
          setDeleteConfig({
            mode: 'wholesale',
            count: total, // current total count of products in this wholesale filter
            wholesaleSiteId: wholesaleFilter
          });
          setWarningSyncedCount(0);
          setDeleteError(null);
          setDeleteModalOpen(true);
        }}
      >
        "{matchedSite?.name || '도매처'}" 상품 전체 삭제
      </button>
    )}
    ```
  * Render `<DeleteConfirmModal>` at the bottom of the page return tree.
    ```typescript
    <DeleteConfirmModal
      isOpen={deleteModalOpen}
      onClose={() => {
        if (!isDeleting) {
          setDeleteModalOpen(false);
          setDeleteConfig(null);
        }
      }}
      onConfirm={handleDeleteProducts}
      count={deleteConfig?.count || 0}
      warningSyncedCount={warningSyncedCount}
      isDeleting={isDeleting}
      error={deleteError}
    />
    ```

- [ ] **Step 4: Add CSS styles for buttons in `products.module.css`**
  ```css
  .deleteSelectedBtn {
    background: rgba(255, 59, 48, 0.09);
    border: 1px solid rgba(255, 59, 48, 0.2);
    color: #ff3b30;
    padding: 8px 16px;
    border-radius: 9999px;
    font-size: 13.5px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-right: 12px;
  }

  .deleteSelectedBtn:hover {
    background: rgba(255, 59, 48, 0.15);
  }

  .deleteWholesaleBtn {
    background: #ffffff;
    border: 1px solid #ff3b30;
    color: #ff3b30;
    padding: 8px 16px;
    border-radius: 9999px;
    font-size: 13.5px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .deleteWholesaleBtn:hover {
    background: rgba(255, 59, 48, 0.05);
  }
  ```

- [ ] **Step 5: Run UI verification & commit integration**
  ```bash
  git add frontend/src/app/\(ai-mall\)/products/page.tsx frontend/src/app/\(ai-mall\)/products/products.module.css
  git commit -m "feat: integrate Deletion Buttons and DeleteConfirmModal to Product List page"
  ```
