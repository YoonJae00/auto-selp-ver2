'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/store/authStore';
import PillButton from '@/components/UI/PillButton/PillButton';
import IntelligenceCapsule from '@/components/UI/IntelligenceCapsule/IntelligenceCapsule';
import styles from './ai-mall.module.css';

export default function AiMallLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, logout, user, isLoading } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

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

  return (
    <div className={styles.container}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarBrand}>Auto-Selp AI Mall</div>
        <div className={styles.userInfo}>
          <p className={styles.username}>{user?.username}님</p>
          <PillButton variant="link" onClick={handleLogout}>로그아웃</PillButton>
        </div>
        <nav className={styles.sidebarNav}>
          <Link href="/home" className={pathname === '/home' ? styles.activeNavItem : ''}>
            홈
          </Link>
          <Link href="/process" className={pathname === '/process' ? styles.activeNavItem : ''}>
            상품 가공
          </Link>
          <Link href="/upload" className={pathname === '/upload' ? styles.activeNavItem : ''}>
            도매처 & 업로드 설정
          </Link>
          <Link href="/products" className={pathname === '/products' ? styles.activeNavItem : ''}>
            상품 관리
          </Link>
          <Link href="/settings" className={pathname === '/settings' ? styles.activeNavItem : ''}>
            설정
          </Link>
        </nav>
      </aside>
      <main className={styles.main}>
        <IntelligenceCapsule />
        {children}
      </main>
    </div>
  );
}
