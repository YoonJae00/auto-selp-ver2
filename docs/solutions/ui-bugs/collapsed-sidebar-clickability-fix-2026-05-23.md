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
- **탭 클릭 불가능 및 UI 전체 프리징**: `/process` 또는 다른 dense workspace 페이지에 들어와서 사이드바가 접히면, 특정 수직 범위(예: Sticky Table Header가 있는 높이)의 사이드바 탭들을 클릭할 수 없거나, 아예 브라우저 탭 전체가 먹통이 되어 마우스 호버 반응 및 클릭 이벤트가 전혀 수신되지 않는 심각한 UI 프리징 현상이 발생했다.
- **아이콘 misalignment**: 사이드바가 접혔을 때 텍스트 레이블만 보이지 않게 처리되었으나, 아이콘(`H`, `AI`, `UP`, `PR`, `ST`)이 좌측으로 쏠리고 clickable 영역에서 어긋나서 클릭하기 힘들어졌다.

## What Didn't Work
- 단순 absolute/relative 위치만 변경하는 것으로는 해결되지 않았다.
- 사이드바 내부의 `Pointer-events` 설정 변경 시, 다른 부작용(사이드바의 버튼이 아예 클릭되지 않음 등)이 생겼다.

## Solution
이 문제는 다음 세 가지 원인이 복합적으로 겹쳐서 발생하였다:
1. **React Infinite Render Loop (최종적 프리징 원인)**: `/process` 페이지의 Celery 작업 동기화 훅에서 이전 활성 태스크 ID 목록을 저장하기 위한 `prevActiveTaskIds` 상태(`useState`)를 활용하고 있었다. 하지만 `useEffect` 내부에서 `activeTasks.map(t => t.id)`라는 매번 새로운 배열 참조(New Array Reference)를 가진 값을 `setPrevActiveTaskIds(activeIds)`로 업데이트했고, 이 상태인 `prevActiveTaskIds`를 `useEffect` 자체의 의존성 배열(dependency array)에 포함시켰다. 이로 인해 `상태 변경 -> useEffect 트리거 -> 상태 변경 -> useEffect 트리거...` 순의 **무한 렌더링 루프**에 빠져 브라우저 메인 스레드가 100% 점유되어 전체 UI가 정지하고 클릭 등 모든 이벤트 수신이 불가능해졌다.
2. **Stacking Context(z-index) 불일치**: `.sidebar`가 `position: relative`는 갖고 있으나 `z-index`가 명시되지 않아, `.main` 영역 안에 있는 `.productTable th` (sticky table header, `z-index: 1`) 등의 쌓임 맥락(stacking context)에 밀려서 가려지며 마우스 클릭 이벤트를 뺏겼다.
3. **Flexbox Layout misalignment**: 사이드바가 접힐(collapsed) 때 `.navLabel`을 `opacity: 0`과 `pointer-events: none`으로 숨겨두었지만, 여전히 DOM 공간을 차지하고 있었다. 그로 인해 flex container가 텍스트 공간까지 합쳐서 중앙 정렬을 연산하여, 아이콘이 강제로 왼쪽으로 밀려 사이드바 경계를 벗어났다.

이 문제들을 해결하기 위해 `frontend/src/app/(ai-mall)/ai-mall.module.css` 및 `frontend/src/app/(ai-mall)/process/page.tsx`을 수정하여 다음과 같이 변경을 가하였다:

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

### 3) React 무한 렌더링 루프 수정 (`useRef` 적용)
매 렌더링 주기마다 렌더링을 유발하지 않으면서 이전 상태의 얕은 비교를 안전하게 수행하기 위해 `prevActiveTaskIds`를 `useRef`로 교체하였다. 이를 통해 `useEffect`가 오직 `tasks`와 `fetchProducts`의 참조 변화 시에만 작동하도록 차단하고 메인 스레드 프리징을 완전히 해결했다.

```typescript
  // Automatically fetch products when a running task completes or fails to sync with DB
  const prevActiveTaskIdsRef = useRef<string[]>([]);
  useEffect(() => {
    const activeTasks = tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS');
    const activeIds = activeTasks.map(t => t.id);
    const prevActiveIds = prevActiveTaskIdsRef.current;
    
    // Check if any task that was active has finished (SUCCESS or FAILURE)
    const justFinished = prevActiveIds.some(id => {
      const task = tasks.find(t => t.id === id);
      return task && (task.status === 'SUCCESS' || task.status === 'FAILURE');
    });

    if (justFinished) {
      fetchProducts();
    }

    prevActiveTaskIdsRef.current = activeIds;
  }, [tasks, fetchProducts]);
```

## Why This Works
- **불필요한 re-render 유발 방지**: `useRef`를 도입하여 `prevActiveTaskIdsRef.current`가 변경되더라도 추가적인 re-render 루프가 활성화되지 않으며, 의존성 배열에서 이전 상태 자체를 배제시킴으로써 무한 루프 위험을 100% 제거하고 브라우저 메인 스레드에 자유를 보장한다. 이로써 메인 스레드 락이 풀려 모든 클릭 이벤트가 온전히 정상 처리된다.
- `z-index: 100`을 통해 `.sidebar`가 페이지의 다른 모든 relative/sticky content(특히 `z-index: 1`인 테이블 헤더)보다 앞선 쌓임 순서(stacking order)를 가지므로 마우스 클릭 이벤트를 방해받지 않는다.
- `display: none`으로 지정된 요소는 Flexbox의 flex 아이템으로 참여하지 않으므로, 사이드바가 64px 폭으로 접혀도 아이콘 단독으로 정확히 가로 세로 중앙 정렬을 수행할 수 있게 되어 시각적으로나 클릭 영역 면으로나 완벽하게 일치한다.

## Prevention
- **useEffect 내부의 무한 렌더링 방지**: `useEffect` 내에서 상태(`useState`)를 변경하고, 변경된 상태를 다시 `useEffect` 의존성 배열에 올리는 패턴은 대단히 위험하다. 이전 상태값을 비교/보관하려는 목적이라면 화면 렌더링에 직접 영향이 가지 않는 `useRef`를 우선적으로 활용한다.
- **사이드바 등 공통 UI 레이아웃의 z-index 명시**: 스크롤되거나 sticky한 요소가 있는 페이지(`.main`) 내부와 겹칠 가능성이 있는 레이아웃 사이드바는 반드시 충분한 높이의 `z-index`를 정의하여 stacking context를 확보한다.
- **비활성화 요소의 DOM Flow 영향 최소화**: 레이아웃을 접고 펼 때 단순히 `opacity: 0`을 사용하면 layout 계산(width, margin, gap 등)에 잔존하여 Flexbox/Grid 정렬을 망친다. 숨겨야 하는 텍스트나 큰 블록은 transition이 중요하지 않다면 `display: none`을 적용하는 것이 안전하다.

## Related Issues
- `frontend/src/app/(ai-mall)/ai-mall.module.css`
- `frontend/src/app/(ai-mall)/layout.tsx`
