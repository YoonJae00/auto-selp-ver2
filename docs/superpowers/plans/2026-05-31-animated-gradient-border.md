# Animated Gradient Border Pill Loading Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the `IntelligenceCapsule` component in the frontend to display a spinning rainbow gradient border when tasks are actively processing, returning to a clean, static Apple-style glass capsule upon completion.

**Architecture:** Wrap the capsule `button` inside a `.capsuleWrapper` relative container to keep the ambient `.glowRing` visible without being clipped by the button's `overflow: hidden`. Place a rotating `conic-gradient` container inside the active button, masked by a frosted-glass inner capsule to form a perfect 1.5px gradient border.

**Tech Stack:** Next.js (React), CSS Modules

---

### Task 1: Update CSS Styles (`IntelligenceCapsule.module.css`)

**Files:**
- Modify: `frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.module.css`

- [x] **Step 1: Modify Capsule, add loading state, wrapper, inner, and rotating gradient classes**

Replace the `.capsule` class and add `.capsuleWrapper`, `.capsule.loading`, `.capsuleInner`, and `.rainbowBorder` classes.

```css
/* ── Capsule Wrapper (To contain outer glow without clipping) ───────────── */
.capsuleWrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

/* ── Capsule ─────────────────────────────────────────────────────────────── */

.capsule {
  position: relative;
  display: flex;
  align-items: center;
  height: 44px;
  padding: 0; /* Padding is 0 so capsuleInner handles inner padding */
  border: none;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow:
    0 2px 8px rgba(0,0,0,0.08),
    0 0 0 1px rgba(255,255,255,0.6) inset;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  outline: none;
  z-index: 2; /* Sits above the glowRing */
  overflow: hidden; /* Clips the rotating conic gradient to the rounded capsule shape */
}

.capsule:hover {
  transform: scale(1.03);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
}

.capsule.loading {
  padding: 1.5px; /* Creates the 1.5px gap for the rainbow border */
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

/* ── Inner Content (Apple glassmorphism) ── */
.capsuleInner {
  display: flex;
  align-items: center;
  width: 100%;
  height: 100%;
  padding: 0 20px;
  border-radius: 21px; /* Fits inside the 22px capsule with 1.5px gap */
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  z-index: 3;
}

/* ── Rainbow Border Layer ── */
.rainbowBorder {
  position: absolute;
  inset: -50%; /* Large enough to cover the rotation area */
  background: conic-gradient(
    from 0deg,
    #ff3b30, #ff9500, #34c759, #007aff, #af52de, #ff3b30
  );
  animation: spinRainbow 3s linear infinite;
  z-index: 1;
  pointer-events: none;
}

@keyframes spinRainbow {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
```

- [x] **Step 2: Adjust `.glowRing` z-index**

Since `.glowRing` is now a sibling in `.capsuleWrapper`, adjust its styling to fit perfectly behind the capsule button.

```css
.glowRing {
  position: absolute;
  inset: -6px;
  border-radius: 28px;
  /* Small bright arc (0-40deg) + rest transparent → after blur looks ambient */
  background: conic-gradient(
    from 0deg,
    rgba(167, 139, 250, 0)   0deg,
    rgba(167, 139, 250, 0.9) 10deg,
    rgba(96,  165, 250, 0.9) 22deg,
    rgba(52,  211, 153, 0.7) 36deg,
    rgba(52,  211, 153, 0)   48deg,
    rgba(167, 139, 250, 0)   360deg
  );
  filter: blur(14px);
  animation: orbitGlow 4.5s linear infinite;
  z-index: 1; /* Renders behind button (which has z-index 2) */
  pointer-events: none;
}
```

- [x] **Step 3: Commit CSS Changes**

```bash
git add frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.module.css
git commit -m "style: add rotating gradient border and wrapper container for IntelligenceCapsule"
```

---

### Task 2: Update Component JSX Structure (`IntelligenceCapsule.tsx`)

**Files:**
- Modify: `frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx`

- [x] **Step 1: Modify the TSX structure of the capsule button**

Update the returned TSX in `IntelligenceCapsule` function (lines 282-304) to use the new `.capsuleWrapper`, `.capsuleInner`, and `.rainbowBorder` elements.

```tsx
        {/* Capsule Wrapper */}
        <div className={styles.capsuleWrapper}>
          {isActive && <div className={styles.glowRing} />}
          <button
            className={`${styles.capsule} ${isActive ? styles.loading : ''}`}
            onClick={handleCapsuleClick}
            aria-label="작업 현황 열기"
          >
            {isActive && <div className={styles.rainbowBorder} />}
            <div className={styles.capsuleInner}>
              <div className={styles.capsuleContent}>
                {isActive ? (
                  <>
                    <span className={styles.capsuleIcon}>⚡</span>
                    <span>가공 중... ({displayTask.progress}%)</span>
                    <div className={styles.miniBar}>
                      <div className={styles.miniBarFill} style={{ width: `${displayTask.progress}%` }} />
                    </div>
                  </>
                ) : (
                  <>
                    <span className={styles.capsuleIcon}>✅</span>
                    <span>가공 완료</span>
                  </>
                )}
              </div>
            </div>
          </button>
        </div>
```

- [x] **Step 2: Commit TSX Changes**

```bash
git add frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx
git commit -m "feat: implement animated gradient border markup in IntelligenceCapsule"
```

---

### Task 3: Verification & Polish

**Files:**
- Test visually in the browser.

- [x] **Step 1: Verify styling compiles successfully without CSS module errors**

Run the Next.js production build or test suite to ensure the changes compile and build perfectly.

Run: `npm run build` inside `/Users/yoonjae/Desktop/auto-selp-ver2/frontend`
Expected: Compile success without TS or CSS errors.

- [x] **Step 2: Complete CE compound review**

Run `/ce-compound mode:headless` after successfully completing the feature.
