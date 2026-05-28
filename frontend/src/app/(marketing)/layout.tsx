import Link from 'next/link';
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from './marketing.module.css';

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className={styles.layout}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/" className={styles.logoLink}>
            <span className={styles.logoIcon}>⚡</span>
            <span className={styles.logoText}>Auto-Selp</span>
          </Link>
          <div className={styles.headerActions}>
            <Link href="/login">
              <PillButton variant="secondary" className={styles.loginBtn}>로그인</PillButton>
            </Link>
            <Link href="/login">
              <PillButton variant="primary" className={styles.startBtn}>무료 시작하기</PillButton>
            </Link>
          </div>
        </div>
      </header>
      <main className={styles.main}>
        {children}
      </main>
    </div>
  );
}
