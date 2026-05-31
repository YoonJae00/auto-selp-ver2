---
title: Real-time Smartstore and Coupang Attribute UI Integration
date: 2026-05-31
category: best-practices
module: AI Mall - Intelligence UI
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - "Integrating real-time task progress with platform attribute tags in frontend layouts"
  - "Handling reactive state synchronization between Zustand task managers and DB persistent models"
tags:
  - nextjs
  - fastapi
  - zustand
  - realtime-sync
  - attribute-extraction
---

# Real-time Smartstore and Coupang Attribute UI Integration

## Context
When integrating multi-stage AI batch processing pipelines (like LangGraph agentic graphs on the backend), keeping the user interface completely reactive in real-time is crucial for premium UX. 

We recently added a 4th stage, **Attribute Extraction (속성 추출)**, to our backend pipeline, which extracts product details using Vision LLM and maps them to marketplace-specific schemas (Smartstore/Naver and Coupang). The client needed to see the real-time progress and results of this stage in the floating `IntelligenceCapsule` UI and the product spreadsheet table reactively without page reloads.

## Guidance
To bind real-time Celery PROGRESS updates containing raw JSON structures with DB-persisted schema representations on the frontend, apply the following design patterns:

### 1. DRY Stage Enum Synchronization
Extract core stage literals into a single, unified type across store state definitions:
```typescript
export type ProcessingStage = 'refining' | 'keywords' | 'categorizing' | 'extracting';

export interface CompletedRowStage {
  name: ProcessingStage;
  ms: number;
  mapped_attributes?: Record<string, any>; // Unified payload
}

export interface Task {
  ...
  stage?: ProcessingStage | 'completed_row';
  ...
}
```

### 2. Consolidate Calculation Logic with IIFEs inside JSX
To avoid DRY violations and multiple repetitive rendering computations inside reactive layout components (like summarizing counts of attributes in an accordion), use an Immediately Invoked Function Expression (IIFE) to compute clean local variables first:
```tsx
{stage.name === 'extracting' && stage.mapped_attributes && (() => {
  const naverCount = stage.mapped_attributes.naver_attributes?.length || 0;
  const coupangProd = stage.mapped_attributes.coupang_attributes?.product_attributes?.length || 0;
  const coupangItem = stage.mapped_attributes.coupang_attributes?.item_attributes?.length || 0;
  const coupangCount = coupangProd + coupangItem;

  return (
    <div className={styles.stageDetail}>
      {naverCount > 0 && <>네이버 속성: <strong>{naverCount}개</strong></>}
      {naverCount > 0 && coupangCount > 0 && ' · '}
      {coupangCount > 0 && <>쿠팡 속성: <strong>{coupangCount}개</strong></>}
      {naverCount === 0 && coupangCount === 0 && (
        <span style={{ color: '#8e8e93' }}>추출된 속성 없음</span>
      )}
    </div>
  );
})()}
```

### 3. Safe Parsing Helper with Guards for Dynamic Payloads
Dynamic JSON structures emitted by active worker nodes might be partially complete or fail in dynamic edge cases. Always wrap dynamic iterations inside strict type guards like `Array.isArray()` and utilize safe string fallback interpolations to prevent front-end render crashes:
```typescript
const extractAttributesList = (naverAttrs: any[] = [], coupangAttrs: any = {}) => {
  const attrsList: { key: string; value: string }[] = [];

  const prodAttrs = coupangAttrs.product_attributes || [];
  const itemAttrs = coupangAttrs.item_attributes || [];

  prodAttrs.forEach((attr: any) => {
    if (attr?.attributeTypeName && attr?.attributeValueName) {
      attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
    }
  });

  itemAttrs.forEach((attr: any) => {
    if (attr?.attributeTypeName && attr?.attributeValueName) {
      if (!attrsList.some((a) => a.key === attr.attributeTypeName)) {
        attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
      }
    }
  });

  if (Array.isArray(naverAttrs)) {
    naverAttrs.forEach((attr: any) => {
      if (attr?.attributeRealValue) {
        attrsList.push({ key: `속성 #${attr.attributeSeq ?? ''}`, value: attr.attributeRealValue });
      } else if (attr?.attributeValueSeq) {
        attrsList.push({ key: `속성 #${attr.attributeSeq ?? ''}`, value: `선택값 #${attr.attributeValueSeq}` });
      }
    });
  }

  return attrsList;
};
```

## Why This Matters
- **Crash Prevention**: When streaming dynamic web-socket or polled chunks, incomplete or incorrectly typed values (e.g. `naver_attributes` emitted as `null` or a single object due to backend exceptions) will crash the browser thread if `.forEach()` is called without type checks.
- **Maintainability (DRY)**: Abstracting the attribute mapping logic avoids duplicate logic in DB rendering and real-time state rendering pathways.
- **Interactive WOW-Factor**: Users see Naver/Coupang tags populating instantly during processing, keeping them engaged.

## Examples
*Before (Repetitive and prone to crashing on malformed payloads):*
```typescript
const renderAttributes = (product: Product) => {
  const attrsList = [];
  // DB-only logic...
  naverMapping.mapped_attributes.forEach(attr => { // Throws if not array
    attrsList.push({ key: attr.attributeSeq, value: attr.attributeRealValue }); // Missing attributeValueSeq check
  });
}
```

*After (Safe helper with dual-parsing):*
```typescript
const renderAttributes = (product: Product, realTimeMappedAttributes?: any) => {
  let attrsList = [];
  if (realTimeMappedAttributes) {
    attrsList = extractAttributesList(
      realTimeMappedAttributes.naver_attributes, 
      realTimeMappedAttributes.coupang_attributes
    );
  } else {
    attrsList = extractAttributesList(
      naverMapping?.mapped_attributes, 
      coupangMapping?.mapped_attributes
    );
  }
  // Safe JSX rendering...
}
```

## Related
- [taskStore.ts](file:///Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/store/taskStore.ts)
- [IntelligenceCapsule.tsx](file:///Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx)
- [process/page.tsx](file:///Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/app/\(ai-mall\)/process/page.tsx)
