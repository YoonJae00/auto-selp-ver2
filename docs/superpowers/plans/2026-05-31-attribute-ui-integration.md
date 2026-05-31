# Real-time Smartstore & Coupang Attribute UI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the Smartstore and Coupang attribute extraction step (`extracting` stage) and results into the frontend floating Intelligence Capsule and the main product processing table in real-time.

**Architecture:** 
Extend frontend store definitions to support the `'extracting'` stage. Update the floating `IntelligenceCapsule` to track the 4-stage processing pipeline and display attribute summary counts. Modify the product table's attribute rendering logic to bind live-extracted attributes reactively from Zustand task updates as well as DB persist fallbacks.

**Tech Stack:** Next.js (App Router), Zustand, TypeScript, Vanilla CSS.

---

### Task 1: Extend Task Store Type Definitions

**Files:**
- Modify: `frontend/src/store/taskStore.ts`
- Verification: Run TypeScript compilation check.

- [x] **Step 1: Modify `taskStore.ts` types**
  Extend `CompletedRowStage` to allow the `'extracting'` stage with an optional `mapped_attributes` payload, and update the task's active `stage` union type.

  Modify `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/store/taskStore.ts` around lines 4-29:
  ```typescript
  export interface CompletedRowStage {
    name: 'refining' | 'keywords' | 'categorizing' | 'extracting';
    ms: number;
    mapped_attributes?: any;
  }

  export interface Task {
    id: string;
    filename: string;
    progress: number;
    total?: number;
    status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
    stage?: 'refining' | 'keywords' | 'categorizing' | 'extracting' | 'completed_row';
    currentName?: string;
    completedRows?: CompletedRow[];
    resultPath?: string;
    startTime: number;
    warnings?: Record<number, any[]>;
    result?: any;
  }
  ```

- [x] **Step 2: Verify code compiling**
  Run: `npm run build` in `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/` to ensure the type updates did not break any files.
  Expected: Successful compilation or normal warnings unrelated to types.

- [x] **Step 3: Commit store changes**
  Run:
  ```bash
  git add frontend/src/store/taskStore.ts
  git commit -m "chore: add extracting stage and mapped_attributes to taskStore types"
  ```

---

### Task 2: Implement Real-time Stage Detail & Stage Order in `IntelligenceCapsule.tsx`

**Files:**
- Modify: `frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx`
- Verification: Ensure capsule compiles without issues.

