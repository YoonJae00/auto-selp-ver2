import { useEffect } from 'react';
import { useTaskStore } from '@/store/taskStore';
import { api } from '@/lib/api';

/**
 * Hook to poll the status of active tasks (PENDING or PROGRESS)
 * and update the task store with the latest progress and status.
 */
export function useTaskPolling() {
  const { tasks, updateTask } = useTaskStore();

  useEffect(() => {
    // Filter tasks that need polling
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
