'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/store/authStore';
import PillButton from '@/components/UI/PillButton/PillButton';
import IntelligenceCapsule from '@/components/UI/IntelligenceCapsule/IntelligenceCapsule';
import styles from './ai-mall.module.css';

const NAV_ITEMS = [
  { href: '/home', label: '홈', railLabel: 'H' },
  { href: '/process', label: '상품 가공', railLabel: 'AI' },
  { href: '/upload', label: '도매처 & 업로드 설정', railLabel: 'UP' },
  { href: '/products', label: '상품 관리', railLabel: 'PR' },
  { href: '/settings', label: '설정', railLabel: 'ST' },
];

const DENSE_WORKSPACE_PATHS = ['/products', '/upload', '/process'];

export default function AiMallLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, logout, user, isLoading } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const isDenseWorkspace = DENSE_WORKSPACE_PATHS.some((path) => pathname?.startsWith(path));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [hasSidebarPreference, setHasSidebarPreference] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  useEffect(() => {
    const stored = window.localStorage.getItem('autoselp.sidebarCollapsed');
    if (stored === null) {
      setSidebarCollapsed(isDenseWorkspace);
      setHasSidebarPreference(false);
      return;
    }

    setSidebarCollapsed(stored === 'true');
    setHasSidebarPreference(true);
  }, [isDenseWorkspace]);

  useEffect(() => {
    if (!hasSidebarPreference) {
      setSidebarCollapsed(isDenseWorkspace);
    }
  }, [hasSidebarPreference, isDenseWorkspace]);

  if (isLoading) {
    return (
      <div className={styles.loadingContainer}>
        접속 중...
      </div>
    );
  }

  if (!isAuthenticated) return null;

  const handleLogout = async () => {
    await logout();
    router.push('/login');
  };

  const toggleSidebar = () => {
    setHasSidebarPreference(true);
    setSidebarCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem('autoselp.sidebarCollapsed', String(next));
      return next;
    });
  };

  return (
    <div className={`${styles.container} ${sidebarCollapsed ? styles.sidebarCollapsed : ''}`}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <Link href="/home" className={styles.sidebarBrand} aria-label="Auto-Selp AI Mall 홈">
            <span className={styles.brandMark}>AS</span>
            <span className={styles.brandText}>Auto-Selp AI Mall</span>
          </Link>
          <button
            type="button"
            className={styles.sidebarToggle}
            onClick={toggleSidebar}
            aria-label={sidebarCollapsed ? '메뉴 펼치기' : '메뉴 접기'}
            title={sidebarCollapsed ? '메뉴 펼치기' : '메뉴 접기'}
          >
            {sidebarCollapsed ? '>' : '<'}
          </button>
        </div>
        <div className={styles.userInfo}>
          <p className={styles.userLabel}>Workspace</p>
          <p className={styles.username}>{user?.username}님</p>
          <PillButton variant="link" onClick={handleLogout}>로그아웃</PillButton>
        </div>
        <nav className={styles.sidebarNav} aria-label="AI Mall 메뉴">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? styles.activeNavItem : ''}
              title={item.label}
            >
              <span className={styles.navIcon}>{item.railLabel}</span>
              <span className={styles.navLabel}>{item.label}</span>
            </Link>
          ))}
        </nav>
      </aside>
      <main className={`${styles.main} ${isDenseWorkspace ? styles.denseMain : ''}`}>
        <IntelligenceCapsule />
        {children}
      </main>
    </div>
  );
}
