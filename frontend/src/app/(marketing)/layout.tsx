import type { Metadata } from 'next';
import Link from 'next/link';
import styles from './marketing.module.css';

export const metadata: Metadata = {
  title: 'Auto-Selp | 1인 셀러를 위한 상품 등록 준비 자동화',
  description: '공급사 엑셀을 상품명, 키워드, 상표권 확인, 네이버·쿠팡 등록 초안으로 정리하는 AI 커머스 워크스페이스.',
};

const demoFormUrl = process.env.DEMO_FORM_URL;

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.layout}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/" className={styles.logo}>Auto-Selp</Link>
          <nav className={styles.desktopNav} aria-label="주요 메뉴">
            <a href="#workflow">작동 방식</a>
            <a href="#features">핵심 기능</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className={styles.headerActions}>
            <Link className={styles.headerLogin} href="/login">로그인</Link>
            {demoFormUrl ? (
              <a className={styles.headerDemo} href={demoFormUrl} target="_blank" rel="noopener noreferrer">데모 신청</a>
            ) : (
              <button className={styles.headerDemo} type="button" disabled>데모 준비 중</button>
            )}
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
