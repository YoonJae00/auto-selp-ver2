import styles from '../ai-mall.module.css';

export default function HomePage() {
  return (
    <div>
      <h1 className={styles.pageTitle}>안녕하세요, 사장님!</h1>
      <div className={styles.statsGrid}>
        <div className={styles.card}>
          <h3>오늘의 매출</h3>
          <div className={styles.cardValue}>₩4,250,000</div>
        </div>
        <div className={styles.card}>
          <h3>가공 대기 상품</h3>
          <div className={styles.cardValue}>45개</div>
        </div>
      </div>
    </div>
  );
}
