# Design Spec: Animated Gradient Border Pill Loading Indicator for Intelligence Capsule

- **Date:** 2026-05-31
- **Feature:** Animated Gradient Border Pill Loading Indicator
- **Target Component:** `IntelligenceCapsule` (`frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx`)
- **Status:** Approved by User

---

## 1. Overview
The goal is to modify the existing `IntelligenceCapsule` component in the frontend so that when tasks are actively processing (i.e. the loading state is active), the capsule displays a vibrant, rotating rainbow gradient border (animated gradient border pill loading indicator). Once processing completes, the capsule smoothly transitions back to its standard static frosted-glass appearance.

---

## 2. Visual & Interaction Design
- **Active / Processing State (`isActive` is true):**
  - Border: 1.5px thick, rotating conic gradient with a full spectrum of vibrant colors (red, orange, green, blue, purple, red).
  - Rotation Animation: Infinite linear rotation taking 3 seconds per full 360-degree rotation.
  - Soft Outer Glow: Keep the existing `.glowRing` orbiting glow behind the capsule to add premium depth.
  - Inner Capsule: Semi-transparent white backdrop (`rgba(255, 255, 255, 0.9)`) with a high-blur backdrop-filter (`blur(20px)`).
- **Completed / Inactive State (`isActive` is false):**
  - Border: Standard 1px high-transparency border (`rgba(255,255,255,0.6)` inset).
  - Background: Standard frosted-glass background.
- **Hover Transition:**
  - Micro-animation: Smoothly scale up to `1.03` with a soft box-shadow transition.

---

## 3. DOM & CSS Architecture (Approach A)
To implement this without visual artifacts, we will nest the capsule's content inside an inner container (`capsuleInner`) and make the outer container (`capsule`) overflow-hidden to act as the mask for the rotating border:

```
+-------------------------------------------------+
| Capsule Button (overflow: hidden, padding: 1.5px)|
|  +-------------------------------------------+  |
|  | Rainbow Border Layer (rotating conic-grad)|  |
|  |  +-------------------------------------+  |  |
|  |  | Capsule Inner (backdrop-filter)     |  |  |
|  |  |  [ Capsule Content ]                |  |  |
|  |  +-------------------------------------+  |  |
|  +-------------------------------------------+  |
+-------------------------------------------------+
```

### Key Components:
1. **Outer Container (`.capsule`):**
   - Sets the relative boundary and pill layout.
   - When active, gets `.loading` class, which changes the padding to `1.5px` and turns container background transparent.
   - Set `overflow: hidden` to clip the rotating square border background into the capsule's rounded-pill shape.
2. **Rotating Border (`.rainbowBorder`):**
   - Absolutely positioned with negative insets (e.g. `inset: -50%`) to cover all corners while rotating.
   - Background: `conic-gradient(from 0deg, #ff3b30, #ff9500, #34c759, #007aff, #af52de, #ff3b30)`.
   - CSS Animation: `spinRainbow 3s linear infinite`.
3. **Inner Container (`.capsuleInner`):**
   - Stretches to `100% width` and `100% height`.
   - Has a slightly smaller border-radius to fit perfectly inside the outer container.
   - Holds the actual content and applying the `backdrop-filter: blur(20px)` frosted-glass effect.

---

## 4. Verification Checklist
- [ ] Capsule shows standard static glassmorphism when there are no active tasks.
- [ ] Capsule border turns into a spinning rainbow gradient when tasks are actively processing.
- [ ] The backdrop-filter (blur) works correctly behind the active capsule.
- [ ] Hover effect (`scale(1.03)`) operates smoothly.
- [ ] No visual glitches or corner overflows occur during dynamic capsule resizing.
