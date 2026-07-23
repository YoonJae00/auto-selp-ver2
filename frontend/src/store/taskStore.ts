import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export type ProcessingStage =
  | 'refining'
  | 'keywords'
  | 'categorizing'
  | 'extracting'
  | 'smartstore_candidates'
  | 'smartstore_validation';

export interface CompletedRowStage {
  name: ProcessingStage;
  ms: number;
  mapped_attributes?: Record<string, any>;
  candidates?: string[];
  product_name?: string;
  generation_method?: 'llm' | 'fallback';
}

export interface CompletedRow {
  name: string;
  total_ms: number;
  stages: CompletedRowStage[];
  error?: string;
}

export interface Task {
  id: string;
  filename: string;
  progress: number;
  total?: number;
  status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
  stage?: ProcessingStage | 'completed_row';
  currentName?: string;
  completedRows?: CompletedRow[];
  resultPath?: string;
  startTime: number;
  warnings?: Record<number, any[]>;
  result?: any;
  kind?: 'ai-processing' | 'smartstore-naming' | 'main-image-processing';
  poll?: boolean;
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
