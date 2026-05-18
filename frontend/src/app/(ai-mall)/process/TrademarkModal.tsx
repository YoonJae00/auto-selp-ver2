import styles from './process.module.css';
import PillButton from '@/components/UI/PillButton/PillButton';

interface TrademarkWarning {
  keyword: string;
  type: 'kipris_confirmed' | 'llm_suspected';
  info?: {
    exists: boolean;
    title: string;
    details: any[];
  };
  reason?: string;
}

interface TrademarkModalProps {
  warnings: Record<number, TrademarkWarning[]>;
  onClose: () => void;
}

export default function TrademarkModal({ warnings, onClose }: TrademarkModalProps) {
  const allWarnings = Object.values(warnings).flat();
  const kiprisConfirmed = allWarnings.filter((w) => w.type === 'kipris_confirmed');
  const llmSuspected = allWarnings.filter((w) => w.type === 'llm_suspected');

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalContent}>
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>상표권 검증 결과</h2>
          <button className={styles.closeButton} onClick={onClose}>&times;</button>
        </div>

        <div className={styles.modalBody}>
          {/* KIPRIS 실제 확인 */}
          {kiprisConfirmed.length > 0 && (
            <div className={styles.warningSection}>
              <div className={styles.warningSectionHeader}>
                <span className={styles.badgeKipris}>🔴 KIPRIS 상표 확인됨</span>
                <span className={styles.warningSectionCount}>{kiprisConfirmed.length}개</span>
              </div>
              <p className={styles.modalDesc}>
                KIPRIS 특허청 DB에서 상표권이 확인된 키워드입니다. 키워드에서 자동 제외되었습니다.
              </p>
              <div className={styles.warningList}>
                {kiprisConfirmed.map((w, idx) => (
                  <div key={idx} className={styles.warningCard}>
                    <div className={styles.warningBadge} data-type="kipris">주의</div>
                    <div className={styles.warningInfo}>
                      <h4 className={styles.warningKeyword}>{w.keyword}</h4>
                      <p className={styles.warningDetails}>
                        KIPRIS 검색명: {w.info?.title || '정보 없음'}<br />
                        출원/등록 상태: {w.info?.details?.[0]?.status || '확인 불가'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* LLM 추측 제외 */}
          {llmSuspected.length > 0 && (
            <div className={styles.warningSection}>
              <div className={styles.warningSectionHeader}>
                <span className={styles.badgeLlm}>🟡 LLM 추측 제외</span>
                <span className={styles.warningSectionCount}>{llmSuspected.length}개</span>
              </div>
              <p className={styles.modalDesc}>
                KIPRIS 미사용 상태에서 AI가 브랜드명으로 판단하여 자동 제외된 키워드입니다.
                실제 상표 여부는 직접 확인하세요.
              </p>
              <div className={styles.warningList}>
                {llmSuspected.map((w, idx) => (
                  <div key={idx} className={styles.warningCard}>
                    <div className={styles.warningBadge} data-type="llm">추측</div>
                    <div className={styles.warningInfo}>
                      <h4 className={styles.warningKeyword}>{w.keyword}</h4>
                      <p className={styles.warningDetails}>
                        {w.reason}
                        <br />
                        <a
                          href={`https://www.kipris.or.kr/khome/main.do`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={styles.kiprisLink}
                        >
                          KIPRIS에서 직접 확인 →
                        </a>
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {allWarnings.length === 0 && (
            <p className={styles.modalDesc}>검출된 상표권 이슈가 없습니다.</p>
          )}
        </div>

        <div className={styles.modalFooter}>
          <PillButton onClick={onClose}>닫기</PillButton>
        </div>
      </div>
    </div>
  );
}