- [x] **Step 1: Modify Capsule metadata and rendering logic**
  Add `'extracting'` to both `STAGE_META` and `STAGE_ORDER`. Expand `StageDetail` component to summarize naver and coupang attribute counts upon extraction.

  Modify `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx` around lines 9-16:
  ```typescript
  const STAGE_META: Record<string, { label: string; icon: string }> = {
    refining:     { label: '상품명 가공',      icon: '✏️' },
    keywords:     { label: '키워드 생성',      icon: '🔍' },
    categorizing: { label: '카테고리 매핑',    icon: '📂' },
    extracting:   { label: '속성 추출',        icon: '✨' },
  };

  const STAGE_ORDER = ['refining', 'keywords', 'categorizing', 'extracting'];
  ```

  Modify the `StageDetail` component around lines 23-50:
  ```tsx
  function StageDetail({ stage }: { stage: any }) {
    const meta = STAGE_META[stage.name] ?? { label: stage.name, icon: '▸' };
    return (
      <div className={styles.stageBody}>
        <div className={styles.stageLabel}>{meta.icon} {meta.label}</div>
        {stage.name === 'refining' && stage.refined_name && (
          <div className={styles.stageDetail}>→ <strong>{stage.refined_name}</strong></div>
        )}
        {stage.name === 'keywords' && stage.keywords?.length > 0 && (
          <div className={styles.stageDetail}>
            {stage.keywords.join(', ')}
            {stage.filtered?.length > 0 && (
              <span style={{ color: '#ff3b30', marginLeft: 6 }}>
                ({stage.filtered.join(', ')} 제거됨)
              </span>
            )}
          </div>
        )}
        {stage.name === 'categorizing' && (
          <div className={styles.stageDetail}>
            {stage.naver_category && <>네이버: <strong>{stage.naver_category}</strong></>}
            {stage.naver_category && stage.coupang_category && ' · '}
            {stage.coupang_category && <>쿠팡: <strong>{stage.coupang_category}</strong></>}
          </div>
        )}
        {stage.name === 'extracting' && stage.mapped_attributes && (
          <div className={styles.stageDetail}>
            {stage.mapped_attributes.naver_attributes?.length > 0 && (
              <>네이버 속성: <strong>{stage.mapped_attributes.naver_attributes.length}개</strong></>
            )}
            {stage.mapped_attributes.naver_attributes?.length > 0 && 
             ((stage.mapped_attributes.coupang_attributes?.product_attributes?.length || 0) + 
              (stage.mapped_attributes.coupang_attributes?.item_attributes?.length || 0)) > 0 && ' · '}
            {((stage.mapped_attributes.coupang_attributes?.product_attributes?.length || 0) + 
              (stage.mapped_attributes.coupang_attributes?.item_attributes?.length || 0)) > 0 && (
              <>쿠팡 속성: <strong>{
                (stage.mapped_attributes.coupang_attributes.product_attributes?.length || 0) + 
                (stage.mapped_attributes.coupang_attributes.item_attributes?.length || 0)
              }개</strong></>
            )}
            {(!stage.mapped_attributes.naver_attributes?.length && 
              !(stage.mapped_attributes.coupang_attributes?.product_attributes?.length || 0) && 
              !(stage.mapped_attributes.coupang_attributes?.item_attributes?.length || 0)) && (
              <span style={{ color: '#8e8e93' }}>추출된 속성 없음</span>
            )}
          </div>
        )}
      </div>
    );
  }
  ```

- [x] **Step 2: Verify compilation**
  Run: `npm run build` in `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/` to ensure no syntax errors.
  Expected: Successful compilation.

- [x] **Step 3: Commit capsule updates**
  Run:
  ```bash
  git add frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx
  git commit -m "feat: integrate extracting stage visual progress into floating capsule"
  ```

---

### Task 3: Unify Attribute Parsing and Enable Live Updates in `process/page.tsx`

**Files:**
- Modify: `frontend/src/app/(ai-mall)/process/page.tsx`
- Verification: Perform overall build verification.

- [x] **Step 1: Update `completedRowsMap` useMemo**
  Retrieve `extractingStage?.mapped_attributes` reactively so real-time attribute updates are saved to the completed row state.

  Modify `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/app/(ai-mall)/process/page.tsx` around lines 230-267:
  ```typescript
  const completedRowsMap = useMemo(() => {
    const map = new Map<string, {
      refined_name: string | null;
      keywords: string[] | null;
      mapped_attributes: any | null;
      status: 'completed' | 'failed' | 'processing';
      error?: string;
    }>();

    tasks.forEach((task) => {
      // Process finished/active task rows
      if (task.completedRows) {
        task.completedRows.forEach((row) => {
          const refiningStage = row.stages?.find(s => s.name === 'refining') as any;
          const keywordsStage = row.stages?.find(s => s.name === 'keywords') as any;
          const extractingStage = row.stages?.find(s => s.name === 'extracting') as any;
          
          map.set(row.name, {
            refined_name: refiningStage?.refined_name || null,
            keywords: keywordsStage?.keywords || null,
            mapped_attributes: extractingStage?.mapped_attributes || null,
            status: row.error ? 'failed' : 'completed',
            error: row.error,
          });
        });
      }

      // If a task is PROGRESS, mark the current item as processing
      if (task.status === 'PROGRESS' && task.currentName) {
        if (!map.has(task.currentName)) {
          map.set(task.currentName, {
            refined_name: null,
            keywords: null,
            mapped_attributes: null,
            status: 'processing',
          });
        }
      }
    });

    return map;
  }, [tasks]);
  ```

