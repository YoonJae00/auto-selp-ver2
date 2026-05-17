import styles from './process.module.css';
import PillButton from '@/components/UI/PillButton/PillButton';

interface TrademarkInfo {
  keyword: string;
  info: {
    exists: boolean;
    title: string;
    details: any[];
  };
}

interface TrademarkModalProps {
  warnings: Record<number, TrademarkInfo[]>;
  onClose: () => void;
}

export default function TrademarkModal({ warnings, onClose }: TrademarkModalProps) {
  // Flatten warnings for easier display
  const allWarnings = Object.values(warnings).flat();

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalContent}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>상표권 검증 결과 (주의 필요)</h2>
          <button className={styles.closeButton} onClick={onClose}>&times;</button>
        </div>
        <div className={styles.modalBody}>
          <p className={styles.modalDesc}>
            가공 과정에서 다음 단어들이 KIPRIS 상표권 데이터베이스에서 검색되었습니다. 
            판매 시 저작권 문제가 발생할 수 있으니 검토 후 수정하시기 바랍니다.
          </p>
          <div className={styles.warningList}>
            {allWarnings.map((w, idx) => (
              <div key={idx} className={styles.warningCard}>
                <div className={styles.warningBadge}>주의</div>
                <div className={styles.warningInfo}>
                  <h4 className={styles.warningKeyword}>{w.keyword}</h4>
                  <p className={styles.warningDetails}>
                    KIPRIS 검색명: {w.info.title || '정보 없음'}<br/>
                    출원/등록 상태: {w.info.details?.[0]?.status || '확인 불가'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className={styles.modalFooter}>
          <PillButton onClick={onClose}>닫기</PillButton>
        </div>
      </div>
    </div>
  );
}
