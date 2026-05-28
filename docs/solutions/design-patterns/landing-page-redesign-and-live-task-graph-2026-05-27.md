---
title: Premium Landing Page Redesign with Interactive Live Task Graph
date: 2026-05-27
category: docs/solutions/design-patterns
module: frontend-marketing
problem_type: design_pattern
component: rails_view
severity: medium
applies_when:
  - "The landing page is basic or placeholder-like and needs high-quality branding"
  - "The product has a multi-stage AI pipeline that benefits from real-time flow visualization"
  - "The UI requires responsive, premium Apple-inspired minimalist aesthetics and glassmorphism"
tags: [frontend, landing-page, live-task-graph, css-animation, svg-flow, glassmorphism, responsive]
---

# Premium Landing Page Redesign with Interactive Live Task Graph

## Context
Auto-Selp's main marketing entrypoint was a placeholder page with basic typography and standard pill actions. This layout didn't convey the sophistication of the backend's 5-stage AI processing pipeline (Upload, LLM Refining, Keywords & KIPRIS validation, Category mapping, and Smart Upsert & Database synchronization). To address this, we overhauled the marketing layout with a high-fidelity Apple-inspired aesthetic and built a lightweight, interactive SVG/React DAG pipeline simulator that visually demonstrates the live data processing sequence.

## Guidance
Use an "Interactive Live Task Graph" pattern to visually illustrate complex multi-step backend pipelines on marketing and overview pages:
- **Pure CSS/SVG DAG Graphing:** Build the node-edge topology natively with pure HTML flexboxes and SVG path definitions instead of heavy external canvas dependencies.
- **Glowing edge flows:** Utilize `stroke-dashoffset` keyframes to slide dashed particles along SVG paths, mimicking live data traveling between pipeline nodes.
- **Pulsing ambient cues:** Decorate active nodes with custom-conic-gradients or radar animation loops for elegant ambient feedback.
- **Integrated details terminal:** Place a glassmorphic details pane alongside the node graph to display live changing parameters (inputs and refined outputs) at each step of the pipeline.
- **Alternating structural hierarchy:** Apply edge-to-edge section shifts (e.g. pure white ➔ parchment off-white ➔ deep black) to partition marketing elements without using busy border lines.
- **Frosted glass controls:** Wrap high-level buttons in subtle semi-transparent chips (`backdrop-filter`) with Action Blue accents (`#0066cc`) as the exclusive interactive color.

## Why This Matters
For complex SaaS tools, static copy and bullet points fail to capture the value of backend automation. Live flow visualization turns abstract steps into observable proof, instantly showing potential customers the speed and efficiency of the product. Using native SVG and CSS animations maintains a low page-weight, ensuring fast loads and smooth 60fps scrolling on both desktop and mobile devices.

## When to Apply
- When representing complex multi-stage background pipelines (Celery queues, data mappings, or Agent workflows).
- When upgrading basic landing pages into highly branded, visual marketing panels.
- When designing responsive landing page widgets without inflating bundle sizes with heavy charting libraries.

## Examples

### Before (Basic landing page)
```html
<main class={styles.hero}>
  <h1>이커머스 운영의 새로운 정의.</h1>
  <p>당신의 쇼핑몰을 AI와 함께 가장 스마트하게 관리하세요.</p>
  <Link href="/login">
    <PillButton>지금 시작하기</PillButton>
  </Link>
</main>
```

### After (Redesigned structure with LiveTaskGraph simulator)
- Frosted sticky navigation header (`layout.tsx`) with brand logo pulse animation and login buttons.
- Edge-to-edge Hero section (`page.tsx`) with `-0.025em` tight letter-spaced display typography.
- Glassmorphic simulator dashboard (`LiveTaskGraph.tsx`) with 5 animated processing stages:
  1. `도매처 업로드` -> supplier raw data parse
  2. `상품명 가공` -> LLM refining and character cleanup
  3. `키워드 & 상표권` -> search query integration & KIPRIS copyright filtering
  4. `카테고리 매핑` -> Naver/Coupang automated mapping
  5. `스마트 갱신` -> Smart Upsert price/stock state save
- High-fidelity 6-card feature grid with micro-interactions and hover scales.
- Dark-mode transitioning void Final CTA panel.

## Related
- `docs/superpowers/current_state.md`
- `TODO.md`
- `design.md`
