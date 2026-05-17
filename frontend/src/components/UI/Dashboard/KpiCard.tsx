import styles from './Dashboard.module.css';

interface KpiCardProps {
  title: string;
  value: string;
  trend?: { value: string; isUp: boolean };
}

export const KpiCard = ({ title, value, trend }: KpiCardProps) => (
  <div className={styles.kpiCard}>
    <h3 className={styles.kpiTitle}>{title}</h3>
    <div className={styles.kpiValue}>{value}</div>
    {trend && (
      <div className={`${styles.kpiTrend} ${trend.isUp ? styles.up : styles.down}`}>
        {trend.isUp ? '↑' : '↓'} {trend.value}
      </div>
    )}
  </div>
);
