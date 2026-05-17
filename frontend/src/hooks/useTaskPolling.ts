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
          const res = await api.get<{ 
            state: string; 
            meta?: { percent: number; warnings?: Record<number, any[]> };
            result?: any;
          }>(`/api/processor/status/${task.id}`);
          
          if (res.state === 'PROGRESS' && res.meta) {
            updateTask(task.id, { 
              progress: res.meta.percent, 
              status: 'PROGRESS',
              warnings: res.meta.warnings 
            });
          } else if (res.state === 'SUCCESS') {
            const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost'}/api/processor/download/${task.id}`;
            updateTask(task.id, { 
              progress: 100, 
              status: 'SUCCESS', 
              resultPath: downloadUrl,
              warnings: res.result?.warnings,
              result: res.result
            });
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
