---
title: Implementing Animated Conic Gradient Border Loading Indicators on Dynamically-Sized HTML Elements
date: 2026-05-31
category: design-patterns
module: frontend
problem_type: design_pattern
component: tooling
severity: low
applies_when:
  - "adding rotating gradient borders to dynamically sized elements"
  - "designing loading indicators with apple watch style ambient glows"
tags:
  - loading-indicator
  - gradient-border
  - conic-gradient
  - backdrop-filter
  - glassmorphism
---

# Implementing Animated Conic Gradient Border Loading Indicators on Dynamically-Sized HTML Elements

## Context
Implementing a continuous spinning gradient (rainbow) border on dynamic-width elements in modern web apps is challenging due to standard CSS boundary and overflow behaviors:
1. `border-image` properties do not support `border-radius` gracefully in older or cross-platform web engines.
2. Direct `background: conic-gradient` on a bordered element is hard to animate (requires CSS Houdini `@property`, which is poorly supported in Safari/Firefox).
3. Setting `overflow: hidden` on a pill-shaped container to clip the rotating gradient corner-shapes causes outer sibling elements like soft ambient glows (`box-shadow`, `filter: blur()`) to be clipped and rendered invisible.

## Guidance
To achieve a high-performance, responsive, and robust animated gradient border loading indicator without visual bugs, use a **nested container approach** with three distinct layers:

1. **Outer Capsule Wrapper (`.capsuleWrapper`):** A relative container without `overflow: hidden`. This serves as the positioning base and holds any soft ambient glows (e.g. `.glowRing`) so they can blur outward beautifully without being clipped.
2. **Masking Button/Container (`.capsule`):** A relative, `overflow: hidden` element. This handles hover scaling, cursor pointers, and clips the rotating square gradient to the rounded-pill boundary.
   - When loading, it applies a `padding: 1.5px` (or the desired border width) and a transparent background.
3. **Rotating Gradient Layer (`.rainbowBorder`):** An absolute child of the masking container with large negative insets (e.g., `inset: -50%`). It spins infinitely (`360deg`) using standard hardware-accelerated CSS transforms.
4. **Inner Content Panel (`.capsuleInner`):** An absolute or flexing panel sitting on top of the border layer with `backdrop-filter: blur(20px)` and frosted-glass color. The content dictates the layout dimensions, scaling naturally.

```
+-------------------------------------------------+
| Capsule Wrapper (position: relative)            |
|  [ Glow Ring (blur(14px), orbiting conic-grad)]  |
|  +-------------------------------------------+  |
|  | Capsule Button (overflow: hidden, pad: 2px)|  |
|  |  +-------------------------------------+  |  |
|  |  | Rainbow Border Layer (spin transform) |  |  |
|  |  |  +----------------------------------+  |  |
|  |  |  | Capsule Inner (backdrop-filter)  |  |  |
|  |  |  |  [ Capsule Content ]             |  |  |
|  |  |  +----------------------------------+  |  |
|  |  +-------------------------------------+  |  |
|  +-------------------------------------------+  |
+-------------------------------------------------+
```

## Why This Matters
- **Dynamic Widths:** Since the text inside the capsule changes length depending on the processing percentage (e.g., `가공 중... (8%)` vs `가공 중... (100%)`), the outer pill scales dynamically and naturally based on internal text flow, rather than absolute coordinate calculations.
- **Visual Integrity:** Separating the outer glow (`.glowRing`) into a non-clipping wrapper ensures the frosted glass and traveling neon-light glow remain visible and crisp.
- **Cross-Browser & High Performance:** Animating `transform: rotate` rather than dynamic gradient color points leverages GPU hardware-acceleration, resulting in a locked 60FPS animation even on mobile devices.

## When to Apply
- When designing stateful pill-shaped components that require active loading states.
- When applying decorative neon/rainbow border shimmers to premium landing pages, buttons, or cards with dynamic content length.

## Examples

### CSS Implementation (`IntelligenceCapsule.module.css`)
```css
/* ── Capsule Wrapper (to prevent glow ring clipping) ── */
.capsuleWrapper {
  position: relative;
  display: flex;
  align-items: center;
}

/* ── Outer Capsule Button ── */
.capsule {
  position: relative;
  display: flex;
  align-items: center;
  height: 44px;
  padding: 0;
  border: none;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  z-index: 2;
  overflow: hidden;
}

.capsule.loading {
  padding: 1.5px; /* Creates the border width */
  background: transparent;
  backdrop-filter: none;
}

/* ── Inner Frosted Glass Layer ── */
.capsuleInner {
  display: flex;
  align-items: center;
  width: 100%;
  height: 100%;
  padding: 0 20px;
  border-radius: 21px; /* Fit perfectly inside outer radius */
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  z-index: 3;
}

/* ── Spinning Gradient Border ── */
.rainbowBorder {
  position: absolute;
  inset: -50%;
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

### React Layout Structure (`IntelligenceCapsule.tsx`)
```tsx
<div className={styles.capsuleWrapper}>
  {isActive && <div className={styles.glowRing} />}
  <button className={`${styles.capsule} ${isActive ? styles.loading : ''}`}>
    {isActive && <div className={styles.rainbowBorder} />}
    <div className={styles.capsuleInner}>
      <div className={styles.capsuleContent}>
        {isActive ? 'Processing...' : 'Done'}
      </div>
    </div>
  </button>
</div>
```

## Related
- [IntelligenceCapsule.tsx](file:///Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx)
- [IntelligenceCapsule.module.css](file:///Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.module.css)
