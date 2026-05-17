# Command Center Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the `/home` page into a high-productivity "Command Center" dashboard with multi-store metrics, real-time process monitoring, and an action-oriented work queue.

**Architecture:** 3-tier vertical layout (KPIs -> Process Monitor -> Action Queue) using CSS Grid/Flexbox. Multi-store metrics will use mock data as the backend integration is pending.

**Tech Stack:** Next.js (App Router), TypeScript, Vanilla CSS Modules.

---

## File Structure

- `frontend/src/app/(ai-mall)/home/home.module.css`: New styles for the dashboard layout and components.
- `frontend/src/app/(ai-mall)/home/page.tsx`: Updated dashboard component with the 3-tier structure.
- `frontend/src/components/UI/Dashboard/KpiCard.tsx`: New component for metric cards.
- `frontend/src/components/UI/Dashboard/ProgressBar.tsx`: New component for process monitoring.
- `frontend/src/components/UI/Dashboard/ActionItem.tsx`: New component for the work queue.

---

### Task 1: Create Dashboard Components (Completed)

**Files:**
- Create: `frontend/src/components/UI/Dashboard/KpiCard.tsx`
- Create: `frontend/src/components/UI/Dashboard/ProgressBar.tsx`
- Create: `frontend/src/components/UI/Dashboard/ActionItem.tsx`
- Create: `frontend/src/components/UI/Dashboard/Dashboard.module.css`

- [x] **Step 1: Implement KpiCard component**
```tsx
import styles from './Dashboard.module.css';

interface KpiCardProps {
  title: string;
  value: string;
  trend?: { value: string; isUp: boolean };
}

export const KpiCard = ({ title, value, trend }: KpiCardProps) => (
  <div className={styles.kpiCard}>
    <h3 className={styles.kpiTitle}>{title}</h3>
    <div className={styles.kpiValue}>{value}</div>
    {trend && (
      <div className={`${styles.kpiTrend} ${trend.isUp ? styles.up : styles.down}`}>
        {trend.isUp ? '↑' : '↓'} {trend.value}
      </div>
    )}
  </div>
);
```

- [x] **Step 2: Implement ProgressBar component**
```tsx
import styles from './Dashboard.module.css';

interface ProgressBarProps {
  label: string;
  progress: number;
  status: string;
}

export const ProgressBar = ({ label, progress, status }: ProgressBarProps) => (
  <div className={styles.progressContainer}>
    <div className={styles.progressHeader}>
      <span className={styles.progressLabel}>{label}</span>
      <span className={styles.progressStatus}>{status}</span>
    </div>
    <div className={styles.progressTrack}>
      <div className={styles.progressFill} style={{ width: `${progress}%` }} />
    </div>
  </div>
);
```

- [x] **Step 3: Implement ActionItem component**
```tsx
import styles from './Dashboard.module.css';
import PillButton from '../PillButton/PillButton';

interface ActionItemProps {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  type?: 'warning' | 'error' | 'info';
}

export const ActionItem = ({ title, description, actionLabel, onAction, type = 'info' }: ActionItemProps) => (
  <div className={`${styles.actionItem} ${styles[type]}`}>
    <div className={styles.actionContent}>
      <h4 className={styles.actionTitle}>{title}</h4>
      <p className={styles.actionDescription}>{description}</p>
    </div>
    <PillButton variant="secondary" onClick={onAction}>{actionLabel}</PillButton>
  </div>
);
```

- [x] **Step 4: Create CSS for Dashboard components**
```css
.kpiCard {
  background: #fff;
  padding: 24px;
  border-radius: 20px;
  border: 1px solid var(--hairline);
}
.kpiTitle { font-size: 14px; color: var(--ink-muted-48); margin-bottom: 8px; font-weight: 400; }
.kpiValue { font-size: 28px; font-weight: 600; margin-bottom: 8px; }
.kpiTrend { font-size: 13px; font-weight: 500; }
.kpiTrend.up { color: #34c759; }
.kpiTrend.down { color: #ff3b30; }

.progressContainer { margin-bottom: 20px; }
.progressHeader { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }
.progressTrack { height: 8px; background: #f0f0f2; border-radius: 4px; overflow: hidden; }
.progressFill { height: 100%; background: var(--primary); transition: width 0.3s ease; }

.actionItem {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #fff;
  border-radius: 16px;
  border-left: 4px solid var(--primary);
  margin-bottom: 12px;
}
.actionItem.error { border-left-color: #ff3b30; }
.actionItem.warning { border-left-color: #ff9500; }
.actionTitle { font-size: 16px; font-weight: 600; margin: 0 0 4px; }
.actionDescription { font-size: 14px; color: var(--ink-muted-48); margin: 0; }
```

