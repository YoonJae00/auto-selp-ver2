# 구현 계획: Intelligence Capsule & 상품 가공 UX 재설계

**작성일:** 2026-05-19  
**요구사항:** `docs/superpowers/specs/2026-05-19-intelligence-capsule-redesign.md`

---

## Task 1: 백엔드 - 단계별 타이밍 및 completed_rows 누적

**파일:** `services/processor/tasks.py`

### 변경 내용
- `_run_pipeline`에서 각 단계 시작 시 timestamp 기록
- 한 행 완료 시 `{name, total_ms, stages: [{name, ms}]}` 객체를 `completed_rows` 배열에 누적
- `update_state` meta에 `completed_rows` 포함

### 구현 포인트
```python
import time

# 각 행 처리 시작
row_start = time.time()
stage_times = {}

def update_stage(stage_name):
    stage_times[stage_name] = {'start': time.time()}
    task_instance.update_state(state='PROGRESS', meta={
        ...,
        'completed_rows': completed_rows  # 누적 배열 전달
    })

def complete_stage(stage_name):
    stage_times[stage_name]['ms'] = int((time.time() - stage_times[stage_name]['start']) * 1000)

# 행 완료 시
completed_rows.append({
    'name': original_name,
    'total_ms': int((time.time() - row_start) * 1000),
    'stages': [
        {'name': k, 'ms': v['ms']} for k, v in stage_times.items()
    ]
})
```

**완료 기준:** `update_state` meta에 `completed_rows` 배열이 포함되어야 함

---

## Task 2: 프론트엔드 Store - Task 인터페이스 및 Polling 업데이트

**파일:** `frontend/src/store/taskStore.ts`, `frontend/src/hooks/useTaskPolling.ts`

### 변경 내용 - taskStore.ts
```typescript
export interface CompletedRowStage {
  name: 'refining' | 'keywords' | 'categorizing';
  ms: number;
}

export interface CompletedRow {
  name: string;
  total_ms: number;
  stages: CompletedRowStage[];
}

export interface Task {
  id: string;
  filename: string;
  progress: number;
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
  stage?: 'refining' | 'keywords' | 'categorizing' | 'completed_row';
  currentName?: string;
  completedRows?: CompletedRow[];   // 추가
  resultPath?: string;
  startTime: number;
  warnings?: Record<number, any[]>;
  result?: any;
}
```

### 변경 내용 - useTaskPolling.ts
- `res.meta.completed_rows` → `updateTask({ completedRows: res.meta.completed_rows })`

**완료 기준:** 타입 에러 없이 빌드되어야 함

---

## Task 3: IntelligenceCapsule 전면 재설계

**파일:** `frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx`  
**파일:** `frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.module.css`

### 상태 구조
```typescript
type DrawerView = 'list' | 'detail';

const [isOpen, setIsOpen] = useState(false);
const [drawerView, setDrawerView] = useState<DrawerView>('list');
const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
```

### 캡슐 위치 및 스타일
```css
.container {
  position: fixed;
  bottom: 24px;
  left: calc(var(--sidebar-width) + 24px);
  z-index: 1000;
}
```

