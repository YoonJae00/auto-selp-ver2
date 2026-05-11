import styles from './marketing.module.css';

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className={styles.layout}>
      <nav className={styles.nav}>
        <div className={styles.navContent}>
          <span className={styles.logo}>Auto-Selp</span>
        </div>
      </nav>
      {children}
    </div>
  );
}
