import styles from './ai-mall.module.css';

export default function AiMallLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className={styles.container}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarBrand}>Auto-Selp AI Mall</div>
        <nav className={styles.sidebarNav}>
          <div className={styles.activeNavItem}>홈</div>
          <div>상품 가공</div>
          <div>설정</div>
        </nav>
      </aside>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
