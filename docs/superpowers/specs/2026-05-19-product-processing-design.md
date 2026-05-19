# Product Processing Page Redesign Spec

## 1. Goal
Revamp the product processing page (`frontend/src/app/(ai-mall)/process`) from its current placeholder design to a "Bright & Modern" premium experience.

## 2. Visual Thesis
"Energetic Workspace" — glassmorphism cards, vivid gradients (purple-blue-cyan) for accents, and a bright white canvas. Step transitions use fade+slide animations. Process timeline features Apple Intelligence-style text shimmer animations.

## 3. Architecture & Data Flow
- **State Management**: Update `useTaskStore` to support fine-grained stages (`stage`, `currentName`).
- **Backend**: Update `tasks.py` in Celery worker to emit current stage information in `update_state` meta payload.
- **Frontend Components**:
  - Top Step Indicator (Upload → Mapping → Processing → Completed).
  - Step 1 (Upload): Interactive gradient-border dropzone.
  - Step 2 (Mapping): Card-grid layout for column mapping.
  - Step 3 (Processing): Split layout with progress bar on the left, and a real-time animated timeline on the right.
  - Step 4 (Completed): Success animation and action buttons.

## 4. Implementation Steps

### Phase 1: Backend Updates
- Modify `services/processor/tasks.py` `_run_pipeline` to emit granular states: `refining`, `keywords`, `verifying` (if applicable), `categorizing`.
- Pass the current product's original name (`current_name`) in the progress payload.

### Phase 2: Store & API Client Updates
- Update `frontend/src/store/taskStore.ts` interface `Task` and `frontend/src/lib/api.ts` types to expect `stage` and `currentName` in metadata.

### Phase 3: CSS Tokens & Core Styles
- Update `tokens.css` with new gradients: `--accent-gradient: linear-gradient(135deg, #6366f1, #3b82f6, #06b6d4)`.
- Define animations (`fadeSlideUp`, `shimmerText`) in `globals.css` or `process.module.css`.

### Phase 4: Page Structure & Animations
- Rewrite `page.tsx` to use the top step indicator.
- Apply step transition animations.
- Rebuild Step 1 and Step 2 UI using glassmorphic cards.

### Phase 5: Processing Timeline UI
- Build the split layout for Step 3.
- Implement the "Apple Intelligence" style shimmering text for the active stage.
- Tie the UI to the live updates coming from the task store.

## 5. Ambiguity Check
- *How does the polling work?* Polling is handled globally by `TaskPollingProvider` which updates `useTaskStore`. We just read from the store.
- *What happens to existing variables?* We keep the same functionality but wrap it in better UI.
