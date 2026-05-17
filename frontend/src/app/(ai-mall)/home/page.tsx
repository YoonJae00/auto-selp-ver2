'use client';

import KpiCard from '@/components/UI/Dashboard/KpiCard';
import ProgressBar from '@/components/UI/Dashboard/ProgressBar';
import ActionItem from '@/components/UI/Dashboard/ActionItem';
import styles from './home.module.css';

export default function HomePage() {
  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <h1 className={styles.pageTitle}>안녕하세요, 사장님!</h1>
      </header>

      {/* Tier 1: KPI Dashboard */}
      <section className={styles.section}>
        <div className={styles.kpiGrid}>
          <KpiCard title="오늘의 매출" value="₩4,250,000" trend={{ value: "12%", isUp: true }} />
          <KpiCard title="가공 완료 상품" value="128개" trend={{ value: "5%", isUp: true }} />
          <KpiCard title="가공 대기 상품" value="45개" />
          <KpiCard title="AI 효율 (시간 절약)" value="24시간" />
        </div>
        <div className={styles.storeRow}>
          <div className={styles.storeChip}>
            <span>쿠팡</span>
            <span className={styles.storeBadge}>등록 120 / 판매 15</span>
          </div>
          <div className={styles.storeChip}>
            <span>네이버</span>
            <span className={styles.storeBadge}>등록 85 / 판매 8</span>
          </div>
          <div className={styles.storeChip}>
            <span>기타</span>
            <span className={styles.storeBadge}>등록 30 / 판매 2</span>
          </div>
        </div>
      </section>

      {/* Tier 2: Process Monitor */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>프로세스 모니터</h2>
        </div>
        <div className={styles.monitorCard}>
          <ProgressBar label="신상_의류_가공_v2.xlsx" progress={65} status="AI 분석 및 키워드 생성 중..." />
          <ProgressBar label="여름_신발_컬렉션.xlsx" progress={100} status="가공 완료" />
        </div>
      </section>

      {/* Tier 3: Action Queue */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>할 일 목록</h2>
        </div>
        <div className={styles.queueCard}>
          <ActionItem 
            title="카테고리 매핑 확인 필요" 
            description="5건의 상품에 대해 AI가 확신을 갖지 못했습니다. 최종 확인을 해주세요." 
            actionLabel="확인하기" 
            onAction={() => {}}
            type="warning"
          />
          <ActionItem 
            title="가공 오류 발생" 
            description="이미지 누락으로 인해 2건의 상품 가공이 중단되었습니다." 
            actionLabel="수정" 
            onAction={() => {}}
            type="error"
          />
        </div>
      </section>
    </div>
  );
}
