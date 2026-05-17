import styles from './Dashboard.module.css';
import PillButton from '../PillButton/PillButton';
import clsx from 'clsx';

interface ActionItemProps {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  type?: 'warning' | 'error' | 'info';
}

export default function ActionItem({ 
  title, 
  description, 
  actionLabel, 
  onAction, 
  type = 'info' 
}: ActionItemProps) {
  return (
    <div className={clsx(styles.actionItem, type && styles[type])}>
      <div className={styles.actionContent}>
        <h4 className={styles.actionTitle}>{title}</h4>
        <p className={styles.actionDescription}>{description}</p>
      </div>
      <PillButton variant="secondary" onClick={onAction}>{actionLabel}</PillButton>
    </div>
  );
}
