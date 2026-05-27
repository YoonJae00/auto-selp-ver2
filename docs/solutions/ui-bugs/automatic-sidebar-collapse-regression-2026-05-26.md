---
title: "상품 가공 및 상품 관리 탭의 자동 사이드바 접힘 기능 오작동 해결 (workspace별 독립적 localStorage 설정)"
date: "2026-05-26"
category: "docs/solutions/ui-bugs"
module: "ai-mall-layout"
problem_type: "ui_bug"
component: "frontend_layout"
symptoms:
  - "상품 가공(/process) 및 상품 관리(/products) 탭 진입 시 사이드바가 자동으로 접히지 않고 펼쳐진 상태로 유지됨"
  - "한 번이라도 사이드바 토글 버튼을 누르면 그 이후로는 탭 전환 시의 자동 접힘/열림 로직이 작동하지 않음"
root_cause: "state_override_by_global_localstorage"
resolution_type: "code_fix"
severity: "medium"
tags: ["sidebar", "collapsed-sidebar", "localstorage", "layout", "nextjs"]
---

# 상품 가공 및 상품 관리 탭의 자동 사이드바 접힘 기능 오작동 해결

## Problem
사용자가 상품 가공(`/process`) 이나 상품 관리(`/products`) 등 복잡하고 넓은 화면 영역이 필요한 dense workspace 탭에 진입했을 때, 원래는 사이드바가 자동으로 접혀야(collapsed) 했으나 접히지 않고 펼쳐진 채 유지되는 현상이 발생했다.

## Symptoms
- 사이드바 접기/펼치기 토글 버튼을 한 번이라도 클릭하여 localStorage에 사용자 설정(`autoselp.sidebarCollapsed`)이 저장되고 나면, 이후에는 어느 페이지(홈, 상품 가공, 상품 관리 등)를 누르더라도 페이지 특성에 맞게 사이드바가 접히거나 열리지 않고 마지막에 토글했던 고정값으로만 고정됨.

## What Didn't Work
- `isDenseWorkspace` 값에만 의존하여 state를 강제로 변경하면, 사용자가 특정 dense 페이지에서 사이드바를 의도적으로 펼쳐두었을 때(또는 그 반대)의 일시적인 상태 제어(토글 버튼 클릭)가 페이지가 리렌더링되거나 상태가 미세하게 변경될 때 유실되는 부작용이 발생함.

## Root Cause
사이드바 상태(`sidebarCollapsed`) 및 사용자의 선호 토글 여부(`hasSidebarPreference`)를 제어하는 과정에서, 모든 워크스페이스에 대해 하나의 전역 localStorage 키(`autoselp.sidebarCollapsed`)를 공유하여 사용하고 있었다.
이로 인해:
1. 사용자가 토글 버튼을 한 번 클릭하면 `hasSidebarPreference`가 `true`가 되고, localStorage에 해당 고정 상태가 저장됨.
2. 이후 다른 탭으로 이동할 때, `useEffect`에서 localStorage 값(`stored`)이 `null`이 아니므로 무조건 그 고정 사용자 설정을 끌어와서 `sidebarCollapsed`를 덮어씀.
3. 결과적으로, 상품 가공(`/process`)이나 상품 관리(`/products`)처럼 가로 폭이 대단히 넓은 뷰포트가 필요한 dense workspace에서도 예전에 사용자가 선택했던 '사이드바 펼침(stored === false)' Preference가 전역적으로 적용되어 자동으로 접히지 않는 버그가 지속됨.

## Solution
워크스페이스의 성격에 맞춰 사용자의 선호(Preference)를 분리하여 관리하고, 전역/단일 localStorage 설정 대신 **화면의 밀도(Workspace Density)에 따라 독립된 localStorage 키**를 제공하도록 수정하였다.

수정 파일: [layout.tsx](file:///Users/yoonjae/Desktop/auto-selp-ver2/frontend/src/app/(ai-mall)/layout.tsx)

### 1) Workspace 밀도별 독립된 키 설정 및 단일 Effect 통합
복잡한 `hasSidebarPreference`와 다중 `useEffect`로 구성되어 덮어쓰기 버그를 유발하던 코드를 제거하고, 화면 성격(`isDenseWorkspace`)에 따른 단일 `useEffect`로 깔끔하게 통합하였다.

```typescript
  const isDenseWorkspace = DENSE_WORKSPACE_PATHS.some((path) => pathname?.startsWith(path));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  useEffect(() => {
    // 1. dense 영역(/process, /products 등)과 normal 영역(/home, /settings 등)의 키를 분리
    const key = isDenseWorkspace 
      ? 'autoselp.sidebarCollapsed.dense' 
      : 'autoselp.sidebarCollapsed.normal';
    
    const stored = window.localStorage.getItem(key);
    if (stored === null) {
      // 2. 명시적인 토글 이력이 없으면 각 워크스페이스의 기본 모드 적용 (dense = 자동접힘, normal = 자동펼침)
      setSidebarCollapsed(isDenseWorkspace);
    } else {
      // 3. 토글 이력이 있다면 사용자의 해당 영역 선호도 적용
      setSidebarCollapsed(stored === 'true');
    }
  }, [pathname, isDenseWorkspace]);
```

### 2) Sidebar Toggle 핸들러 수정
토글 시에도 현재 속한 화면 밀도(`isDenseWorkspace`)에 맞추어 개별 localStorage 키에 선호 상태를 저장하도록 개선하였다.

```typescript
  const toggleSidebar = () => {
    setSidebarCollapsed((current) => {
      const next = !current;
      const key = isDenseWorkspace 
        ? 'autoselp.sidebarCollapsed.dense' 
        : 'autoselp.sidebarCollapsed.normal';
      window.localStorage.setItem(key, String(next));
      return next;
    });
  };
```

## Why This Works
- **Context-Aware Preference**: 상품 가공/관리처럼 넓은 테이블 레이아웃을 가지는 `dense` 뷰포트의 사이드바 선호도와, 홈/설정처럼 레이블 인지가 중요한 `normal` 뷰포트의 사이드바 선호도가 개별 저장소(`autoselp.sidebarCollapsed.dense`, `autoselp.sidebarCollapsed.normal`)로 독립되었다.
- **Defaulting on Reset/First Visit**: 두 영역 모두 사용자가 수동으로 조절하기 전에는 `stored === null` 상태이므로, 상품 가공/관리 탭을 누르면 `isDenseWorkspace` 값(`true`)에 의해 완벽하게 **자동 접힘**이 보장된다.
- **No Global Leakage**: 한 영역의 토글이 다른 영역의 레이아웃 동작 방식(예: 상품 가공 탭에 들어갈 때 자동으로 작게 보여주어야 하는 기능)에 영향을 주지 않는다.

## Prevention
- **전역 UI 설정의 세분화**: 화면 레이아웃의 레이블이나 가로 폭 요구사항이 서로 극명하게 다른 하위 뷰들이 존재할 때, 하나의 전역 상태/localStorage 키를 모든 뷰에 획일적으로 공유하여 선호도를 저장하는 대신 페이지 특성(예: Normal vs Dense)에 기반한 세분화된 스키마/키 설정을 적용하여 원치 않는 덮어쓰기 현상을 예방한다.
