'use client';

import React, { useEffect } from 'react';
import styles from './DeleteConfirmModal.module.css';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (force: boolean) => void;
  count: number;
  warningSyncedCount: number;
  isDeleting: boolean;
  error: string | null;
}

export default function DeleteConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  count,
  warningSyncedCount,
  isDeleting,
  error
}: DeleteConfirmModalProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isDeleting) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, isDeleting, onClose]);

  if (!isOpen) return null;

  const hasWarnings = warningSyncedCount > 0;

  return (
    <div className={styles.overlay} onClick={!isDeleting ? onClose : undefined}>
      <div
        className={styles.modalCard}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-modal-title"
        aria-describedby="delete-modal-description"
      >
        <div className={styles.iconContainer}>
          {hasWarnings ? (
            <div className={`${styles.icon} ${styles.alertIcon}`}>⚠️</div>
          ) : (
            <div className={`${styles.icon} ${styles.trashIcon}`}>🗑️</div>
          )}
        </div>

        <h2 className={styles.title} id="delete-modal-title">
          {hasWarnings ? '경고: 마켓 연동 상품 포함' : '상품 삭제'}
        </h2>

        <div className={styles.content} id="delete-modal-description">
          {hasWarnings ? (
            <p className={styles.warningMessage}>
              삭제 대상 중 이미 스마트스토어/쿠팡에 등록(동기화) 완료된 상품{' '}
              <strong className={styles.highlight}>{warningSyncedCount}개</strong>가 포함되어 있습니다!
              <br />
              <br />
              DB에서 제거 시 향후 가격/재고 스마트 갱신 및 관리가 완전히 불가능해집니다.
              정말로 연동 데이터를 포함해 모두 강제로 삭제하시겠습니까?
            </p>
          ) : (
            <p className={styles.normalMessage}>
              선택한 <strong className={styles.highlight}>{count}개</strong>의 상품을 데이터베이스에서 영구 삭제하시겠습니까?
              이 작업은 되돌릴 수 없습니다.
            </p>
          )}
        </div>

        {error && <div className={styles.errorAlert}>{error}</div>}

        <div className={styles.actions}>
          <button
            className={styles.cancelBtn}
            onClick={onClose}
            disabled={isDeleting}
          >
            {hasWarnings ? '아니오 (취소)' : '취소'}
          </button>
          <button
            className={hasWarnings ? styles.forceBtn : styles.dangerBtn}
            onClick={() => onConfirm(hasWarnings)}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <span className={styles.spinner}></span>
            ) : hasWarnings ? (
              '예, 강제로 삭제'
            ) : (
              '삭제하기'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

