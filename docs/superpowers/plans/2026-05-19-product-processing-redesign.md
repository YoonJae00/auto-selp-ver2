# Product Processing Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the product processing page into a premium, energetic workspace with step-by-step animations and a real-time shimmer timeline for AI processing stages.

**Architecture:** We will modify the celery tasks in the backend to emit fine-grained stage metadata, update the Zustand taskStore on the frontend to handle these new fields, and refactor the processing UI into a step-based architecture with CSS-driven animations (fade+slide, shimmer text) using standard Next.js and vanilla CSS.

**Tech Stack:** Next.js, React, Zustand, Vanilla CSS, FastAPI, Celery.

---

### Task 1: Backend Celery Task Enhancement

**Files:**
- Modify: `services/processor/tasks.py`

- [ ] **Step 1: Update Celery `_run_pipeline` function**
Modify `_run_pipeline` to report `stage` and `current_name`.

```python
# Before Stage 1: 정제
task_instance.update_state(
    state='PROGRESS', 
    meta={
        'percent': progress, 
        'current': index + 1, 
        'total': total_rows,
        'stage': 'refining',
        'current_name': original_name,
        'warnings': all_warnings
    }
)
refined_name = await llm_client.refine_product_name(original_name)

# Before Stage 2: 키워드
task_instance.update_state(
    state='PROGRESS', 
    meta={
        'percent': progress, 
        'current': index + 1, 
        'total': total_rows,
        'stage': 'keywords',
        'current_name': original_name,
        'warnings': all_warnings
    }
)
keywords, warnings = await keyword_engine.curate_keywords(refined_name)
if warnings:
    all_warnings[index] = warnings

# Before Stage 3: 카테고리
task_instance.update_state(
    state='PROGRESS', 
    meta={
        'percent': progress, 
        'current': index + 1, 
        'total': total_rows,
        'stage': 'categorizing',
        'current_name': original_name,
        'warnings': all_warnings
    }
)
```

- [ ] **Step 2: Commit**

```bash
git add services/processor/tasks.py
git commit -m "feat(backend): emit fine-grained stage metadata in celery task"
```

---

### Task 2: Frontend State Updates

**Files:**
- Modify: `frontend/src/store/taskStore.ts`
- Modify: `frontend/src/components/TaskPollingProvider.tsx`

- [ ] **Step 1: Update Task Interface in `taskStore.ts`**

```typescript
export interface Task {
  id: string;
  filename: string;
  progress: number;
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
  stage?: 'refining' | 'keywords' | 'verifying' | 'categorizing';
  currentName?: string;
  resultPath?: string;
  startTime: number;
  warnings?: Record<number, any[]>;
  result?: any;
}
```

- [ ] **Step 2: Update `TaskPollingProvider.tsx` metadata extraction**
Locate where `api.get` is called in the polling interval and ensure `stage` and `current_name` are extracted from `data.meta`.
*(If the polling provider already merges all updates via `updateTask`, confirm `meta.stage` and `meta.current_name` map to `stage` and `currentName`)*.

```typescript
// Assuming mapping inside TaskPollingProvider polling loop:
updateTask(task.id, {
  status: data.state,
  progress: data.meta?.percent || 0,
  stage: data.meta?.stage,
  currentName: data.meta?.current_name,
  warnings: data.meta?.warnings,
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/store/taskStore.ts frontend/src/components/TaskPollingProvider.tsx
git commit -m "feat(frontend): add stage and currentName to task store"
```

---

