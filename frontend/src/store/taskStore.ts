import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface Task {
  id: string;
  filename: string;
  progress: number;
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
  stage?: 'refining' | 'keywords' | 'verifying' | 'categorizing' | 'completed_row';
  currentName?: string;
  resultPath?: string;
  startTime: number;
  warnings?: Record<number, any[]>;
  result?: any;
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
    { 
      name: 'task-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
);
