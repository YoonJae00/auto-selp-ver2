import styles from './Dashboard.module.css';
import clsx from 'clsx';

interface ProgressBarProps {
  label: string;
  progress: number;
  status: string;
}

export default function ProgressBar({ label, progress, status }: ProgressBarProps) {
  return (
    <div className={styles.progressContainer}>
      <div className={styles.progressHeader}>
        <span className={styles.progressLabel}>{label}</span>
        <span className={styles.progressStatus}>{status}</span>
      </div>
      <div 
        className={styles.progressTrack}
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${status}`}
      >
        <div 
          className={clsx(styles.progressFill)} 
          style={{ width: `${progress}%` }} 
        />
      </div>
    </div>
  );
}
