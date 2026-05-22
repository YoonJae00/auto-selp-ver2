---
title: "상품 가공 UX 개선 및 무한 렌더링 루프 버그 수정"
date: "2026-05-23"
category: "docs/solutions/ui-bugs"
module: "product-processing"
problem_type: "ui_bug"
component: "frontend_stimulus"
symptoms:
  - "상품 가공 탭에서 선택된 상품 가공 버튼의 동선이 불편하고 시인성이 떨어짐"
  - "이전/다음 페이지네이션이 화면 하단에만 존재하여 반복 클릭 시 매번 스크롤 필요"
  - "도매 상품이 많아 특정 키워드로 상품을 찾을 수 있는 검색 입력 필드가 부재함"
  - "백그라운드 태스크 수신 및 가공 완료 동기화 시 브라우저가 정지하며 무한 렌더링 루프 발생"
root_cause: "logic_error"
resolution_type: "code_fix"
severity: "high"
tags: ["product-processing", "pagination", "search-filter", "floating-action-bar", "infinite-render-loop", "react-ref"]
---

# 상품 가공 UX 개선 및 무한 렌더링 루프 버그 수정

## Problem
상품 가공(/process) 화면에서 대량의 상품을 관리할 때 핵심 동작(선택 가공, 페이지 이동, 검색)의 UX 접근성이 떨어지는 문제와, 실시간 백그라운드 가공 태스크 상태가 동기화되는 도중 프론트엔드가 먹통이 되며 브라우저 메모리가 고갈되는 무한 렌더링 루프 버그가 있었습니다.

## Symptoms
- 상품 가공 탭에서 항목을 10개 이상 선택한 후 아래로 스크롤하면 가공 시작 버튼이 화면에서 사라져 동선 낭비가 심했습니다.
- 페이지 하단에만 이전/다음 버튼이 있어 화면 상단 필터 변경 후 다음 페이지로 넘어가려면 불필요한 스크롤이 강제되었습니다.
- 실시간으로 완료된 가공 태스크를 동기화하기 위한 `useEffect`가 비동기 태스크 변경 감지 시 매번 이전 상태를 덮어쓰며 끝없는 React 렌더링 사이클에 돌입하여 화면이 정지(Freeze)했습니다.

## What Didn't Work
- **React State 활용**: `prevActiveTaskIds`를 React State로 관리하며 `useEffect` 의존성 배열에 입력하여 이전 태스크 목록과 현재 태스크 목록의 완료 여부를 비교했으나, 해당 `useEffect` 내부에서 `setPrevActiveTaskIds`를 호출함으로써 다시 렌더링이 일어나고 `tasks`의 새로운 참조로 인해 이펙트가 무한으로 재실행되는 악순환을 유발했습니다.
- **하단 단일 가공 버튼**: 단순히 테이블 툴바에만 버튼을 고정시키는 것만으로는 넓은 뷰포트에서 스크롤을 내렸을 때 빠른 가공 처리가 어려웠습니다.

## Solution
1. **React useRef를 활용한 무한 루프 차단**: 렌더링 흐름을 방해하지 않는 `prevActiveTaskIdsRef`를 생성하여 화면 재랜더링 없이 태스크 종료 감지 비교를 안전하게 처리했습니다.
2. **듀얼 액션 및 플로팅 바 UX 구현**:
   - 테이블 상단 툴바에 `선택 상품 가공` 정적 버튼 배치.
   - 1개 이상의 상품 선택 시 화면 하단 중앙에 부드럽게 솟아오르는 글래스모피즘(Floating Glassmorphic) 스타일의 `Floating Action Bar` 배치.
3. **현재 페이지 전체 선택 PillButton 구현**: 기존의 단순 체크박스 컨트롤 대신, 정교하게 디자인된 `PillButton` (세컨더리 타입)을 도입하여 현재 페이지 전체 상품을 원클릭으로 선택/해제 토글할 수 있도록 편의성을 극대화했습니다.
4. **동적 표시 개수 (Page Size) 셀렉트 필터 추가**: 기존 50개 고정이었던 대용량 조회를 동적 React State로 전환하여 기본 30개 보기로 설정하고, 상단 필터바 블록에 `10개 / 30개 / 50개 / 100개 / 200개` 보기 개수 드롭다운을 연동했습니다.
5. **상하단 동기화 페이지네이션**: 필터 바 우측 상단에 컴팩트 페이지 네비게이터를 배치하여 하단 컴포넌트와 상태를 양방향 연동.
6. **엔터/클리어 연동 검색 바**: API 쿼리 파라미터 `search`와 실시간 매핑되는 Enter 트리거 검색 창 탑재.

### React 무한 루프 해결 코드
```tsx
// AS-IS: State로 이전 태스크 목록을 의존성에 걸어 무한 루프 유발
const [prevActiveTaskIds, setPrevActiveTaskIds] = useState<string[]>([]);
useEffect(() => {
  const activeTasks = tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS');
  const activeIds = activeTasks.map(t => t.id);
  
  const justFinished = prevActiveTaskIds.some(id => {
    const task = tasks.find(t => t.id === id);
    return task && (task.status === 'SUCCESS' || task.status === 'FAILURE');
  });

  if (justFinished) {
    fetchProducts();
  }
  setPrevActiveTaskIds(activeIds);
}, [tasks, fetchProducts, prevActiveTaskIds]);

// TO-BE: useRef를 활용하여 렌더링 사이클과 차단된 상태 비교 적용
const prevActiveTaskIdsRef = useRef<string[]>([]);
useEffect(() => {
  const activeTasks = tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS');
  const activeIds = activeTasks.map(t => t.id);
  const prevActiveIds = prevActiveTaskIdsRef.current;
  
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

### CSS 플로팅 액션 바 및 레이아웃 개선
```css
.floatingActionBar {
  position: fixed;
  bottom: 32px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 12px 24px;
  border-radius: 999px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.04);
  animation: slideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes slideUp {
  from {
    transform: translate(-50%, 20px);
    opacity: 0;
  }
  to {
    transform: translate(-50%, 0);
    opacity: 1;
  }
}
```

## Why This Works
- `useRef.current` 변경은 React의 리렌더링을 유발하지 않으며, 이펙트의 실행 조건(의존성 배열)에서도 제외되어 상태 변화에 따른 무한 이펙트 실행 루프를 완벽히 끊었습니다.
- 하단 플로팅 바는 대용량 그리드 화면 스크롤 시 시선이나 마우스 동선을 수십 픽셀 내외로 제어할 수 있도록 도와주며, 취소 기능 및 가공 상태를 동적으로 제공하여 한눈에 액션을 파악할 수 있도록 만듭니다.

## Prevention
- **State vs Ref 사용 가이드**: `useEffect` 내에서 이전 상태값을 저장하거나 감지할 목적으로 상태를 업데이트할 경우, 리렌더링이 불필요한 값은 절대 React State가 아닌 `useRef`를 사용하여 기록하십시오.
- **듀얼 UX 설계 가이드**: 사용자의 대량 조작이 일어나는 테이블 혹은 그리드 환경에서는 중요한 처리를 실행하는 핵심 버튼을 상단에 고정하는 동시에 화면 이탈 시에도 대응할 수 있게 반응형 하단 플로팅 바로 묶어 조작 편의성을 극대화하십시오.

## Related Issues
- `docs/solutions/ui-bugs/process-product-list-filter-location-2026-05-22.md`
- `docs/solutions/ui-bugs/realtime-product-list-sync-2026-05-22.md`
