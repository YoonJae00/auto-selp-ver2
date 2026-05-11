import styles from './PillButton.module.css';
import clsx from 'clsx';

interface Props {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'link';
  onClick?: () => void;
}

export default function PillButton({ children, variant = 'primary', onClick }: Props) {
  return (
    <button 
      className={clsx(styles.button, styles[variant])}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
