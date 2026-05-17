'use client';

import React, { useState, useMemo } from 'react';
import { useTaskStore, Task } from '@/store/taskStore';
import styles from './IntelligenceCapsule.module.css';
import clsx from 'clsx';

export default function IntelligenceCapsule() {
  const { tasks, removeTask, clearCompleted } = useTaskStore();
  const [isExpanded, setIsExpanded] = useState(false);

  // Active tasks that are currently being processed
  const activeTasks = useMemo(() => 
    tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS'),
  [tasks]);

  // If no tasks at all, don't show anything
  if (tasks.length === 0) return null;

  const isActive = activeTasks.length > 0;
  
  // Display the most recent active task, or the most recent completed task
  const displayTask = activeTasks.length > 0 
    ? activeTasks[activeTasks.length - 1] 
    : tasks[tasks.length - 1];

  const toggleExpand = () => setIsExpanded(!isExpanded);

  const handleDownload = (task: Task) => {
    if (task.resultPath) {
      // In a real app, this might be a direct link or a triggered download
      window.open(task.resultPath, '_blank');
    }
  };

  return (
    <div className={clsx(styles.container, isActive && styles.active)}>
      <div className={styles.capsule} onClick={toggleExpand}>
        <div className={styles.glow} />
        <div className={styles.content}>
          {isActive ? (
            <>
              <span>가공 중... ({activeTasks.length})</span>
              <div className={styles.progressBar}>
                <div 
                  className={styles.progressFill} 
                  style={{ width: `${displayTask.progress}%` }} 
                />
              </div>
            </>
          ) : (
            <span>가공 완료</span>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className={styles.expandedPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>Intelligence Tasks</span>
            <button className={styles.clearAllBtn} onClick={clearCompleted}>
              지우기
            </button>
          </div>
          
          <div className={styles.taskList}>
            {tasks.slice().reverse().map((task) => (
              <div key={task.id} className={styles.taskItem}>
                <div className={styles.taskHeader}>
                  <span className={styles.filename} title={task.filename}>
                    {task.filename}
                  </span>
                  <span className={clsx(styles.status, styles[`status_${task.status}`])}>
                    {task.status === 'PROGRESS' ? `${task.progress}%` : task.status}
                  </span>
                </div>
                
                {(task.status === 'PROGRESS' || task.status === 'PENDING') && (
                  <div className={styles.progressBar} style={{ width: '100%', marginTop: '4px' }}>
                    <div 
                      className={styles.progressFill} 
                      style={{ width: `${task.progress}%` }} 
                    />
                  </div>
                )}

                <div className={styles.taskFooter}>
                  {task.status === 'SUCCESS' && (
                    <button 
                      className={styles.downloadBtn}
                      onClick={() => handleDownload(task)}
                    >
                      다운로드
                    </button>
                  )}
                  <button 
                    className={styles.removeBtn}
                    onClick={() => removeTask(task.id)}
                  >
                    삭제
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
