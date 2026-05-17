import styles from './Dashboard.module.css';
import clsx from 'clsx';

interface KpiCardProps {
  title: string;
  value: string;
  trend?: { value: string; isUp: boolean };
}

export default function KpiCard({ title, value, trend }: KpiCardProps) {
  return (
    <div className={styles.kpiCard}>
      <h3 className={styles.kpiTitle}>{title}</h3>
      <div className={styles.kpiValue}>{value}</div>
      {trend && (
        <div className={clsx(styles.kpiTrend, trend.isUp ? styles.up : styles.down)}>
          {trend.isUp ? '↑' : '↓'} {trend.value}
        </div>
      )}
    </div>
  );
}
