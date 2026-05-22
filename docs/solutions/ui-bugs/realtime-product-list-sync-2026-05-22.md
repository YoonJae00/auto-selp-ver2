---
title: "새로고침 없이 가공 목록의 상태를 실시간으로 동기화하는 상태 관리 개선"
date: "2026-05-22"
category: "docs/solutions/ui-bugs"
module: "product-processing"
problem_type: "ui_bug"
component: "frontend_zustand"
symptoms:
  - "상품 가공 페이지에서 가공이 끝났음에도 상품 목록 테이블의 상태는 수동 새로고침을 하기 전까지 '대기' 또는 '가공 중'으로 멈춰 있음"
  - "사용자가 백그라운드 작업 완료를 화면에서 보고도 목록 상태가 변경되지 않아 시스템 에러로 오인할 수 있는 인지적 불일치 발생"
root_cause: "state_desynchronization"
resolution_type: "code_fix"
severity: "medium"
tags: ["realtime-sync", "zustand-polling", "product-processing", "react-usememo"]
---

# 새로고침 없이 가공 목록의 상태를 실시간으로 동기화하는 상태 관리 개선

## Problem
상품 가공 페이지(`/process`)에서 상품 가공을 시작하면 백그라운드에서 Celery 작업이 진행된다. 좌측 하단의 글로벌 Intelligence Capsule은 Zustand Store의 `useTaskPolling`을 통해 2초마다 백엔드 상태를 수신하여 완료를 띄워주지만, 실제 페이지 중앙의 상품 목록 그리드(`products` 로컬 스테이트)는 데이터베이스 최종본을 수동 새로고침하기 전까지 상태 변화(`완료`, `AI 정제 이름`, `키워드 배지`)를 감지하지 못했다.

이 문제를 양방향 소켓 통신(WebSocket)이나 서버 전송 이벤트(SSE)와 같은 헤비한 기술 없이, 이미 클라이언트 메모리에 도달하고 있는 데이터를 활용해 추가적인 서버 비용 전혀 없이 실시간 그리드 업데이트로 동화처럼 흐르게 만들고자 했다.

## Symptoms
- 사용자가 진행창을 통해 가공이 끝났음을 확인했음에도 상품 목록에서는 `대기` 상태가 지속됨.
- 수동 새로고침을 해야만 `완료` 배지와 정제된 AI 결과 필드들이 채워짐.
- 실시간 피드백 루프의 단절로 서비스 신뢰도 저하 및 사용 편의성 상실.

## Solution
서버 부하와 운영 비용이 발생하는 소켓 서버 개설 대신, **글로벌 Zustand Store에서 진행창용으로 이미 2초마다 꿀처럼 빨아오고 있는 실시간 태스크 정보를 로컬 상품 그리드 데이터와 결합(Merge)하여 화면에 그리는 방식**을 채택했다.

1. **태스크 데이터 구독**:
   `/process` 페이지 컴포넌트에서 `useTaskStore`로부터 실시간 백그라운드 태스크 정보(`tasks`)를 받아오도록 개선했다.

2. **메모리 상 매핑 로직 구축 (`completedRowsMap`)**:
   성능 최적화를 위해 실시간 태스크 진행 중에 도착하는 `completedRows`와 `currentName` 정보를 `useMemo` 기반의 단일 맵으로 구축했다. 상품명이 일치하면 실시간 AI 가공 완료 상태와 정제 값들을 오버레이한다.
   
   ```tsx
   const completedRowsMap = useMemo(() => {
     const map = new Map<string, {
       refined_name: string | null;
       keywords: string[] | null;
       status: 'completed' | 'failed' | 'processing';
       error?: string;
     }>();

     tasks.forEach((task) => {
       if (task.completedRows) {
         task.completedRows.forEach((row) => {
           const refiningStage = row.stages?.find(s => s.name === 'refining') as any;
           const keywordsStage = row.stages?.find(s => s.name === 'keywords') as any;
           
           map.set(row.name, {
             refined_name: refiningStage?.refined_name || null,
             keywords: keywordsStage?.keywords || null,
             status: row.error ? 'failed' : 'completed',
             error: row.error,
           });
         });
       }

       if (task.status === 'PROGRESS' && task.currentName) {
         if (!map.has(task.currentName)) {
           map.set(task.currentName, {
             refined_name: null,
             keywords: null,
             status: 'processing',
           });
         }
       }
     });

     return map;
   }, [tasks]);
   ```

3. **그리드 실시간 오버레이**:
   각 행의 렌더링에 `product` 원본 값 대신 `completedRowsMap`에 임시 데이터가 존재하는지 확인하여 `displayStatus`, `displayRefinedName`, `displayKeywords`를 그리도록 연결했다.
   - 가공 중인 항목은 텍스트가 `가공 중...`으로 변하고 배지가 주황색 `가공 중`으로 바뀐다.
   - 가공이 완료된 항목은 그 자리에서 즉각 `완료` 배지로 바뀌며 AI 정제명과 키워드가 스르륵 생성된다.

4. **최종 시점 완전 동기화 (Auto-Refetch)**:
   백그라운드 Celery 작업이 완전히 끝나는 순간(`SUCCESS` 또는 `FAILURE`) DB 상태와의 완전한 정합성과 페이지네이션 전체 카운트를 맞추기 위해, **딱 1회만 백엔드 상품 조회 API(`fetchProducts`)를 자동 호출**하여 최종 저장 데이터로 치환한다.
   ```tsx
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
   ```

## Lessons Learned
- **프론트엔드 오버레이 패턴의 경제성**: 대단한 실시간 기술 인프라(소켓 등)를 새로 세팅하지 않더라도, 글로벌 상태 관리와 메모리 병합 로직만 정교하게 맞추면 **백엔드 리소스 부하 0(Zero) 수준으로 완벽한 실시간 사용자 경험**을 구현할 수 있다.
- **인지적 완결성**: 진행 캡슐 배너와 눈앞의 상세 리스트 그리드의 라이프사이클이 정확히 연동됨으로써 사용자가 툴을 제어하고 있다는 신뢰도가 극대화되었다.
