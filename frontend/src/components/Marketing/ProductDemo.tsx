'use client';

import Image from 'next/image';
import { useState } from 'react';
import styles from './ProductDemo.module.css';

const stages = [
  {
    shortLabel: '업로드',
    label: '엑셀 업로드',
    title: '248개 상품을 읽었습니다',
    description: '저장된 공급사 설정으로 상품명, 공급가, 옵션 열을 연결했습니다.',
    meta: '열 매핑 7개 · 누락 0개',
  },
  {
    shortLabel: '상품명',
    label: '상품명 정제',
    title: '불필요한 표현을 정리했습니다',
    description: '반복 단어와 특수문자를 제거하고 상품 특징이 먼저 보이도록 이름을 다듬었습니다.',
    meta: '원본 보존 · 변경 이력 기록',
  },
  {
    shortLabel: '키워드',
    label: '키워드와 상표권',
    title: '판매 전 확인할 키워드를 분리했습니다',
    description: '검색 키워드를 선별하고 상표권 의심어는 제외 사유와 함께 표시했습니다.',
    meta: '추천 10개 · 확인 필요 1개',
  },
  {
    shortLabel: '카테고리',
    label: '카테고리 매핑',
    title: '마켓별 분류를 찾았습니다',
    description: '같은 상품을 네이버 스마트스토어와 쿠팡의 서로 다른 카테고리 체계에 맞췄습니다.',
    meta: '네이버 97% · 쿠팡 95% 신뢰도',
  },
  {
    shortLabel: '초안',
    label: '등록 초안',
    title: '검토할 등록 초안이 준비됐습니다',
    description: '상품명, 키워드, 카테고리와 속성을 마켓별 초안으로 묶었습니다.',
    meta: '스마트스토어 · 쿠팡',
  },
];

export default function ProductDemo() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeStage = stages[activeIndex];

  return (
    <div className={styles.shell} id="product-demo">
      <div className={styles.windowBar}>
        <div>
          <span className={styles.statusDot} />
          <span>상품 가공 워크스페이스</span>
        </div>
        <span className={styles.sampleBadge}>예시 데이터</span>
      </div>

      <div className={styles.stageTabs} role="tablist" aria-label="상품 가공 단계">
        {stages.map((stage, index) => (
          <button
            key={stage.shortLabel}
            type="button"
            role="tab"
            aria-selected={activeIndex === index}
            aria-controls="demo-stage-panel"
            className={activeIndex === index ? styles.activeTab : undefined}
            onClick={() => setActiveIndex(index)}
          >
            <span>{String(index + 1).padStart(2, '0')}</span>
            {stage.shortLabel}
          </button>
        ))}
      </div>

      <div className={styles.workspace} id="demo-stage-panel" role="tabpanel" tabIndex={0}>
        <div className={styles.productPreview}>
          <Image
            src="/product-assortment.webp"
            alt="조명, 보온병, 데스크 정리함과 운동화 상품 예시"
            width={1536}
            height={1024}
            priority
            sizes="(max-width: 720px) 100vw, 46vw"
          />
          <div className={styles.fileInfo}>
            <span>supplier_products_07.xlsx</span>
            <strong>248개 상품</strong>
          </div>
        </div>

        <div className={styles.stageDetail}>
          <p className={styles.stageLabel}>{activeStage.label}</p>
          <h2>{activeStage.title}</h2>
          <p className={styles.stageDescription}>{activeStage.description}</p>
          <div className={styles.nameComparison}>
            <div>
              <span>원본 상품명</span>
              <p>[행사특가] 북유럽 감성 크림 미니 버섯램프!!!</p>
            </div>
            <div>
              <span>정제 상품명</span>
              <p>크림 미니 테이블 조명</p>
            </div>
          </div>
          <p className={styles.stageMeta}>{activeStage.meta}</p>
        </div>
      </div>
    </div>
  );
}
