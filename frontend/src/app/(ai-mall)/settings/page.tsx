'use client';

import { useSettingsStore } from '@/store/settingsStore';
import styles from './settings.module.css';

export default function SettingsPage() {
  const { llmProvider, setLlmProvider, kiprisEnabled, setKiprisEnabled } = useSettingsStore();

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>설정</h1>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>AI 엔진 설정</h2>
        
        <div className={styles.formGroup}>
          <label className={styles.label}>기본 LLM 엔진</label>
          <select 
            className={styles.select}
            value={llmProvider}
            onChange={(e) => setLlmProvider(e.target.value)}
          >
            <option value="gemini">Gemini 3.1 Flash-Lite (추천)</option>
            <option value="openai">gpt-5.4-nano (고성능)</option>
          </select>
          <p className={styles.hint}>
            상품명 정제 및 키워드 생성에 사용될 기본 인공지능 모델을 선택합니다.
          </p>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>상표권 검증 설정</h2>

        <div className={styles.formGroup}>
          <div className={styles.toggleRow}>
            <div className={styles.toggleInfo}>
              <label className={styles.label}>KIPRIS 상표권 실시간 검증</label>
              <p className={styles.hint}>
                활성화 시 LLM이 브랜드로 의심한 키워드를 KIPRIS 특허청 DB에서 실시간 확인합니다.
                <br />
                <strong>월 1,000회 한도</strong> — 초과 시 자동 비활성화를 권장합니다.
                비활성화 시 LLM 판단으로 브랜드 의심 키워드를 자동 제외하고 결과에 목록을 표시합니다.
              </p>
            </div>
            <button
              className={`${styles.toggleBtn} ${kiprisEnabled ? styles.toggleOn : styles.toggleOff}`}
              onClick={() => setKiprisEnabled(!kiprisEnabled)}
              aria-label="KIPRIS 상표권 검증 토글"
            >
              <span className={styles.toggleKnob} />
              <span className={styles.toggleLabel}>{kiprisEnabled ? 'ON' : 'OFF'}</span>
            </button>
          </div>

          {!kiprisEnabled && (
            <div className={styles.warningBanner}>
              ⚠️ KIPRIS 검증이 꺼져 있습니다. LLM 추측 기반으로 브랜드 의심 키워드를 제외하며,
              제거된 키워드 목록은 처리 완료 후 확인할 수 있습니다.
            </div>
          )}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>서비스 정보</h2>
        <div className={styles.formGroup}>
          <label className={styles.label}>버전</label>
          <p className={styles.hint}>v0.1.0-alpha</p>
        </div>
      </section>
    </div>
  );
}
