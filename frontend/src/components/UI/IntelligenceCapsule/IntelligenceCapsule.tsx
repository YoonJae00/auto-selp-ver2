'use client';

import React, { useState, useMemo } from 'react';
import { useTaskStore, Task, CompletedRow } from '@/store/taskStore';
import styles from './IntelligenceCapsule.module.css';

// ─── Sub-components ─────────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  refining: '상품명 정제',
  keywords: '키워드 생성',
  categorizing: '카테고리 매핑',
};

const STAGE_ORDER = ['refining', 'keywords', 'categorizing'];

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** 완료된 행 하나 — accordion */
function CompletedRowItem({ row, index }: { row: CompletedRow; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.rowItem}>
      <button className={styles.rowHeader} onClick={() => setOpen(!open)}>
        <span className={styles.rowStatus}>
          {row.error ? '❌' : '✅'}
        </span>
        <span className={styles.rowName} title={row.name}>{row.name}</span>
        <span className={styles.rowTime}>{formatMs(row.total_ms)}</span>
        <span className={styles.rowChevron}>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className={styles.stageList}>
          {row.stages.map((s) => (
            <div key={s.name} className={styles.stageItem}>
              <span className={styles.stageDot}>✓</span>
              <span className={styles.stageLabel}>{STAGE_LABELS[s.name] ?? s.name}</span>
              <span className={styles.stageTime}>{formatMs(s.ms)}</span>
            </div>
          ))}
          {row.error && (
            <div className={`${styles.stageItem} ${styles.stageError}`}>
              <span className={styles.stageDot}>✗</span>
              <span className={styles.stageLabel}>{row.error}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** 현재 처리 중인 행 — 자동 펼침 + shimmer */
function ActiveRowItem({ name, stage }: { name: string; stage?: string }) {
  return (
    <div className={`${styles.rowItem} ${styles.rowItemActive}`}>
      <div className={styles.rowHeader}>
        <span className={styles.rowStatus}>🔄</span>
        <span className={`${styles.rowName} ${styles.shimmer}`} title={name}>{name}</span>
      </div>
      <div className={styles.stageList}>
        {STAGE_ORDER.map((s) => {
          const isActive = stage === s;
          const isPast = stage
            ? STAGE_ORDER.indexOf(s) < STAGE_ORDER.indexOf(stage)
            : false;
          return (
            <div
              key={s}
              className={`${styles.stageItem} ${isActive ? styles.stageActive : isPast ? styles.stagePast : styles.stagePending}`}
            >
              <span className={styles.stageDot}>
                {isPast ? '✓' : isActive ? '⟳' : '○'}
              </span>
              <span className={isActive ? `${styles.stageLabel} ${styles.shimmer}` : styles.stageLabel}>
                {STAGE_LABELS[s]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** 트리 상세 뷰 */
function DetailView({ task, onBack }: { task: Task; onBack: () => void }) {
  const completedRows = task.completedRows ?? [];
  const isProcessing = task.status === 'PROGRESS' || task.status === 'PENDING';

  return (
    <div className={styles.detailView}>
      <button className={styles.backBtn} onClick={onBack}>
        ← 목록으로
      </button>
      <div className={styles.detailHeader}>
        <p className={styles.detailFilename} title={task.filename}>{task.filename}</p>
        <div className={styles.detailProgressBar}>
          <div
            className={styles.detailProgressFill}
            style={{ width: `${task.progress}%` }}
          />
        </div>
        <span className={styles.detailProgressText}>
          {completedRows.length} / {task.status === 'SUCCESS' ? completedRows.length : '?'} 완료 · {task.progress}%
        </span>
      </div>

      <div className={styles.rowList}>
        {/* 완료된 행들 (최신 순) */}
        {[...completedRows].reverse().map((row, i) => (
          <CompletedRowItem key={i} row={row} index={i} />
        ))}

        {/* 현재 진행 중인 행 */}
        {isProcessing && task.currentName && task.stage !== 'completed_row' && (
          <ActiveRowItem name={task.currentName} stage={task.stage} />
        )}
      </div>

      {task.status === 'SUCCESS' && task.resultPath && (
        <div className={styles.downloadSection}>
          <a
            href={task.resultPath}
            className={styles.downloadBtn}
            target="_blank"
            rel="noopener noreferrer"
          >
            ⬇ 결과 다운로드
          </a>
        </div>
      )}
    </div>
  );
}

/** 작업 목록 뷰 */
function ListView({
  tasks,
  onSelectTask,
  onClearCompleted,
  onRemoveTask,
}: {
  tasks: Task[];
  onSelectTask: (id: string) => void;
  onClearCompleted: () => void;
  onRemoveTask: (id: string) => void;
}) {
  return (
    <div className={styles.listView}>
      <div className={styles.listHeader}>
        <span className={styles.listTitle}>Intelligence Tasks</span>
        <button className={styles.clearBtn} onClick={onClearCompleted}>
          완료 지우기
        </button>
      </div>
      <div className={styles.taskList}>
        {tasks.length === 0 && (
          <p className={styles.emptyState}>진행 중인 작업이 없습니다.</p>
        )}
        {[...tasks].reverse().map((task) => (
          <button
            key={task.id}
            className={styles.taskRow}
            onClick={() => onSelectTask(task.id)}
          >
            <div className={styles.taskRowTop}>
              <span className={styles.taskFilename} title={task.filename}>
                {task.filename}
              </span>
              <span className={`${styles.badge} ${styles[`badge_${task.status}`]}`}>
                {task.status === 'PROGRESS'
                  ? `${task.progress}%`
                  : task.status === 'SUCCESS'
                  ? '완료'
                  : task.status === 'PENDING'
                  ? '대기'
                  : '실패'}
              </span>
            </div>
            {(task.status === 'PROGRESS' || task.status === 'PENDING') && (
              <div className={styles.taskProgressBar}>
                <div
                  className={styles.taskProgressFill}
                  style={{ width: `${task.progress}%` }}
                />
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function IntelligenceCapsule() {
  const { tasks, removeTask, clearCompleted } = useTaskStore();
  const [isOpen, setIsOpen] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [isMounted, setIsMounted] = React.useState(false);

  React.useEffect(() => { setIsMounted(true); }, []);

  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status === 'PENDING' || t.status === 'PROGRESS'),
    [tasks]
  );

  if (!isMounted || tasks.length === 0) return null;

  const isActive = activeTasks.length > 0;
  const displayTask = activeTasks.length > 0
    ? activeTasks[activeTasks.length - 1]
    : tasks[tasks.length - 1];

  const selectedTask = selectedTaskId ? tasks.find((t) => t.id === selectedTaskId) : null;

  const handleCapsuleClick = () => {
    setIsOpen((prev) => !prev);
    if (isOpen) setSelectedTaskId(null);
  };

  return (
    <div className={`${styles.container} ${isActive ? styles.active : ''}`}>
      {/* Drawer (opens above the capsule) */}
      {isOpen && (
        <div className={styles.drawer}>
          {selectedTask ? (
            <DetailView
              task={selectedTask}
              onBack={() => setSelectedTaskId(null)}
            />
          ) : (
            <ListView
              tasks={tasks}
              onSelectTask={(id) => setSelectedTaskId(id)}
              onClearCompleted={clearCompleted}
              onRemoveTask={removeTask}
            />
          )}
        </div>
      )}

      {/* Capsule */}
      <button
        className={styles.capsule}
        onClick={handleCapsuleClick}
        aria-label="작업 현황 열기"
      >
        {/* Rotating glow ring (active only) */}
        {isActive && <div className={styles.glowRing} />}

        <div className={styles.capsuleContent}>
          {isActive ? (
            <>
              <span className={styles.capsuleIcon}>⚡</span>
              <span>가공 중... ({displayTask.progress}%)</span>
              <div className={styles.miniBar}>
                <div
                  className={styles.miniBarFill}
                  style={{ width: `${displayTask.progress}%` }}
                />
              </div>
            </>
          ) : (
            <>
              <span className={styles.capsuleIcon}>✅</span>
              <span>가공 완료</span>
            </>
          )}
        </div>
      </button>
    </div>
  );
}
