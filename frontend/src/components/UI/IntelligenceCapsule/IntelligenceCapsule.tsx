'use client';

import React, { useState, useMemo } from 'react';
import { useTaskStore, Task, CompletedRow } from '@/store/taskStore';
import styles from './IntelligenceCapsule.module.css';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const STAGE_META: Record<string, { label: string; icon: string }> = {
  refining:     { label: '상품명 가공',      icon: '✏️' },
  keywords:     { label: '키워드 생성',      icon: '🔍' },
  categorizing: { label: '카테고리 매핑',    icon: '📂' },
  extracting:   { label: '속성 추출',        icon: '✨' },
};

const STAGE_ORDER = ['refining', 'keywords', 'categorizing', 'extracting'];

function formatMs(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

// ─── Stage detail renderer ────────────────────────────────────────────────────

function StageDetail({ stage }: { stage: any }) {
  const meta = STAGE_META[stage.name] ?? { label: stage.name, icon: '▸' };
  return (
    <div className={styles.stageBody}>
      <div className={styles.stageLabel}>{meta.icon} {meta.label}</div>
      {stage.name === 'refining' && stage.refined_name && (
        <div className={styles.stageDetail}>→ <strong>{stage.refined_name}</strong></div>
      )}
      {stage.name === 'keywords' && stage.keywords?.length > 0 && (
        <div className={styles.stageDetail}>
          {stage.keywords.join(', ')}
          {stage.filtered?.length > 0 && (
            <span style={{ color: '#ff3b30', marginLeft: 6 }}>
              ({stage.filtered.join(', ')} 제거됨)
            </span>
          )}
        </div>
      )}
      {stage.name === 'categorizing' && (
        <div className={styles.stageDetail}>
          {stage.naver_category && <>네이버: <strong>{stage.naver_category}</strong></>}
          {stage.naver_category && stage.coupang_category && ' · '}
          {stage.coupang_category && <>쿠팡: <strong>{stage.coupang_category}</strong></>}
        </div>
      )}
      {stage.name === 'extracting' && stage.mapped_attributes && (() => {
        const naverCount = stage.mapped_attributes.naver_attributes?.length || 0;
        const coupangProd = stage.mapped_attributes.coupang_attributes?.product_attributes?.length || 0;
        const coupangItem = stage.mapped_attributes.coupang_attributes?.item_attributes?.length || 0;
        const coupangCount = coupangProd + coupangItem;

        return (
          <div className={styles.stageDetail}>
            {naverCount > 0 && (
              <>네이버 속성: <strong>{naverCount}개</strong></>
            )}
            {naverCount > 0 && coupangCount > 0 && ' · '}
            {coupangCount > 0 && (
              <>쿠팡 속성: <strong>{coupangCount}개</strong></>
            )}
            {naverCount === 0 && coupangCount === 0 && (
              <span style={{ color: '#8e8e93' }}>추출된 속성 없음</span>
            )}
          </div>
        );
      })()}
    </div>
  );
}

// ─── Completed Row (accordion) ────────────────────────────────────────────────

function CompletedRowItem({ row }: { row: CompletedRow }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.rowItem}>
      <button className={styles.rowHeader} onClick={() => setOpen(!open)}>
        <span className={styles.rowStatus}>{row.error ? '❌' : '✅'}</span>
        <span className={styles.rowName} title={row.name}>{row.name}</span>
        <span className={styles.rowTime}>{formatMs(row.total_ms)}</span>
        <span className={styles.rowChevron}>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className={styles.stageList}>
          {row.stages?.map((s: any) => (
            <div key={s.name} className={`${styles.stageItem} ${styles.stagePast}`}>
              <span className={styles.stageDot}>✓</span>
              <StageDetail stage={s} />
              <span className={styles.stageTime}>{formatMs(s.ms)}</span>
            </div>
          ))}
          {row.error && (
            <div className={`${styles.stageItem} ${styles.stageError}`}>
              <span className={styles.stageDot}>✗</span>
              <div className={styles.stageBody}>
                <div className={styles.stageLabel}>오류 발생</div>
                <div className={styles.stageDetail}>{row.error}</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Active Row (auto-expanded + shimmer) ─────────────────────────────────────

function ActiveRowItem({ task }: { task: Task }) {
  const { currentName, stage } = task;
  return (
    <div className={`${styles.rowItem} ${styles.rowItemActive}`}>
      <div className={styles.rowHeader} style={{ cursor: 'default' }}>
        <span className={styles.rowStatus}>🔄</span>
        <span className={`${styles.rowName} ${styles.shimmer}`} title={currentName}>{currentName}</span>
      </div>
      <div className={styles.stageList}>
        {STAGE_ORDER.map((s) => {
          const currentIdx = stage ? STAGE_ORDER.indexOf(stage) : -1;
          const sIdx = STAGE_ORDER.indexOf(s);
          const isPast   = currentIdx > sIdx;
          const isActive = currentIdx === sIdx;
          const isPending = currentIdx < sIdx;
          const meta = STAGE_META[s];
          return (
            <div
              key={s}
              className={`${styles.stageItem} ${isPast ? styles.stagePast : isActive ? styles.stageActive : styles.stagePending}`}
            >
              <span className={styles.stageDot}>
                {isPast ? '✓' : isActive ? '⟳' : '○'}
              </span>
              <div className={styles.stageBody}>
                <div className={isActive ? `${styles.stageLabel} ${styles.shimmer}` : styles.stageLabel}>
                  {meta.icon} {meta.label}{isActive ? ' 중...' : ''}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Full-screen Detail Modal ─────────────────────────────────────────────────

function DetailModal({ task, onClose }: { task: Task; onClose: () => void }) {
  const completedRows = task.completedRows ?? [];
  const isProcessing = task.status === 'PROGRESS' || task.status === 'PENDING';
  const total = task.total ?? '?';

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalPanel} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <button className={styles.backBtn} onClick={onClose}>← 목록</button>
          <span className={styles.modalFilename} title={task.filename}>{task.filename}</span>
          <span className={`${styles.badge} ${styles[`badge_${task.status}`]}`}>
            {task.status === 'PROGRESS' ? `${task.progress}%`
              : task.status === 'SUCCESS' ? '완료'
              : task.status === 'PENDING' ? '대기' : '실패'}
          </span>
          <button className={styles.modalClose} onClick={onClose}>×</button>
        </div>

        {/* Progress */}
        <div className={styles.modalProgress}>
          <div className={styles.modalProgressBar}>
            <div className={styles.modalProgressFill} style={{ width: `${task.progress}%` }} />
          </div>
          <span className={styles.modalProgressText}>
            {completedRows.length} / {total} 완료 · {task.progress}%
          </span>
        </div>

        {/* Row list */}
        <div className={styles.rowList}>
          {/* Current active row (top, auto-expanded) */}
          {isProcessing && task.currentName && task.stage !== 'completed_row' && (
            <ActiveRowItem task={task} />
          )}

          {/* Completed rows in reverse order (most recent first) */}
          {[...completedRows].reverse().map((row, i) => (
            <CompletedRowItem key={i} row={row} />
          ))}
        </div>

        {/* Download */}
        {task.status === 'SUCCESS' && task.resultPath && (
          <div className={styles.downloadSection}>
            <a href={task.resultPath} className={styles.downloadBtn} target="_blank" rel="noopener noreferrer">
              ⬇ 결과 파일 다운로드
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── List View ────────────────────────────────────────────────────────────────

function ListView({
  tasks,
  onSelect,
  onClear,
}: {
  tasks: Task[];
  onSelect: (id: string) => void;
  onClear: () => void;
}) {
  return (
    <div className={styles.listView}>
      <div className={styles.listHeader}>
        <span className={styles.listTitle}>Intelligence Tasks</span>
        <button className={styles.clearBtn} onClick={onClear}>완료 지우기</button>
      </div>
      <div className={styles.taskList}>
        {tasks.length === 0 && <p className={styles.emptyState}>진행 중인 작업이 없습니다.</p>}
        {[...tasks].reverse().map((task) => (
          <button key={task.id} className={styles.taskRow} onClick={() => onSelect(task.id)}>
            <div className={styles.taskRowTop}>
              <span className={styles.taskFilename} title={task.filename}>{task.filename}</span>
              <span className={`${styles.badge} ${styles[`badge_${task.status}`]}`}>
                {task.status === 'PROGRESS' ? `${task.progress}%`
                  : task.status === 'SUCCESS' ? '완료'
                  : task.status === 'PENDING' ? '대기' : '실패'}
              </span>
            </div>
            {(task.status === 'PROGRESS' || task.status === 'PENDING') && (
              <div className={styles.taskProgressBar}>
                <div className={styles.taskProgressFill} style={{ width: `${task.progress}%` }} />
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function IntelligenceCapsule() {
  const { tasks, removeTask, clearCompleted } = useTaskStore();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [isMounted, setIsMounted] = React.useState(false);

  React.useEffect(() => { setIsMounted(true); }, []);

  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status === 'PENDING' || t.status === 'PROGRESS'),
    [tasks]
  );

  if (!isMounted || tasks.length === 0) return null;

  const isActive = activeTasks.length > 0;
  const displayTask = isActive ? activeTasks[activeTasks.length - 1] : tasks[tasks.length - 1];
  const selectedTask = selectedTaskId ? tasks.find((t) => t.id === selectedTaskId) : null;

  const handleCapsuleClick = () => {
    setIsDrawerOpen((prev) => !prev);
    if (isDrawerOpen) setSelectedTaskId(null);
  };

  const handleSelectTask = (id: string) => {
    setSelectedTaskId(id);
    setIsDrawerOpen(false); // close drawer, modal takes over
  };

  const handleCloseModal = () => {
    setSelectedTaskId(null);
    setIsDrawerOpen(true); // return to drawer
  };

  return (
    <>
      {/* Full-screen detail modal (rendered outside container for z-index) */}
      {selectedTask && (
        <DetailModal task={selectedTask} onClose={handleCloseModal} />
      )}

      <div className={`${styles.container} ${isActive ? styles.active : ''}`}>
        {/* Compact list drawer */}
        {isDrawerOpen && !selectedTask && (
          <div className={styles.drawer}>
            <ListView
              tasks={tasks}
              onSelect={handleSelectTask}
              onClear={clearCompleted}
            />
          </div>
        )}

        {/* Capsule Wrapper */}
        <div className={styles.capsuleWrapper}>
          {isActive && <div className={styles.glowRing} />}
          <button
            className={`${styles.capsule} ${isActive ? styles.loading : ''}`}
            onClick={handleCapsuleClick}
            aria-label="작업 현황 열기"
          >
            {isActive && <div className={styles.rainbowBorder} />}
            <div className={styles.capsuleInner}>
              <div className={styles.capsuleContent}>
                {isActive ? (
                  <>
                    <span className={styles.capsuleIcon}>⚡</span>
                    <span>가공 중... ({displayTask.progress}%)</span>
                    <div className={styles.miniBar}>
                      <div className={styles.miniBarFill} style={{ width: `${displayTask.progress}%` }} />
                    </div>
                  </>
                ) : (
                  <>
                    <span className={styles.capsuleIcon}>✅</span>
                    <span>가공 완료</span>
                  </>
                )}
              </div>
            </div>
          </button>
        </div>
      </div>
    </>
  );
}