### Task 3: CSS System Updates

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/app/(ai-mall)/process/process.module.css`

- [ ] **Step 1: Add gradients to `tokens.css`**

```css
:root {
  /* ... existing tokens ... */
  --accent-gradient: linear-gradient(135deg, #6366f1, #3b82f6, #06b6d4);
  --accent-gradient-hover: linear-gradient(135deg, #4f46e5, #2563eb, #0891b2);
}
```

- [ ] **Step 2: Add animations to `process.module.css`**

```css
/* At the bottom of process.module.css */
@keyframes shimmerText {
  0% {
    background-position: -200% center;
  }
  100% {
    background-position: 200% center;
  }
}

.shimmerText {
  background: linear-gradient(
    90deg,
    var(--ink-muted-48) 0%,
    var(--ink-muted-48) 35%,
    var(--primary) 50%,
    var(--ink-muted-48) 65%,
    var(--ink-muted-48) 100%
  );
  background-size: 200% auto;
  color: transparent;
  -webkit-background-clip: text;
  background-clip: text;
  animation: shimmerText 3s linear infinite;
  font-weight: 600;
}

@keyframes fadeSlideUp {
  0% { opacity: 0; transform: translateY(20px); }
  100% { opacity: 1; transform: translateY(0); }
}

.stepContainer {
  animation: fadeSlideUp 0.3s ease-out forwards;
}

/* Timeline Layout */
.timelineSplit {
  display: flex;
  gap: 32px;
  align-items: flex-start;
}

.timelineLeft {
  flex: 1;
}

.timelineRight {
  flex: 1;
  background: var(--canvas-parchment);
  border-radius: 16px;
  padding: 24px;
  border: 1px solid var(--hairline);
}

.timelineItem {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  font-size: 15px;
}

.timelineIcon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 14px;
}

.timelineIcon.completed {
  background: #10b981;
  color: white;
}

.timelineIcon.active {
  background: var(--primary);
  color: white;
  animation: pulse 2s infinite;
}

.timelineIcon.pending {
  background: var(--hairline);
  color: var(--ink-muted-48);
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(0, 102, 204, 0.4); }
  70% { box-shadow: 0 0 0 8px rgba(0, 102, 204, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 102, 204, 0); }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/\(ai-mall\)/process/process.module.css
git commit -m "style(process): add gradient tokens and timeline animations"
```

---

### Task 4: Process Page Step Indicator & Upload Redesign

**Files:**
- Modify: `frontend/src/app/(ai-mall)/process/page.tsx`

- [ ] **Step 1: Create Step Indicator UI**
Add a horizontal step indicator at the top of the container, before the steps render.

```tsx
const STEPS = [
  { id: 'UPLOAD', label: '① 파일 업로드' },
  { id: 'MAPPING', label: '② 컬럼 설정' },
  { id: 'PROCESSING', label: '③ 가공 중' },
  { id: 'COMPLETED', label: '④ 완료' }
];

// Inside render:
<div className={styles.stepIndicator}>
  {STEPS.map((s, index) => (
    <div key={s.id} className={`${styles.stepItem} ${step === s.id ? styles.activeStep : ''}`}>
      {s.label}
      {index < STEPS.length - 1 && <div className={styles.stepConnector} />}
    </div>
  ))}
</div>
```
*(Add `.stepIndicator`, `.stepItem`, `.activeStep`, `.stepConnector` to `process.module.css`)*

- [ ] **Step 2: Update Upload Section**
Ensure the upload section uses the `stepContainer` animation class. Replace border color with `--accent-gradient` via inline style or CSS pseudo-element on hover.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(ai-mall\)/process/page.tsx frontend/src/app/\(ai-mall\)/process/process.module.css
git commit -m "feat(process): add step indicator and animated upload container"
```

---

### Task 5: Live Timeline UI Implementation

**Files:**
- Modify: `frontend/src/app/(ai-mall)/process/page.tsx`

- [ ] **Step 1: Replace Processing Section with Timeline Split Layout**

```tsx
{(step === 'PROCESSING' || step === 'COMPLETED') && (
  <section className={`${styles.section} ${styles.stepContainer}`}>
    <div className={styles.timelineSplit}>
      
      {/* Left: Global Progress */}
      <div className={styles.timelineLeft}>
        <div className={styles.statusText}>
          {step === 'PROCESSING' ? `상품 가공 중... (${activeTask?.progress || 0}%)` : '가공이 완료되었습니다!'}
        </div>
        
        <div className={styles.progressBar}>
          <div className={styles.progressFill} style={{ width: `${activeTask?.progress || 0}%`, background: 'var(--accent-gradient)' }}></div>
        </div>
        
        {step === 'COMPLETED' && (
          <div style={{ marginTop: '24px' }}>
            <PillButton variant="primary" onClick={handleDownload}>결과 파일 다운로드</PillButton>
          </div>
        )}
      </div>

      {/* Right: Live Timeline */}
      <div className={styles.timelineRight}>
        <h4 style={{ marginBottom: '16px', color: 'var(--ink)' }}>진행 현황</h4>
        {activeTask?.currentName && (
          <div style={{ marginBottom: '16px', padding: '12px', background: '#fff', borderRadius: '8px', fontSize: '13px' }}>
            현재 처리중: <strong>{activeTask.currentName}</strong>
          </div>
        )}
        
        <div className={styles.timelineList}>
           <TimelineItem 
             label="상품명 정제" 
             isActive={activeTask?.stage === 'refining'} 
             isPast={['keywords', 'categorizing', 'verifying'].includes(activeTask?.stage || '') || step === 'COMPLETED'} 
           />
           <TimelineItem 
             label="키워드 생성" 
             isActive={activeTask?.stage === 'keywords'} 
             isPast={['categorizing'].includes(activeTask?.stage || '') || step === 'COMPLETED'} 
           />
           <TimelineItem 
             label="카테고리 매핑" 
             isActive={activeTask?.stage === 'categorizing'} 
             isPast={step === 'COMPLETED'} 
           />
        </div>
      </div>
      
    </div>
  </section>
)}
```

- [ ] **Step 2: Add `TimelineItem` Component Helper**

```tsx
const TimelineItem = ({ label, isActive, isPast }: { label: string, isActive: boolean, isPast: boolean }) => {
  return (
    <div className={styles.timelineItem}>
      <div className={`${styles.timelineIcon} ${isPast ? styles.completed : isActive ? styles.active : styles.pending}`}>
        {isPast ? '✓' : isActive ? '⟳' : '○'}
      </div>
      <div className={isActive ? styles.shimmerText : (isPast ? styles.completedText : styles.pendingText)}>
        {label} {isActive && '...'}
      </div>
    </div>
  );
};
```
*(Add `.completedText` (color: ink) and `.pendingText` (color: muted-48) to CSS)*

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(ai-mall\)/process/page.tsx
git commit -m "feat(process): implement animated real-time process timeline"
```
