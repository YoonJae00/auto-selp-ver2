'use client';

import React, { useRef } from 'react';
import Link from 'next/link';
import PillButton from '@/components/UI/PillButton/PillButton';
import LiveTaskGraph from '@/components/Marketing/LiveTaskGraph';
import styles from './marketing.module.css';

export default function LandingPage() {
  const demoSectionRef = useRef<HTMLDivElement>(null);

  const scrollToDemo = () => {
    demoSectionRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className={styles.pageContainer}>
      {/* 1. Hero Section */}
      <section className={styles.heroSection}>
        <div className={styles.heroContent}>
          <span className={styles.heroSuperTitle}>AI-POWERED ECOMMERCE FLOW</span>
          <h1 className={styles.heroTitle}>
            이커머스 상품 가공의<br />
            새로운 표준.
          </h1>
          <p className={styles.heroDesc}>
            도매처 엑셀 대장 업로드 한 번으로 상품명 순화, 키워드 추출, KIPRIS 상표권 검증, 
            카테고리 매핑까지 단 몇 초 만에 완수합니다. 지루한 반복 작업은 AI 자동화 파이프라인에 맡기세요.
          </p>
          <div className={styles.heroActions}>
            <Link href="/login">
              <PillButton variant="primary" className={styles.heroPrimaryBtn}>
                지금 무료로 시작하기
              </PillButton>
            </Link>
            <PillButton variant="secondary" onClick={scrollToDemo} className={styles.heroSecondaryBtn}>
              가공과정 체험하기 <span>↓</span>
            </PillButton>
          </div>
        </div>
      </section>

      {/* 2. Interactive Live Task Graph Section */}
      <section ref={demoSectionRef} className={styles.demoSection}>
        <div className={styles.demoHeader}>
          <span className={styles.sectionBadge}>LIVE PIPELINE VISUALIZATION</span>
          <h2 className={styles.sectionTitle}>
            실시간 AI 가공 엔진<br />
            작업 흐름도
          </h2>
          <p className={styles.sectionDesc}>
            도매처에서 제공한 날것의 상품 데이터가 Auto-Selp의 5단계 지능형 파이프라인을 통과하며 
            최적화된 검색 키워드와 안전한 판매용 상품 정보로 탈바꿈되는 실시간 데이터 흐름을 확인해 보세요.
          </p>
        </div>
        <div className={styles.graphContainer}>
          <LiveTaskGraph />
        </div>
      </section>

      {/* 3. Feature Showcase Grid Section */}
      <section className={styles.featuresSection}>
        <div className={styles.featuresHeader}>
          <span className={styles.sectionBadge}>CORE CAPABILITIES</span>
          <h2 className={styles.sectionTitle}>비즈니스를 가속화하는 핵심 엔진</h2>
          <p className={styles.sectionDesc}>
            기존 수작업 대비 가공 속도를 99% 단축하면서도 상표권 침해 우려와 정보 오류율은 0%로 수렴합니다.
          </p>
        </div>

        <div className={styles.featuresGrid}>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>📤</div>
            <h3 className={styles.featureTitle}>도매처 엑셀 파서 & 매퍼</h3>
            <p className={styles.featureText}>
              도매 대장의 다양한 상품 형식을 분석하여 컬럼 매핑기(Column Mapper)가 구조화된 데이터 모델로 일괄 변환 및 흡수합니다.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>✏️</div>
            <h3 className={styles.featureTitle}>LLM 기획자급 상품명 가공</h3>
            <p className={styles.featureText}>
              인기 없고 조잡한 수식어, 특수기호, 반복되는 유인용 단어를 정밀 청소하여 고객 검색 노출에 완벽히 타겟팅된 이름으로 단숨에 순화합니다.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>🛡️</div>
            <h3 className={styles.featureTitle}>KIPRIS 특허청 상표권 검증</h3>
            <p className={styles.featureText}>
              특허청 KIPRIS 실시간 상표권 조회와 자체 금지어 데이터베이스를 통해 상표 분쟁 리스크가 숨어 있는 키워드를 선제 차단해 셀러 계정을 안전하게 보호합니다.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>📂</div>
            <h3 className={styles.featureTitle}>네이버 & 쿠팡 카테고리 매핑</h3>
            <p className={styles.featureText}>
              수동 카테고리 매핑의 고통을 덜어드립니다. AI 카테고리 매퍼가 네이버 스마트스토어와 쿠팡의 분류 체계를 100% 매치하여 실시간 반환합니다.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>⚡</div>
            <h3 className={styles.featureTitle}>Smart Upsert & 스마트 갱신</h3>
            <p className={styles.featureText}>
              도매처의 변동 상황을 실시간 감지하여 재고 없음이나 가격 변동(Upsert) 등 핵심 변경 사항만 필터링하여 유연한 마켓플레이스 동기화를 준비합니다.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>📲</div>
            <h3 className={styles.featureTitle}>실시간 백그라운드 태스크</h3>
            <p className={styles.featureText}>
              FastAPI 비동기 Celery 아키텍처와 Zustand 상태 관리로 대량의 파일 가공 중에도 다른 페이지의 작업을 멈춤 없이 자유롭게 이행할 수 있습니다.
            </p>
          </div>
        </div>
      </section>

      {/* 4. Final CTA Section (Dark Mode Transition) */}
      <section className={styles.ctaSection}>
        <div className={styles.ctaContent}>
          <h2 className={styles.ctaTitle}>
            지루한 노가다는 AI에게 맡기고,<br />
            셀러는 본질적인 성장에 집중하세요.
          </h2>
          <p className={styles.ctaDesc}>
            지금 Auto-Selp와 함께 가장 영리하고 안전한 이커머스 자동화 운영 체제를 구축해 보시기 바랍니다.
          </p>
          <Link href="/login">
            <PillButton variant="primary" className={styles.ctaBtn}>
              지금 바로 무료로 시작하기
            </PillButton>
          </Link>
        </div>
      </section>

      {/* 5. Footer Section */}
      <footer className={styles.footer}>
        <div className={styles.footerContent}>
          <div className={styles.footerBrand}>
            <span className={styles.footerLogo}>⚡ Auto-Selp</span>
            <p className={styles.footerCopy}>© {new Date().getFullYear()} Auto-Selp. All rights reserved.</p>
          </div>
          <div className={styles.footerLinks}>
            <Link href="/login" className={styles.footerLink}>대시보드</Link>
            <Link href="/login" className={styles.footerLink}>로그인</Link>
            <Link href="/login" className={styles.footerLink}>회원가입</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
