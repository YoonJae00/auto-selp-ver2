# Intelligence Capsule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a global background processing indicator ("Intelligence Capsule") with Siri-inspired animations and persistent task management.

**Architecture:** A global Zustand store (`taskStore`) manages task states and handles background polling. A React component (`IntelligenceCapsule`) integrated into the main layout provides visual feedback and interaction.

**Tech Stack:** Next.js (TypeScript), Zustand (Persistence), Vanilla CSS (Animations/Glassmorphism).

---

### Task 1: Create Global `taskStore`

**Files:**
- Create: `frontend/src/store/taskStore.ts`
- Modify: `frontend/src/store/authTypes.ts` (if needed for shared types)

- [x] **Step 1: Define types and create the store**
Create the `taskStore` with `persist` middleware to track tasks across sessions.

```typescript
// frontend/src/store/taskStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Task {
  id: string;
  filename: string;
  progress: number;
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
  resultPath?: string;
  startTime: number;
}

interface TaskState {
  tasks: Task[];
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  removeTask: (id: string) => void;
  clearCompleted: () => void;
}

export const useTaskStore = create<TaskState>()(
  persist(
    (set) => ({
      tasks: [],
      addTask: (task) => set((state) => ({ tasks: [...state.tasks, task] })),
      updateTask: (id, updates) => set((state) => ({
        tasks: state.tasks.map((t) => t.id === id ? { ...t, ...updates } : t)
      })),
      removeTask: (id) => set((state) => ({
        tasks: state.tasks.filter((t) => t.id !== id)
      })),
      clearCompleted: () => set((state) => ({
        tasks: state.tasks.filter((t) => t.status !== 'SUCCESS' && t.status !== 'FAILURE')
      })),
    }),
    { name: 'task-storage' }
  )
);
```

- [x] **Step 2: Commit store implementation**
```bash
git add frontend/src/store/taskStore.ts
git commit -m "feat: add taskStore with zustand persistence"
```

---

### Task 2: Implement Background Polling Hook

**Files:**
- Create: `frontend/src/hooks/useTaskPolling.ts`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Create polling hook**
This hook will monitor active tasks in the store and poll the API.

```typescript
// frontend/src/hooks/useTaskPolling.ts
import { useEffect } from 'react';
import { useTaskStore } from '@/store/taskStore';
import { api } from '@/lib/api';

export function useTaskPolling() {
  const { tasks, updateTask } = useTaskStore();

  useEffect(() => {
    const activeTasks = tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS');
    if (activeTasks.length === 0) return;

    const interval = setInterval(async () => {
      for (const task of activeTasks) {
        try {
          const res = await api.get<{ state: string; meta?: { percent: number } }>(`/api/processor/status/${task.id}`);
          if (res.state === 'PROGRESS' && res.meta) {
            updateTask(task.id, { progress: res.meta.percent, status: 'PROGRESS' });
          } else if (res.state === 'SUCCESS') {
            updateTask(task.id, { progress: 100, status: 'SUCCESS' });
          } else if (res.state === 'FAILURE') {
            updateTask(task.id, { status: 'FAILURE' });
          }
        } catch (err) {
          console.error(`Polling failed for task ${task.id}`, err);
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [tasks, updateTask]);
}
```

- [ ] **Step 2: Mount hook in RootLayout**
Ensure polling happens globally.

```typescript
// frontend/src/app/layout.tsx (Inside RootLayout component)
// Import and call useTaskPolling()
```

- [ ] **Step 3: Commit polling logic**
```bash
git add frontend/src/hooks/useTaskPolling.ts frontend/src/app/layout.tsx
git commit -m "feat: implement global task polling hook"
```

---

### Task 3: Create `IntelligenceCapsule` UI

**Files:**
- Create: `frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.tsx`
- Create: `frontend/src/components/UI/IntelligenceCapsule/IntelligenceCapsule.module.css`

- [ ] **Step 1: Implement CSS for Siri Glow and Glassmorphism**
Focus on `@keyframes` for the animated gradient border and `backdrop-filter`.

- [ ] **Step 2: Implement the React component**
Include collapsed and expanded states.

- [ ] **Step 3: Commit UI component**
```bash
git add frontend/src/components/UI/IntelligenceCapsule/
git commit -m "ui: implement IntelligenceCapsule with Siri glow"
```

---

### Task 4: Integration and Refactoring

**Files:**
- Modify: `frontend/src/app/(ai-mall)/layout.tsx` (Add Capsule)
- Modify: `frontend/src/app/(ai-mall)/process/page.tsx` (Remove local polling, use store)

- [ ] **Step 1: Add Capsule to Layout**
Place the component at the top center of the main content.

- [ ] **Step 2: Refactor Process Page**
Replace local `taskId` and `progress` states with `useTaskStore`.

- [ ] **Step 3: Final verification**
Run the app, start a process, navigate away, and verify the capsule continues to show progress.

- [ ] **Step 4: Commit integration**
```bash
git add frontend/src/app/(ai-mall)/layout.tsx frontend/src/app/(ai-mall)/process/page.tsx
git commit -m "refactor: integrate global task management and capsule UI"
```
