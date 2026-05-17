import styles from './auth.module.css';

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className={styles.container}>
      <div className={styles.blob1}></div>
      <div className={styles.blob2}></div>
      <div className={styles.grain}></div>
      <div className={styles.card}>
        {children}
      </div>
    </div>
  );
}
