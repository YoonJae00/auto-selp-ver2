import styles from './PillButton.module.css';
import clsx from 'clsx';

interface Props {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'link';
  onClick?: () => void;
  type?: 'button' | 'submit' | 'reset';
  className?: string;
  disabled?: boolean;
}

export default function PillButton({ 
  children, 
  variant = 'primary', 
  onClick, 
  type = 'button',
  className,
  disabled
}: Props) {
  return (
    <button 
      type={type}
      className={clsx(styles.button, styles[variant], className)}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
