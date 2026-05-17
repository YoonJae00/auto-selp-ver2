import styles from './Dashboard.module.css';
import PillButton from '../PillButton/PillButton';

interface ActionItemProps {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  type?: 'warning' | 'error' | 'info';
}

export const ActionItem = ({ title, description, actionLabel, onAction, type = 'info' }: ActionItemProps) => (
  <div className={`${styles.actionItem} ${styles[type]}`}>
    <div className={styles.actionContent}>
      <h4 className={styles.actionTitle}>{title}</h4>
      <p className={styles.actionDescription}>{description}</p>
    </div>
    <PillButton variant="secondary" onClick={onAction}>{actionLabel}</PillButton>
  </div>
);
