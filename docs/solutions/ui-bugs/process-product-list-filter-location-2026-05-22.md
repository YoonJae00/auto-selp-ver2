---
title: "상품 가공 목록 필터가 보이지 않던 문제"
date: "2026-05-22"
category: "docs/solutions/ui-bugs"
module: "product-processing"
problem_type: "ui_bug"
component: "frontend_stimulus"
symptoms:
  - "상품 가공 화면의 도매처 상품 목록에 요청한 필터 메뉴가 보이지 않음"
  - "Codex 워크트리에서 변경한 화면과 브라우저의 localhost 화면이 서로 다름"
root_cause: "incomplete_setup"
resolution_type: "code_fix"
severity: "medium"
tags: ["product-processing", "filters", "worktree", "localhost", "wholesale"]
---

# 상품 가공 목록 필터가 보이지 않던 문제

## Problem
상품 가공 화면의 도매처 상품 목록에 도매가 정렬과 가공상태 필터를 추가해야 했지만, 처음에는 `/products` 상품 관리 화면에 구현되어 사용자가 보고 있던 `/process` 화면에는 변화가 보이지 않았다.

## Symptoms
- 사용자가 `localhost:3000/process`에서 보는 "친구도매 상품 목록"에는 필터 UI가 나타나지 않았다.
- Codex 워크트리의 `/process/page.tsx`에는 예전 업로드/매핑 단계 UI가 있었고, 실제 브라우저 화면의 도매처 상품 목록 텍스트는 검색되지 않았다.
- `lsof -nP -iTCP:3000 -sTCP:LISTEN` 결과 `127.0.0.1:3000`은 Codex 워크트리, `localhost:3000`은 `/Users/yoonjae/Desktop/auto-selp-ver2/frontend`에서 떠 있었다.

## What Didn't Work
- `/products` 화면에 도매가 정렬과 "가공 완료만 보기"를 추가하는 것만으로는 사용자가 보는 화면이 바뀌지 않았다. 요청의 "상품 가공에서 상품목록"은 상품 관리 페이지가 아니라 `/process` 안의 도매처별 상품 목록이었다.
- Codex 워크트리 기준으로만 파일을 검색하면 실제 실행 중인 Desktop repo의 `/process` 구현을 찾을 수 없었다.
- 프론트만 수정하면 완료 필터는 동작할 수 있지만 도매가 정렬은 API가 `sort_by`/`sort_order`를 받아야 페이지네이션 전체 기준으로 안정적으로 정렬된다.

## Solution
실제 실행 중인 repo 경로를 먼저 확인한 뒤, `/process` 상품 목록에 필터바를 추가하고 `/products` API에 도매가 정렬 파라미터를 연결했다.

```tsx
const [statusFilter, setStatusFilter] = useState('');
const [completedOnly, setCompletedOnly] = useState(false);
const [wholesalePriceSort, setWholesalePriceSort] = useState('');

const effectiveStatus = completedOnly ? 'completed' : statusFilter;
if (effectiveStatus) params.append('status', effectiveStatus);
if (wholesalePriceSort) {
  params.append('sort_by', 'price_wholesale');
  params.append('sort_order', wholesalePriceSort);
}
```

UI는 `/process`의 기존 테이블 툴바 아래에 추가했다.

```tsx
<div className={styles.filterBar} aria-label="상품 필터">
  <label className={styles.filterGroup}>
    <span>가공 상태</span>
    <select value={statusFilter} onChange={...}>
      <option value="">전체 상태</option>
      <option value="pending">대기</option>
      <option value="processing">가공 중</option>
      <option value="completed">완료</option>
      <option value="failed">실패</option>
    </select>
  </label>

  <label className={styles.filterGroup}>
    <span>도매가 정렬</span>
    <select value={wholesalePriceSort} onChange={...}>
      <option value="">기본순</option>
      <option value="asc">낮은 도매가순</option>
      <option value="desc">높은 도매가순</option>
    </select>
  </label>

  <label className={styles.filterToggle}>
    <input type="checkbox" checked={completedOnly} onChange={...} />
    가공 완료만 보기
  </label>
</div>
```

백엔드는 SQL 레벨에서 도매가 정렬을 적용한다.

```python
def apply_product_sort(stmt, sort_by: Optional[str], sort_order: str):
    if sort_by == "price_wholesale":
        sort_column = Product.price_wholesale
        if sort_order == "asc":
            return stmt.order_by(sort_column.asc().nullslast(), Product.created_at.desc())
        return stmt.order_by(sort_column.desc().nullslast(), Product.created_at.desc())

    return stmt.order_by(Product.created_at.desc())
```

Desktop repo의 processor 컨테이너는 백엔드 코드 변경 후 재시작했다.

```bash
docker compose restart processor
```

## Why This Works
`/process` 화면은 도매처를 선택하고 DB에 저장된 상품을 페이지 단위로 조회하는 실제 작업 화면이다. 필터 상태를 `/api/processor/products` 쿼리스트링으로 넘기면 현재 페이지 내부만 정렬하는 문제가 없고, 전체 결과 기준으로 가공 상태와 도매가 정렬이 적용된다.

실행 중인 서버의 cwd를 확인한 것도 중요했다. 같은 포트에 두 Node 프로세스가 떠 있었고, 브라우저가 보는 `localhost`와 Codex가 띄운 `127.0.0.1`이 서로 다른 repo를 바라보고 있었다.

## Prevention
- UI 변경이 보이지 않으면 먼저 `lsof -nP -iTCP:<port> -sTCP:LISTEN`과 프로세스 cwd로 실제 실행 중인 repo를 확인한다.
- 사용자가 말한 화면명과 라우트를 브라우저에서 확인한 뒤 변경 대상을 정한다. "상품목록"처럼 여러 화면에 같은 단어가 있을 때는 특히 중요하다.
- 페이지네이션이 있는 목록의 정렬은 프론트 배열 정렬 대신 API 정렬 파라미터로 구현한다.
- `/process` 상품목록 관련 필터는 `/products` 페이지가 아니라 `frontend/src/app/(ai-mall)/process/page.tsx`에 우선 적용한다.

## Related Issues
- `docs/solutions/architecture-patterns/wholesale-management-smart-upsert.md`
- `docs/solutions/database-issues/product-db-migration-2026-05-20.md`