- [x] **Step 2: Unify `renderAttributes` parsing logic**
  Rewrite `renderAttributes` to support dual-input: `product` + optional `realTimeMappedAttributes`. Parse both input-based and select-based Naver attributes.

  Modify `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/app/(ai-mall)/process/page.tsx` around lines 71-123:
  ```tsx
  const renderAttributes = (product: Product, realTimeMappedAttributes?: any) => {
    const attrsList: { key: string; value: string }[] = [];

    // 1. Parse real-time attributes from in-progress task stage output
    if (realTimeMappedAttributes) {
      const naverAttrs = realTimeMappedAttributes.naver_attributes || [];
      const coupangAttrs = realTimeMappedAttributes.coupang_attributes || {};
      
      const prodAttrs = coupangAttrs.product_attributes || [];
      const itemAttrs = coupangAttrs.item_attributes || [];

      prodAttrs.forEach((attr: any) => {
        if (attr.attributeTypeName && attr.attributeValueName) {
          attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
        }
      });

      itemAttrs.forEach((attr: any) => {
        if (attr.attributeTypeName && attr.attributeValueName) {
          if (!attrsList.some((a) => a.key === attr.attributeTypeName)) {
            attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
          }
        }
      });

      naverAttrs.forEach((attr: any) => {
        if (attr.attributeRealValue) {
          attrsList.push({ key: `속성 #${attr.attributeSeq}`, value: attr.attributeRealValue });
        } else if (attr.attributeValueSeq) {
          attrsList.push({ key: `속성 #${attr.attributeSeq}`, value: `선택값 #${attr.attributeValueSeq}` });
        }
      });
    } 
    // 2. Fall back to standard database persisted mappings
    else if (product.platform_mappings && product.platform_mappings.length > 0) {
      const coupangMapping = product.platform_mappings.find((m) => m.platform_name === 'coupang');
      const naverMapping = product.platform_mappings.find((m) => m.platform_name === 'naver');

      if (coupangMapping?.mapped_attributes) {
        const coupangAttrs = coupangMapping.mapped_attributes as any;
        const prodAttrs = coupangAttrs.product_attributes || [];
        const itemAttrs = coupangAttrs.item_attributes || [];

        prodAttrs.forEach((attr: any) => {
          if (attr.attributeTypeName && attr.attributeValueName) {
            attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
          }
        });

        itemAttrs.forEach((attr: any) => {
          if (attr.attributeTypeName && attr.attributeValueName) {
            if (!attrsList.some((a) => a.key === attr.attributeTypeName)) {
              attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
            }
          }
        });
      }

      if (naverMapping?.mapped_attributes) {
        const naverAttrs = naverMapping.mapped_attributes;
        if (Array.isArray(naverAttrs)) {
          naverAttrs.forEach((attr: any) => {
            if (attr.attributeRealValue) {
              attrsList.push({ key: `속성 #${attr.attributeSeq}`, value: attr.attributeRealValue });
            } else if (attr.attributeValueSeq) {
              attrsList.push({ key: `속성 #${attr.attributeSeq}`, value: `선택값 #${attr.attributeValueSeq}` });
            }
          });
        }
      }
    }

    if (attrsList.length === 0) {
      return <span className={styles.emptyAttributes}>-</span>;
    }

    return (
      <div className={styles.attributeCloud}>
        {attrsList.map((attr, idx) => (
          <span key={`${product.id}-attr-${idx}`} className={styles.attributeTag}>
            <span className={styles.attributeKey}>{attr.key}</span>: {attr.value}
          </span>
        ))}
      </div>
    );
  };
  ```

- [x] **Step 3: Update Table rendering row parameter**
  Update the table row attributes cell to pass the real-time attribute map result.

  Modify `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/app/(ai-mall)/process/page.tsx` around line 623:
  ```tsx
  <td>{renderAttributes(product, realTimeUpdate?.mapped_attributes)}</td>
  ```

- [x] **Step 4: Verify complete build**
  Run: `npm run build` in `/Users/yoonjae/Desktop/auto-selp-ver2/frontend/` to guarantee no errors.
  Expected: Successful compilation of the entire application.

- [x] **Step 5: Commit table updates**
  Run:
  ```bash
  git add frontend/src/app/\(ai-mall\)/process/page.tsx
  git commit -m "feat: render real-time and DB persisted platform attributes reactively in table"
  ```
