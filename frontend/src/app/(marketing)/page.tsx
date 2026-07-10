import Link from 'next/link';
import ProductDemo from '@/components/Marketing/ProductDemo';
import styles from './marketing.module.css';

const demoFormUrl = process.env.DEMO_FORM_URL;

const workflow = [
  {
    number: '01',
    title: '공급사 엑셀 업로드',
    description: '쓰던 상품 대장을 그대로 올리고 필요한 열만 연결합니다.',
  },
  {
    number: '02',
    title: 'AI 가공 결과 검토',
    description: '상품명, 검색 키워드, 상표권 의심어와 카테고리를 한곳에서 확인합니다.',
  },
  {
    number: '03',
    title: '마켓 초안 준비',
    description: '네이버와 쿠팡 형식에 맞춘 등록 초안을 검토 가능한 상태로 정리합니다.',
  },
];

const capabilities = [
  {
    label: '상품 데이터',
    title: '엑셀 형식이 달라도 필요한 열만 연결',
    description: '공급사마다 다른 상품명, 가격, 옵션 열을 시각적으로 매핑하고 다음 업로드에도 같은 설정을 사용합니다.',
  },
  {
    label: '검색과 안전',
    title: '검색어 정리와 상표권 확인을 한 흐름으로',
    description: '불필요한 표현을 정리하고 키워드를 선별한 뒤 KIPRIS 확인 결과와 제외 사유를 함께 남깁니다.',
  },
  {
    label: '마켓 준비',
    title: '네이버와 쿠팡에 맞는 등록 초안',
    description: '카테고리와 속성, 판매가 정책을 마켓별 형식으로 구성해 최종 검토할 초안을 만듭니다.',
  },
];

const faqs = [
  {
    question: '엑셀을 잘 다루지 못해도 사용할 수 있나요?',
    answer: '네. 처음 한 번 상품명, 가격, 옵션처럼 필요한 열을 연결하면 같은 공급사 파일에는 저장한 설정을 다시 사용할 수 있습니다.',
  },
  {
    question: '상품이 바로 네이버와 쿠팡에 등록되나요?',
    answer: '현재는 마켓별 상품 정보와 등록 초안을 준비하고 검토하는 단계까지 지원합니다. 최종 전송 전에는 판매자가 내용을 확인할 수 있습니다.',
  },
  {
    question: '상표권 문제를 완전히 막을 수 있나요?',
    answer: 'KIPRIS 조회와 금지어 검사를 통해 의심 키워드를 찾고 제외 근거를 보여줍니다. 최종 법적 판단을 대신하지는 않으며 판매 전 확인 절차를 줄이는 보조 도구입니다.',
  },
  {
    question: '어떤 쇼핑몰을 지원하나요?',
    answer: '현재 네이버 스마트스토어와 쿠팡용 카테고리, 속성, 등록 초안 준비 흐름을 중심으로 지원합니다.',
  },
];

function DemoCta({ className }: { className?: string }) {
  if (!demoFormUrl) {
    return (
      <button className={className} type="button" disabled>
        데모 신청 준비 중
      </button>
    );
  }

  return (
    <a className={className} href={demoFormUrl} target="_blank" rel="noopener noreferrer">
      데모 신청
    </a>
  );
}

export default function LandingPage() {
  return (
    <div className={styles.page}>
      <section className={styles.hero} aria-labelledby="hero-title">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>AI COMMERCE WORKSPACE</p>
          <h1 id="hero-title">상품 등록 준비를,<br />한 번의 업로드로.</h1>
          <p className={styles.heroDescription}>
            복잡한 공급사 엑셀을 올리면 Auto-Selp가 상품명, 키워드, 상표권 확인,
            마켓별 카테고리와 속성을 검토 가능한 초안으로 정리합니다.
          </p>
          <div className={styles.heroActions}>
            <DemoCta className={styles.primaryAction} />
            <a className={styles.textAction} href="#product-demo">제품 데모 보기 <span aria-hidden="true">↓</span></a>
          </div>
        </div>
        <ProductDemo />
      </section>

      <section className={styles.trustBar} aria-label="지원 범위">
        <p>혼자 운영해도 놓치지 않도록</p>
        <div className={styles.trustItems}>
          <span>NAVER 스마트스토어</span>
          <span>쿠팡</span>
          <span>KIPRIS</span>
          <span>Excel</span>
        </div>
      </section>

      <section className={styles.workflowSection} id="workflow" aria-labelledby="workflow-title">
        <div className={styles.sectionIntro}>
          <p className={styles.sectionLabel}>작동 방식</p>
          <h2 id="workflow-title">반복 작업은 줄이고,<br />확인할 일만 남깁니다.</h2>
        </div>
        <div className={styles.workflowGrid}>
          {workflow.map((item) => (
            <article className={styles.workflowItem} key={item.number}>
              <span className={styles.workflowNumber}>{item.number}</span>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.capabilitiesSection} id="features" aria-labelledby="features-title">
        <div className={styles.capabilitiesInner}>
          <div className={styles.sectionIntroDark}>
            <p className={styles.sectionLabel}>핵심 기능</p>
            <h2 id="features-title">판매자가 결정하고,<br />AI가 준비합니다.</h2>
            <p>자동화 결과와 근거를 함께 보여주어 마지막 판단은 판매자가 할 수 있습니다.</p>
          </div>
          <div className={styles.capabilityList}>
            {capabilities.map((item) => (
              <article className={styles.capabilityItem} key={item.label}>
                <span>{item.label}</span>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={styles.faqSection} id="faq" aria-labelledby="faq-title">
        <div className={styles.faqIntro}>
          <p className={styles.sectionLabel}>자주 묻는 질문</p>
          <h2 id="faq-title">처음 시작하기 전에</h2>
        </div>
        <div className={styles.faqList}>
          {faqs.map((item) => (
            <details key={item.question}>
              <summary>{item.question}</summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className={styles.contactSection} id="contact" aria-labelledby="contact-title">
        <div>
          <p className={styles.sectionLabel}>Auto-Selp 데모</p>
          <h2 id="contact-title">내 상품 파일로 직접 확인해 보세요.</h2>
          <p>데모 신청 채널을 준비하고 있습니다. 오픈 전에는 로그인해 현재 제품을 확인할 수 있습니다.</p>
        </div>
        <div className={styles.contactActions}>
          <DemoCta className={styles.primaryAction} />
          <Link className={styles.secondaryAction} href="/login">로그인</Link>
        </div>
      </section>

      <footer className={styles.footer}>
        <Link href="/" className={styles.footerBrand}>Auto-Selp</Link>
        <p>상품 가공부터 마켓 등록 준비까지, 1인 셀러를 위한 AI 워크스페이스.</p>
        <div>
          <a href="#workflow">작동 방식</a>
          <a href="#features">핵심 기능</a>
          <Link href="/login">로그인</Link>
        </div>
        <small>© {new Date().getFullYear()} Auto-Selp</small>
      </footer>
    </div>
  );
}