- [x] **Step 5: Commit**
```bash
git add frontend/src/components/UI/Dashboard/*
git commit -m "feat: add reusable dashboard components"
```

---

### Task 2: Implement Main Dashboard Layout

**Files:**
- Create: `frontend/src/app/(ai-mall)/home/home.module.css`
- Modify: `frontend/src/app/(ai-mall)/home/page.tsx`

- [ ] **Step 1: Define Dashboard layout CSS**
```css
.dashboard { display: flex; flex-direction: column; gap: 48px; }
.section { display: flex; flex-direction: column; gap: 24px; }
.sectionHeader { display: flex; justify-content: space-between; align-items: center; }
.sectionTitle { font-size: 24px; font-weight: 600; letter-spacing: -0.01em; margin: 0; }

.kpiGrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 24px; }
.storeRow { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; }
.storeChip {
  padding: 8px 16px;
  background: #fff;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  font-size: 14px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
}
.storeBadge { font-weight: 600; color: var(--primary); }

.monitorCard, .queueCard {
  background: #fff;
  padding: 32px;
  border-radius: 24px;
  border: 1px solid var(--hairline);
}
```

- [ ] **Step 2: Update HomePage with 3-tier structure**
```tsx
'use client';

import { KpiCard } from '@/components/UI/Dashboard/KpiCard';
import { ProgressBar } from '@/components/UI/Dashboard/ProgressBar';
import { ActionItem } from '@/components/UI/Dashboard/ActionItem';
import styles from './home.module.css';

export default function HomePage() {
  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <h1 className={styles.pageTitle}>안녕하세요, 사장님!</h1>
      </header>

      {/* Tier 1: KPI Dashboard */}
      <section className={styles.section}>
        <div className={styles.kpiGrid}>
          <KpiCard title="오늘의 매출" value="₩4,250,000" trend={{ value: "12%", isUp: true }} />
          <KpiCard title="가공 완료 상품" value="128개" trend={{ value: "5%", isUp: true }} />
          <KpiCard title="가공 대기 상품" value="45개" />
          <KpiCard title="AI 효율 (시간 절약)" value="24시간" />
        </div>
        <div className={styles.storeRow}>
          <div className={styles.storeChip}>
            <span>쿠팡</span>
            <span className={styles.storeBadge}>등록 120 / 판매 15</span>
          </div>
          <div className={styles.storeChip}>
            <span>네이버</span>
            <span className={styles.storeBadge}>등록 85 / 판매 8</span>
          </div>
          <div className={styles.storeChip}>
            <span>기타</span>
            <span className={styles.storeBadge}>등록 30 / 판매 2</span>
          </div>
        </div>
      </section>

      {/* Tier 2: Process Monitor */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>프로세스 모니터</h2>
        </div>
        <div className={styles.monitorCard}>
          <ProgressBar label="신상_의류_가공_v2.xlsx" progress={65} status="AI 분석 및 키워드 생성 중..." />
          <ProgressBar label="여름_신발_컬렉션.xlsx" progress={100} status="가공 완료" />
        </div>
      </section>

      {/* Tier 3: Action Queue */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>할 일 목록</h2>
        </div>
        <div className={styles.queueCard}>
          <ActionItem 
            title="카테고리 매핑 확인 필요" 
            description="5건의 상품에 대해 AI가 확신을 갖지 못했습니다. 최종 확인을 해주세요." 
            actionLabel="확인하기" 
            onAction={() => {}}
            type="warning"
          />
          <ActionItem 
            title="가공 오류 발생" 
            description="이미지 누락으로 인해 2건의 상품 가공이 중단되었습니다." 
            actionLabel="수정" 
            onAction={() => {}}
            type="error"
          />
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Commit**
```bash
git add frontend/src/app/\(ai-mall\)/home/*
git commit -m "feat: implement 3-tier Command Center dashboard layout"
```

---

### Task 3: Final Polishing & Verification

**Files:**
- Modify: `frontend/src/app/(ai-mall)/ai-mall.module.css`

- [ ] **Step 1: Refine global layout spacing**
```css
/* Update .main padding for cleaner look */
.main {
  flex: 1;
  padding: 60px 80px;
  background-color: #fbfbfd; /* Very soft light gray for workspace */
  overflow-y: auto;
}
```

- [ ] **Step 2: Verify responsive behavior**
Ensure the `kpiGrid` and `storeRow` handle window resizing gracefully.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/app/\(ai-mall\)/ai-mall.module.css
git commit -m "style: refine main layout padding and background color"
```
