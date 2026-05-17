# Spec: Intelligence Capsule & Background Processing System

## Overview
This specification defines the implementation of a sophisticated, Apple Intelligence-inspired background processing system. It replaces the current blocking, page-level processing UI with a global, persistent status indicator ("Intelligence Capsule") that allows users to monitor task progress from anywhere in the application.

## 1. Global State Management (`taskStore`)
A new Zustand store will be implemented to manage processing tasks across the entire application.

- **Storage:** Uses `persist` middleware to save state to `localStorage`.
- **State Schema:**
  ```typescript
  interface Task {
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
  }
  ```
- **Background Polling:**
  - The store (or a global provider) will orchestrate polling for all active tasks (status: `PENDING` or `PROGRESS`).
  - Polling frequency: 2 seconds (matching current backend capabilities).

## 2. Visual Design: "The Intelligence Capsule"
A new UI component located at the top center of the `AiMallLayout` main content area.

### 2.1 Aesthetic Principles (Apple-inspired)
- **Glassmorphism:** `backdrop-filter: blur(20px)` with a subtle white/gray semi-transparent background.
- **Siri Glow:** A multi-colored animated gradient border/glow effect using CSS `@keyframes`.
- **Dynamic Transitions:** Smooth scaling and expansion animations using CSS transitions.

### 2.2 Components
- **Capsule (Collapsed):** A thin, pill-shaped bar showing the most urgent task's progress.
- **Intelligence Glow:** A subtle, pulsing aura of light (magenta, blue, cyan) that appears when processing is active.
- **Expanded Panel:** A list view that drops down when the capsule is clicked.
  - Shows multiple tasks if active.
  - Provides download buttons for completed tasks.
  - Provides a "Clear All" or "Dismiss" function for finished tasks.

## 3. Data Flow & Integration
1. **Initiation:** User clicks "Start Process" on `/process` page.
2. **Persistence:** `handleStartProcess` dispatches `addTask` to the global `taskStore` and redirects user (or allows them to stay).
3. **Global Feedback:** The `IntelligenceCapsule` detects the new task and starts the Siri Glow animation.
4. **Completion:** When a task hits 100% / `SUCCESS`, the capsule triggers a "Success Flash" (a gentle white glow) and updates the status to allow downloading.

## 4. Implementation Details
- **Frontend:** React, Zustand, Vanilla CSS.
- **Key Files to Modify/Create:**
  - `frontend/src/store/taskStore.ts` (New)
  - `frontend/src/components/UI/IntelligenceCapsule/` (New)
  - `frontend/src/app/(ai-mall)/layout.tsx` (Integration)
  - `frontend/src/app/(ai-mall)/process/page.tsx` (Update to use global store)

## 5. Success Criteria
- [ ] Users can start a process and navigate to "Home" without losing progress tracking.
- [ ] The UI feels premium and responsive, mimicking Apple's Intelligence animations.
- [ ] Background polling stops automatically when no tasks are active.
- [ ] Completed tasks are accessible for download via the capsule from any page.
