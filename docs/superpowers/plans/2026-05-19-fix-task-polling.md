# Fix Task Polling Stability and Auth Guard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the task polling frequency by removing the `tasks` dependency from `useEffect` and adding an authentication guard.

**Architecture:** Use Zustand's `getState()` inside the `setInterval` callback to access the latest tasks without triggering effect re-runs. Utilize `useAuthStore` to conditionalize polling based on the user's authentication status.

**Tech Stack:** React, Zustand, TypeScript.

---

### Task 1: Update useTaskPolling Hook

**Files:**
- Modify: `frontend/src/hooks/useTaskPolling.ts`

- [ ] **Step 1: Import useAuthStore and update the hook logic**

Replace the existing `useTaskPolling` implementation with a version that checks for authentication and uses `useTaskStore.getState()` for stable polling.

```typescript
import { useEffect } from 'react';
import { useTaskStore } from '@/store/taskStore';
import { useAuthStore } from '@/store/authStore';
import { api } from '@/lib/api';

/**
 * Hook to poll the status of active tasks (PENDING or PROGRESS)
 * and update the task store with the latest progress and status.
 */
export function useTaskPolling() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const updateTask = useTaskStore((state) => state.updateTask);

  useEffect(() => {
    // Only poll if the user is authenticated
    if (!isAuthenticated) return;

    const interval = setInterval(async () => {
      // Get the latest tasks from the store state to avoid triggering effect re-runs
      const { tasks } = useTaskStore.getState();
      const activeTasks = tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS');
      
      if (activeTasks.length === 0) return;

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
  }, [isAuthenticated, updateTask]);
}
```

- [ ] **Step 2: Verify the change**

Check that the file compiles and the logic correctly uses `isAuthenticated` and `getState()`.

- [ ] **Step 3: Commit the changes**

```bash
git add frontend/src/hooks/useTaskPolling.ts
git commit -m "fix(frontend): stabilize task polling and add auth guard"
```
