# AI-Mall Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js-based frontend with an Apple-inspired design for the Auto-Selp platform, featuring a marketing landing page and a dedicated AI Mall management area.

**Architecture:** Use Next.js App Router with Route Groups (`(marketing)`, `(ai-mall)`) to separate concerns. Styling is handled via Vanilla CSS and CSS Modules for precise design control.

**Tech Stack:** Next.js 14, TypeScript, Vanilla CSS (CSS Modules), Zustand, SWR.

---

### Task 1: Initialize Next.js Project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/.gitignore`

- [ ] **Step 1: Create package.json with necessary dependencies**
```json
{
  "name": "auto-selp-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.2.3",
    "react": "^18",
    "react-dom": "^18",
    "zustand": "^4.5.2",
    "swr": "^2.2.5",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.3.0"
  },
  "devDependencies": {
    "typescript": "^5",
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "eslint": "^8",
    "eslint-config-next": "14.2.3"
  }
}
```

- [ ] **Step 2: Create next.config.mjs**
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
```

- [ ] **Step 3: Run npm install**
Run: `cd frontend && npm install`

- [ ] **Step 4: Commit initialization**
```bash
git add frontend/package.json frontend/next.config.mjs
git commit -m "chore: initialize next.js project"
```

### Task 2: Setup Design Tokens and Global Styles

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Define CSS variables in tokens.css based on design.md**
```css
:root {
  --canvas: #ffffff;
  --canvas-parchment: #f5f5f7;
  --primary: #0066cc;
  --primary-focus: #0071e3;
  --ink: #1d1d1f;
  --ink-muted-80: #333333;
  --ink-muted-48: #7a7a7a;
  --divider-soft: rgba(0, 0, 0, 0.04);
  --hairline: #e0e0e0;
  --surface-black: #000000;
  
  --font-display: 'Inter', system-ui, -apple-system, sans-serif;
  --font-body: 'Inter', system-ui, -apple-system, sans-serif;
}
```

- [ ] **Step 2: Create basic global styles**
```css
@import url('https://rsms.me/inter/inter.css');

html, body {
  padding: 0;
  margin: 0;
  font-family: var(--font-body);
  background-color: var(--canvas);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4 {
  font-family: var(--font-display);
  letter-spacing: -0.02em;
}
```

- [ ] **Step 3: Create Root Layout**
```tsx
import '@/styles/globals.css';
import '@/styles/tokens.css';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 4: Commit styles**
```bash
git add frontend/src/styles/ frontend/src/app/layout.tsx
git commit -m "feat: setup design tokens and root layout"
```

### Task 3: Create Reusable UI Components

**Files:**
- Create: `frontend/src/components/UI/PillButton/PillButton.tsx`
- Create: `frontend/src/components/UI/PillButton/PillButton.module.css`

- [ ] **Step 1: Implement PillButton component**
```tsx
import styles from './PillButton.module.css';
import clsx from 'clsx';

interface Props {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'link';
  onClick?: () => void;
}

export default function PillButton({ children, variant = 'primary', onClick }: Props) {
  return (
    <button 
      className={clsx(styles.button, styles[variant])}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 2: Implement PillButton styles**
```css
.button {
  padding: 11px 22px;
  border-radius: 999px;
  font-size: 17px;
  cursor: pointer;
  transition: transform 0.2s, background-color 0.2s;
  border: none;
  font-weight: 400;
}

.button:active {
  transform: scale(0.95);
}

.primary {
  background-color: var(--primary);
  color: #fff;
}

.secondary {
  background-color: var(--canvas-parchment);
  color: var(--primary);
}

.link {
  background: none;
  color: var(--primary);
  padding: 0;
}
```

- [ ] **Step 3: Commit components**
```bash
git add frontend/src/components/UI/PillButton/
git commit -m "feat: add PillButton component"
```

### Task 4: Implement Marketing Route Group

**Files:**
- Create: `frontend/src/app/(marketing)/layout.tsx`
- Create: `frontend/src/app/(marketing)/page.tsx`
- Create: `frontend/src/app/(marketing)/marketing.module.css`

- [ ] **Step 1: Create Marketing Layout**
```tsx
import styles from './marketing.module.css';

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className={styles.layout}>
      <nav className={styles.nav}>
        <div className={styles.navContent}>
          <span className={styles.logo}>Auto-Selp</span>
        </div>
      </nav>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Implement Landing Page**
```tsx
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from './marketing.module.css';

export default function LandingPage() {
  return (
    <main>
      <section className={styles.hero}>
        <h1>이커머스 운영의 새로운 정의.</h1>
        <p>당신의 쇼핑몰을 AI와 함께 가장 스마트하게 관리하세요.</p>
        <PillButton>지금 시작하기</PillButton>
      </section>
    </main>
  );
}
```

- [ ] **Step 3: Commit marketing route**
```bash
git add frontend/src/app/(marketing)/
git commit -m "feat: implement marketing landing page"
```

### Task 5: Implement AI-Mall Route Group

**Files:**
- Create: `frontend/src/app/(ai-mall)/layout.tsx`
- Create: `frontend/src/app/(ai-mall)/home/page.tsx`
- Create: `frontend/src/app/(ai-mall)/ai-mall.module.css`

- [ ] **Step 1: Create AI-Mall Layout with Sidebar**
```tsx
import styles from './ai-mall.module.css';

export default function AiMallLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className={styles.container}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarBrand}>Auto-Selp AI Mall</div>
        <nav className={styles.sidebarNav}>
          <div className={styles.activeNavItem}>홈</div>
          <div>상품 가공</div>
          <div>설정</div>
        </nav>
      </aside>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Implement Home Page**
```tsx
import styles from './ai-mall.module.css';

export default function HomePage() {
  return (
    <div>
      <h1 className={styles.pageTitle}>안녕하세요, 사장님!</h1>
      <div className={styles.statsGrid}>
        <div className={styles.card}>
          <h3>오늘의 매출</h3>
          <div className={styles.cardValue}>₩4,250,000</div>
        </div>
        <div className={styles.card}>
          <h3>가공 대기 상품</h3>
          <div className={styles.cardValue}>45개</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit AI-Mall route**
```bash
git add frontend/src/app/(ai-mall)/
git commit -m "feat: implement ai-mall home layout and page"
```
