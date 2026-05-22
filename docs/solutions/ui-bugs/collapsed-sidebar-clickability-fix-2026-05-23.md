---
title: "상품 가공 탭에서 다른 탭이 클릭되지 않던 문제 해결 (사이드바 z-index 및 collapsed flow 버그)"
date: "2026-05-23"
category: "docs/solutions/ui-bugs"
module: "ai-mall-layout"
problem_type: "ui_bug"
component: "frontend_layout"
symptoms:
  - "상품 가공 탭(/process) 등 일부 탭 진입 시 홈 이나 상품관리 탭이 클릭되지 않음"
  - "사이드바가 접힌(collapsed) 상태에서 아이콘 정렬이 어긋나며 클릭 영역이 일치하지 않음"
root_cause: "z_index_conflict"
resolution_type: "code_fix"
severity: "high"
tags: ["sidebar", "z-index", "collapsed-sidebar", "pointer-events", "flexbox-alignment"]
---

# 상품 가공 탭에서 다른 탭이 클릭되지 않던 문제 해결

## Problem
사용자가 상품 가공(`localhost:3000/process`) 탭에 들어갔을 때, 사이드바의 홈(`/home`), 상품 관리(`/products`) 등 다른 탭이 클릭되지 않는 현상이 발생하였다. 또한 사이드바가 접혔을(collapsed) 때 메뉴 아이콘의 중앙 정렬이 깨져서 마우스 클릭 hitbox와 실제 아이콘 위치가 불일치하는 인터랙션 불편함이 있었다.

## Symptoms
- **탭 클릭 불가능**: `/process` 또는 다른 dense workspace 페이지에 들어와서 사이드바가 접히면, 특정 수직 범위(예: Sticky Table Header가 있는 높이)의 사이드바 탭들을 클릭할 수 없었다.
- **아이콘 misalignment**: 사이드바가 접혔을 때 텍스트 레이블만 보이지 않게 처리되었으나, 아이콘(`H`, `AI`, `UP`, `PR`, `ST`)이 좌측으로 쏠리고 clickable 영역에서 어긋나서 클릭하기 힘들어졌다.

## What Didn't Work
- 단순 absolute/relative 위치만 변경하는 것으로는 해결되지 않았다.
- 사이드바 내부의 `Pointer-events` 설정 변경 시, 다른 부작용(사이드바의 버튼이 아예 클릭되지 않음 등)이 생겼다.

## Solution
이 문제는 다음 두 가지 원인이 겹쳐서 발생하였다:
1. **Stacking Context(z-index) 불일치**: `.sidebar`가 `position: relative`는 갖고 있으나 `z-index`가 명시되지 않아, `.main` 영역 안에 있는 `.productTable th` (sticky table header, `z-index: 1`) 등의 쌓임 맥락(stacking context)에 밀려서 가려지며 마우스 클릭 이벤트를 뺏겼다.
2. **Flexbox Layout misalignment**: 사이드바가 접힐(collapsed) 때 `.navLabel`을 `opacity: 0`과 `pointer-events: none`으로 숨겨두었지만, 여전히 DOM 공간을 차지하고 있었다. 그로 인해 flex container가 텍스트 공간까지 합쳐서 중앙 정렬을 연산하여, 아이콘이 강제로 왼쪽으로 밀려 사이드바 경계를 벗어났다.

이 두 문제를 해결하기 위해 `frontend/src/app/(ai-mall)/ai-mall.module.css`을 수정하여 다음과 같이 변경을 가하였다:

### 1) Sidebar Stacking Context 보장
사이드바가 언제나 최상단 레이어에 위치하도록 명시적으로 `z-index: 100`을 부여했다.

```css
.sidebar {
  position: relative;
  z-index: 100; /* Main content와 sticky header 위에 위치 보장 */
  width: var(--active-sidebar-width);
  background: rgba(255, 255, 255, 0.86);
  border-right: 1px solid var(--hairline);
  ...
}
```

### 2) Collapsed Layout 개선 (`display: none` 적용)
`.sidebarCollapsed .navLabel`에 `display: none`을 부여하여 flex item 계산에서 완전히 제외시켰다. 이로 인해 `justify-content: center`가 아이콘 단독 기준으로 정상 작동하여 완벽하게 중앙 정렬이 되며 클릭 hitbox가 정렬되었다.

```css
.sidebarCollapsed .brandText,
.sidebarCollapsed .userInfo {
  opacity: 0;
  pointer-events: none;
  transform: translateX(-8px);
}

.sidebarCollapsed .navLabel {
  display: none; /* opacity/pointer-events 대신 flex container 공간에서 완전히 배제 */
}
```

## Why This Works
- `z-index: 100`을 통해 `.sidebar`가 페이지의 다른 모든 relative/sticky content(특히 `z-index: 1`인 테이블 헤더)보다 앞선 쌓임 순서(stacking order)를 가지므로 마우스 클릭 이벤트를 방해받지 않는다.
- `display: none`으로 지정된 요소는 Flexbox의 flex 아이템으로 참여하지 않으므로, 사이드바가 64px 폭으로 접혀도 아이콘 단독으로 정확히 가로 세로 중앙 정렬을 수행할 수 있게 되어 시각적으로나 클릭 영역 면으로나 완벽하게 일치한다.

## Prevention
- **사이드바 등 공통 UI 레이아웃의 z-index 명시**: 스크롤되거나 sticky한 요소가 있는 페이지(`.main`) 내부와 겹칠 가능성이 있는 레이아웃 사이드바는 반드시 충분한 높이의 `z-index`를 정의하여 stacking context를 확보한다.
- **비활성화 요소의 DOM Flow 영향 최소화**: 레이아웃을 접고 펼 때 단순히 `opacity: 0`을 사용하면 layout 계산(width, margin, gap 등)에 잔존하여 Flexbox/Grid 정렬을 망친다. 숨겨야 하는 텍스트나 큰 블록은 transition이 중요하지 않다면 `display: none`을 적용하는 것이 안전하다.

## Related Issues
- `frontend/src/app/(ai-mall)/ai-mall.module.css`
- `frontend/src/app/(ai-mall)/layout.tsx`
