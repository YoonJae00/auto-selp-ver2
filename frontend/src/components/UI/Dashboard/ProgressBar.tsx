import styles from './Dashboard.module.css';

interface ProgressBarProps {
  label: string;
  progress: number;
  status: string;
}

export const ProgressBar = ({ label, progress, status }: ProgressBarProps) => (
  <div className={styles.progressContainer}>
    <div className={styles.progressHeader}>
      <span className={styles.progressLabel}>{label}</span>
      <span className={styles.progressStatus}>{status}</span>
    </div>
    <div className={styles.progressTrack}>
      <div className={styles.progressFill} style={{ width: `${progress}%` }} />
    </div>
  </div>
);
