# Spec: The Intelligence Action Button

## Overview
This specification details the transformation of the "Start Process" button into a dynamic, Apple Intelligence-inspired floating action button (FAB) during product processing.

## 1. Interaction Flow: The Evolution
- **Initial State:** The button sits in its standard position on the `/process` page ("가공 시작하기").
- **Trigger:** User clicks the button.
- **Transition (Approach A):** The button detaches from the document flow (`position: fixed`) and smoothly animates to the bottom-right corner of the screen (`bottom: 40px, right: 40px`).
- **Transformation:** The button shrinks slightly into a more compact pill/capsule shape.

## 2. Visual Design (During Processing)
- **Glassmorphism:** The button background becomes semi-transparent (`rgba(255,255,255,0.7)`) with a strong background blur (`backdrop-filter: blur(15px)`).
- **Intelligence Border:** A 1px border exhibiting a rainbow gradient.
- **Pulsing Glow (The Breathing Effect):** A glowing aura behind the button.
  - Colors: Magenta, Blue, Cyan gradient.
  - Animation: A slow, breathing pulse (scaling up and down slightly, opacity fading in and out over a 2-3 second cycle). It should feel like a strong, steady breath, not a frantic flash.

## 3. State Management & Content
- **Processing State:** Text changes to reflect progress (e.g., "가공 중... 45%").
- **Completion State:** The pulsing glow transitions to a soft, steady green aura. The text updates to indicate completion, and clicking it will trigger the download.
- **Global Context:** This button acts as a visual representation of the `taskStore` state, specifically for the active task initiated from this page.

## 4. Technical Approach
- Use Vanilla CSS modules for complex `@keyframes` and transitions.
- Use React state to toggle classes that trigger the `fixed` positioning and animations.
- Ensure the glow is implemented using a pseudo-element (`::before` or `::after`) placed behind the main button content to avoid blurring the text.