### Ambient Glow 애니메이션
```css
/* Apple Watch 스타일 - conic gradient 회전 */
.glow {
  position: absolute;
  inset: -4px;
  border-radius: 26px;
  background: conic-gradient(
    from 0deg,
    #a78bfa,  /* 보라 */
    #60a5fa,  /* 파랑 */
    #34d399,  /* 민트 */
    #a78bfa
  );
  filter: blur(12px);
  opacity: 0;
  animation: rotateGlow 6s linear infinite;
  z-index: -1;
}

.active .glow { opacity: 0.7; }

@keyframes rotateGlow {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

### 드로어 렌더링
- 캡슐 바로 위에 `position: absolute; bottom: 54px; left: 0;`로 드로어 배치
- 드로어 내부: `drawerView === 'list'` → 작업 목록, `drawerView === 'detail'` → 트리 뷰

**완료 기준:** 캡슐이 좌하단에 위치, 작업 중 glow 동작, 드로어 열리고 닫힘 확인

---

## Task 4: 드로어 - 작업 목록 뷰

**파일:** `IntelligenceCapsule.tsx` 내부

### 렌더링 구조
```tsx
// 작업 목록
{tasks.map(task => (
  <div onClick={() => { setSelectedTaskId(task.id); setDrawerView('detail'); }}>
    <span>{task.filename}</span>
    <StatusBadge status={task.status} />
    {task.status === 'PROGRESS' && <ProgressBar value={task.progress} />}
  </div>
))}
```

**완료 기준:** 작업 클릭 시 상세 뷰로 전환됨

---

## Task 5: 드로어 - 트리 상세 뷰 (핵심)

**파일:** `IntelligenceCapsule.tsx` 내부

### 렌더링 로직
```tsx
function TaskDetailView({ task }: { task: Task }) {
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  
  const currentIndex = task.completedRows?.length ?? 0;
  const totalRows = /* task.result?.total or estimate */ 0;

  return (
    <div>
      {/* 헤더 */}
      <button onClick={() => setDrawerView('list')}>← 목록으로</button>
      <h4>{task.filename}</h4>
      <ProgressBar value={task.progress} gradient />

      {/* 완료된 행들 */}
      {task.completedRows?.map((row, i) => (
        <RowItem 
          key={i}
          row={row}
          isExpanded={expandedRows.has(i)}
          onToggle={() => toggleExpand(i)}
          status="completed"
        />
      ))}

      {/* 현재 진행 중인 행 */}
      {task.status === 'PROGRESS' && task.currentName && (
        <RowItem
          row={{ name: task.currentName, stage: task.stage }}
          isExpanded={true}  // 자동 펼침
          status="active"
        />
      )}
    </div>
  );
}
```

### RowItem 컴포넌트
- **완료**: `✅ {name}  {total_ms}ms` + accordion으로 단계별 시간 표시
- **진행 중**: `🔄 {name}` shimmer 텍스트 + 단계들 (완료/진행중/대기)
- **대기**: `⏳ {name}` opacity: 0.4

**완료 기준:** 완료 상품 accordion 동작, 진행 중 shimmer 동작

---

## Task 6: Process 페이지 UX - 가공 시작 후 흐름 개선

**파일:** `frontend/src/app/(ai-mall)/process/page.tsx`

### 변경 내용
- 가공 시작(`handleStartProcess`) 후 토스트 메시지 표시 ("백그라운드에서 처리 중입니다.")
- PROCESSING 단계의 타임라인 분할 UI 제거 (복잡한 UI → 캡슐로 위임)
- PROCESSING 단계: 간결한 "작업이 시작되었습니다" + "좌측 하단 캡슐에서 진행 현황을 확인하세요" 안내

### 간단한 대체 UI (PROCESSING 단계)
```tsx
{step === 'PROCESSING' && (
  <section className={styles.section}>
    <div style={{ textAlign: 'center', padding: '60px 0' }}>
      <div style={{ fontSize: '48px', marginBottom: '16px' }}>⚡</div>
      <h3>백그라운드에서 가공 중입니다</h3>
      <p>좌측 하단 캡슐에서 실시간 진행 현황을 확인할 수 있습니다.</p>
      <p>다른 작업을 계속하셔도 됩니다.</p>
    </div>
  </section>
)}
```

**완료 기준:** PROCESSING 단계에서 불필요한 타임라인 없이 간결한 안내 메시지만 표시

---

## 구현 순서

```
Task 1 (Backend) → Task 2 (Store) → Task 3 (Capsule 기본) 
→ Task 4 (목록 뷰) → Task 5 (트리 뷰) → Task 6 (Process 페이지)
```

## 체크리스트

- [ ] Task 1: 백엔드 completed_rows 누적
- [ ] Task 2: 프론트 Store 타입 확장
- [ ] Task 3: 캡슐 좌하단 이동 + glow 애니메이션
- [ ] Task 4: 드로어 작업 목록 뷰
- [ ] Task 5: 트리 상세 뷰 (accordion + shimmer)
- [ ] Task 6: Process 페이지 PROCESSING 단계 단순화
