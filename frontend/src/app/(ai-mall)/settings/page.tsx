'use client';

import { useSettingsStore } from '@/store/settingsStore';
import styles from './settings.module.css';

export default function SettingsPage() {
  const { llmProvider, setLlmProvider } = useSettingsStore();

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
        <h2 className={styles.sectionTitle}>서비스 정보</h2>
        <div className={styles.formGroup}>
          <label className={styles.label}>버전</label>
          <p className={styles.hint}>v0.1.0-alpha</p>
        </div>
      </section>
    </div>
  );
}
