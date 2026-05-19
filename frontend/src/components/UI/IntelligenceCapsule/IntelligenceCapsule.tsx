'use client';

import React, { useState, useMemo } from 'react';
import { useTaskStore, Task, CompletedRow } from '@/store/taskStore';
import styles from './IntelligenceCapsule.module.css';
import clsx from 'clsx';

type DrawerView = 'list' | 'detail';

function RowItem({ row, isExpanded, onToggle, status }: { row: any, isExpanded: boolean, onToggle?: () => void, status: 'completed' | 'active' | 'waiting' }) {
  
  const stageLabels: Record<string, string> = {
    refining: '상품명 정제',
    keywords: '키워드 생성',
    categorizing: '카테고리 매핑'
  };

  const currentStageName = status === 'active' ? row.stage : null;
  const stagesOrder = ['refining', 'keywords', 'categorizing'];

  return (
    <div className={styles.treeRow}>
      <div 
        className={clsx(styles.treeRowHeader, styles[status])} 
        onClick={status === 'completed' && onToggle ? onToggle : undefined}
      >
        <div className={styles.treeRowInfo}>
          <span className={styles.treeIcon}>
            {status === 'completed' ? '✅' : status === 'active' ? '🔄' : '⏳'}
          </span>
          <span className={clsx(styles.treeName, status === 'active' && styles.shimmerText)}>
            {row.name}
          </span>
        </div>
        {status === 'completed' && row.total_ms !== undefined && (
          <span className={styles.treeTime}>{(row.total_ms / 1000).toFixed(1)}s</span>
        )}
      </div>

      {isExpanded && (
        <div className={styles.treeChildren}>
          {status === 'completed' ? (
            row.stages?.map((stage: any, idx: number) => (
              <div key={idx} className={styles.treeChild}>
                <div className={styles.treeChildInfo}>
                  <span>✅</span>
                  <span>{stageLabels[stage.name] || stage.name}</span>
                </div>
                <span>{(stage.ms / 1000).toFixed(1)}s</span>
              </div>
            ))
          ) : status === 'active' ? (
            stagesOrder.map((stageKey) => {
              let childStatus = 'waiting';
              if (currentStageName === stageKey) childStatus = 'active';
              else if (
                stagesOrder.indexOf(currentStageName) > stagesOrder.indexOf(stageKey) ||
                currentStageName === 'completed_row'
              ) childStatus = 'completed';

              return (
                <div key={stageKey} className={styles.treeChild}>
                  <div className={styles.treeChildInfo}>
                    <span>{childStatus === 'completed' ? '✅' : childStatus === 'active' ? '🔄' : '⏳'}</span>
                    <span className={childStatus === 'active' ? styles.shimmerText : undefined}>
                      {stageLabels[stageKey]}
                    </span>
                  </div>
                </div>
              );
            })
          ) : null}
        </div>
      )}
    </div>
  );
}

function TaskDetailView({ task, onBack }: { task: Task, onBack: () => void }) {
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const toggleExpand = (idx: number) => {
    const newSet = new Set(expandedRows);
    if (newSet.has(idx)) newSet.delete(idx);
    else newSet.add(idx);
    setExpandedRows(newSet);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className={styles.drawerHeader}>
        <div className={styles.drawerTitleWithBack}>
          <button className={styles.backBtn} onClick={onBack}>←</button>
          <span className={styles.drawerTitle}>작업 상세 내역</span>
        </div>
      </div>
      
      <div className={styles.drawerBody}>
        <div style={{ marginBottom: '16px' }}>
          <div className={styles.filename} style={{ fontSize: '15px', marginBottom: '8px' }}>
            {task.filename}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div className={styles.progressBar} style={{ flex: 1 }}>
              <div 
                className={styles.progressFill} 
                style={{ width: `${task.progress}%`, background: 'var(--accent-gradient)' }} 
              />
            </div>
            <span style={{ fontSize: '13px', fontWeight: 600 }}>{task.progress}%</span>
          </div>
        </div>

        <div className={styles.treeContainer}>
          {task.completedRows?.map((row, i) => (
            <RowItem 
              key={i}
              row={row}
              isExpanded={expandedRows.has(i)}
              onToggle={() => toggleExpand(i)}
              status="completed"
            />
          ))}

          {task.status === 'PROGRESS' && task.currentName && (
            <RowItem
              row={{ name: task.currentName, stage: task.stage }}
              isExpanded={true}
              status="active"
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default function IntelligenceCapsule() {
  const { tasks, removeTask, clearCompleted } = useTaskStore();
  const [isOpen, setIsOpen] = useState(false);
  const [drawerView, setDrawerView] = useState<DrawerView>('list');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [isMounted, setIsMounted] = React.useState(false);

  React.useEffect(() => {
    setIsMounted(true);
  }, []);

  const activeTasks = useMemo(() => 
    tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS'),
  [tasks]);

  if (!isMounted || tasks.length === 0) return null;

  const isActive = activeTasks.length > 0;
  const displayTask = activeTasks.length > 0 ? activeTasks[activeTasks.length - 1] : tasks[tasks.length - 1];

  const handleTaskClick = (id: string) => {
    setSelectedTaskId(id);
    setDrawerView('detail');
  };

  const selectedTask = tasks.find(t => t.id === selectedTaskId) || displayTask;

  return (
    <div className={clsx(styles.container, isActive && styles.active)}>
      
      {isOpen && (
        <div className={styles.drawer}>
          {drawerView === 'list' ? (
            <>
              <div className={styles.drawerHeader}>
                <span className={styles.drawerTitle}>Intelligence Tasks</span>
                <button className={styles.clearAllBtn} onClick={clearCompleted}>
                  완료 지우기
                </button>
              </div>
              <div className={styles.drawerBody}>
                <div className={styles.taskList}>
                  {tasks.slice().reverse().map((task) => (
                    <div 
                      key={task.id} 
                      className={styles.taskItem}
                      onClick={() => handleTaskClick(task.id)}
                    >
                      <div className={styles.taskHeader}>
                        <span className={styles.filename} title={task.filename}>
                          {task.filename}
                        </span>
                        <span className={clsx(styles.status, styles[`status_${task.status}`])}>
                          {task.status}
                        </span>
                      </div>
                      
                      {(task.status === 'PROGRESS' || task.status === 'PENDING') && (
                        <div className={styles.progressBar} style={{ width: '100%', marginTop: '8px' }}>
                          <div 
                            className={styles.progressFill} 
                            style={{ width: `${task.progress}%`, background: 'var(--accent-gradient)' }} 
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <TaskDetailView 
              task={selectedTask} 
              onBack={() => setDrawerView('list')} 
            />
          )}
        </div>
      )}

      <div className={styles.capsule} onClick={() => setIsOpen(!isOpen)}>
        <div className={styles.glow} />
        <div className={styles.content}>
          {isActive ? (
            <>
              <span>⚡ 가공 중... ({activeTasks.length})</span>
              <div className={styles.progressBar}>
                <div 
                  className={styles.progressFill} 
                  style={{ width: `${displayTask.progress}%`, background: 'var(--accent-gradient)' }} 
                />
              </div>
            </>
          ) : (
            <span>✅ 가공 완료</span>
          )}
        </div>
      </div>
    </div>
  );
}
