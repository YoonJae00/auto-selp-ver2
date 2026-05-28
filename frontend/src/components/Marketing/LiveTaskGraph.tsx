'use client';

import React, { useState, useEffect, useRef } from 'react';
import styles from './LiveTaskGraph.module.css';

interface SimulationStep {
  id: string;
  name: string;
  icon: string;
  title: string;
  desc: string;
  input: string;
  output: Record<string, any>;
}

const SIMULATION_STEPS: SimulationStep[] = [
  {
    id: 'upload',
    name: '도매처 업로드',
    icon: '📤',
    title: '도매처 엑셀 대장 원본 업로드',
    desc: '도매 사이트에서 내려받은 수천 개의 상품 엑셀 파일을 클릭 한 번으로 업로드하고 구문을 매핑합니다.',
    input: '파일명: wholesale_keyboard_list.xlsx (용량 14.2MB)',
    output: {
      '원본 상품명': '[초특가/대박] 🔥로지텍 호환 기계식 게이밍 키보드 108키 갈축 (정품박스포함) 실물깡패 사은품증정',
      '도매 가격': '59,000원',
      '현재 재고': '42개',
      '공급처': '도매짱'
    }
  },
  {
    id: 'refining',
    name: '상품명 가공',
    icon: '✏️',
    title: 'AI 기반 검색 친화적 상품명 정제',
    desc: '불필요한 홍보용 수식어, 특수문자, 중복 키워드를 완벽히 제거하고 최적의 글자 수로 브랜드 중심의 검색어를 생성합니다.',
    input: '[초특가/대박] 🔥로지텍 호환 기계식 게이밍 키보드 108키 갈축 (정품박스포함) 실물깡패 사은품증정',
    output: {
      '가공 완료 상품명': '로지텍 호환 기계식 게이밍 키보드 갈축 108키',
      '정제 결과': '비품어 및 중복 단어 12개 정제 완료',
      '최적화 등급': 'A+ (노출 최적화 점수 98점)',
      '단축률': '텍스트 길이 52% 감축'
    }
  },
  {
    id: 'keywords',
    name: '키워드 & 상표권',
    icon: '🔍',
    title: '검색조회수 분석 & KIPRIS 특허 검증',
    desc: '네이버 검색광고 API 조회수를 실시간 연동하고, KIPRIS 특허청 상표 DB와 매칭하여 지재권 분쟁 우려가 있는 키워드를 자동차단합니다.',
    input: '추출 키워드 후보: 로지텍, 기계식 키보드, 게이밍 키보드, 사은품 키보드',
    output: {
      '추출된 추천 키워드': ['기계식 키보드 (월 12,400회)', '게이밍 키보드 (월 8,500회)', '갈축 키보드 (월 3,200회)'],
      '상표권 필터링 대상': '로지텍 (KIPRIS 등록 타사 상표 감지 - 즉시 제외)',
      '검증 시스템': '⚠️ 상표권 침해 자동차단 완료 (검증 신뢰도 99.8%)'
    }
  },
  {
    id: 'categorizing',
    name: '카테고리 매핑',
    icon: '📂',
    title: 'AI 멀티 마켓 카테고리 매핑',
    desc: '정제된 상품명과 키워드를 기반으로 네이버 스마트스토어와 쿠팡 윙의 공식 카테고리 코드를 100% 매칭합니다.',
    input: '로지텍 호환 기계식 게이밍 키보드 갈축 108키',
    output: {
      '네이버 스마트스토어': '디지털/가전 > 컴퓨터 주변기기 > 키보드 > 기계식키보드 (카테고리 코드: 50002933)',
      '쿠팡 윙': '가전디지털 > 컴퓨터 > 키보드/마우스 > 키보드 (카테고리 코드: 78912)',
      '매핑 신뢰도': '97.2%'
    }
  },
  {
    id: 'sync',
    name: '스마트 갱신',
    icon: '💾',
    title: 'Smart Upsert 엔진 기반 DB 반영',
    desc: '기존 데이터베이스와 가격/옵션/품절 상태의 실시간 변동을 비교 연산하여 스마트 업데이트하고 쇼핑몰 전송 상태로 저장합니다.',
    input: '상품 ID: PROD-98104',
    output: {
      '저장소': 'PostgreSQL 데이터베이스 안전 저장',
      '스마트 분석': '가격 변동 감지 (59,000원 -> 54,000원) · 재고 유지',
      '쇼핑몰 동기화': '네이버/쿠팡 전송 대기 완료 (준비 상태)',
      '최종 처리 시간': '0.18초'
    }
  }
];

export default function LiveTaskGraph() {
  const [activeStepIdx, setActiveStepIdx] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [simSpeed, setSimSpeed] = useState<number>(3000); // 3 seconds per step
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const startTimer = () => {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setActiveStepIdx((prev) => (prev + 1) % SIMULATION_STEPS.length);
      }, simSpeed);
    };

    if (isPlaying) {
      startTimer();
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, simSpeed]);

  const handleStepClick = (idx: number) => {
    setIsPlaying(false);
    setActiveStepIdx(idx);
  };

  const togglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  const handleNext = () => {
    setIsPlaying(false);
    setActiveStepIdx((prev) => (prev + 1) % SIMULATION_STEPS.length);
  };

  const handlePrev = () => {
    setIsPlaying(false);
    setActiveStepIdx((prev) => (prev - 1 + SIMULATION_STEPS.length) % SIMULATION_STEPS.length);
  };

  const resetSimulation = () => {
    setIsPlaying(false);
    setActiveStepIdx(0);
  };

  const activeStep = SIMULATION_STEPS[activeStepIdx];

  return (
    <div className={styles.container}>
      <div className={styles.glassPanel}>
        {/* Panel Header */}
        <div className={styles.header}>
          <div className={styles.pulseIndicator}>
            <span className={styles.pulseDot} />
            <span className={styles.headerText}>LIVE DATA PIPELINE SIMULATOR</span>
          </div>
          <div className={styles.controls}>
            <button 
              className={`${styles.controlBtn} ${styles.navBtn}`} 
              onClick={handlePrev}
              title="이전 단계"
            >
              ◀
            </button>
            <button 
              className={`${styles.controlBtn} ${isPlaying ? styles.pauseBtn : styles.playBtn}`} 
              onClick={togglePlay}
            >
              {isPlaying ? '⏸ 일시정지' : '▶ 시뮬레이션 시작'}
            </button>
            <button 
              className={`${styles.controlBtn} ${styles.navBtn}`} 
              onClick={handleNext}
              title="다음 단계"
            >
              ▶
            </button>
            <button className={`${styles.controlBtn} ${styles.resetBtn}`} onClick={resetSimulation}>
              ↺ 초기화
            </button>
            <div className={styles.speedSelect}>
              <button 
                className={`${styles.speedBtn} ${simSpeed === 4500 ? styles.speedActive : ''}`} 
                onClick={() => setSimSpeed(4500)}
              >
                느리게
              </button>
              <button 
                className={`${styles.speedBtn} ${simSpeed === 3000 ? styles.speedActive : ''}`} 
                onClick={() => setSimSpeed(3000)}
              >
                보통
              </button>
              <button 
                className={`${styles.speedBtn} ${simSpeed === 1500 ? styles.speedActive : ''}`} 
                onClick={() => setSimSpeed(1500)}
              >
                빠르게
              </button>
            </div>
          </div>
        </div>

        {/* Visual Graph Layout */}
        <div className={styles.graphLayout}>
          {/* Node Graph Column */}
          <div className={styles.graphArea}>
            <div className={styles.nodesWrapper}>
              {SIMULATION_STEPS.map((step, idx) => {
                const isActive = activeStepIdx === idx;
                const isPassed = activeStepIdx > idx;
                
                return (
                  <div 
                    key={step.id} 
                    className={`${styles.nodeContainer} ${isActive ? styles.nodeActive : ''} ${isPassed ? styles.nodePassed : ''}`}
                    onClick={() => handleStepClick(idx)}
                  >
                    <div className={styles.nodeIconWrapper}>
                      <span className={styles.nodeIcon}>{step.icon}</span>
                      <div className={styles.nodeGlowRing} />
                    </div>
                    <span className={styles.nodeLabel}>{step.name}</span>
                    {isActive && <div className={styles.pulseRadar} />}
                  </div>
                );
              })}
            </div>

            {/* SVG Connecting Edges with active animated flow particles */}
            <svg className={styles.svgEdges} width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
              <defs>
                <linearGradient id="edgeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#0066cc" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity="0.8" />
                </linearGradient>
                <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="2" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Edge 1: Upload -> Refining */}
              <path 
                className={`${styles.edgeBg} ${activeStepIdx >= 1 ? styles.edgePassed : ''}`} 
                d="M 10,50 L 30,50" 
              />
              {activeStepIdx === 0 && isPlaying && (
                <path className={styles.edgeFlow} d="M 10,50 L 30,50" filter="url(#glow)" />
              )}

              {/* Edge 2: Refining -> Keywords */}
              <path 
                className={`${styles.edgeBg} ${activeStepIdx >= 2 ? styles.edgePassed : ''}`} 
                d="M 30,50 L 50,50" 
              />
              {activeStepIdx === 1 && isPlaying && (
                <path className={styles.edgeFlow} d="M 30,50 L 50,50" filter="url(#glow)" />
              )}

              {/* Edge 3: Keywords -> Categorizing */}
              <path 
                className={`${styles.edgeBg} ${activeStepIdx >= 3 ? styles.edgePassed : ''}`} 
                d="M 50,50 L 70,50" 
              />
              {activeStepIdx === 2 && isPlaying && (
                <path className={styles.edgeFlow} d="M 50,50 L 70,50" filter="url(#glow)" />
              )}

              {/* Edge 4: Categorizing -> Sync */}
              <path 
                className={`${styles.edgeBg} ${activeStepIdx >= 4 ? styles.edgePassed : ''}`} 
                d="M 70,50 L 90,50" 
              />
              {activeStepIdx === 3 && isPlaying && (
                <path className={styles.edgeFlow} d="M 70,50 L 90,50" filter="url(#glow)" />
              )}
            </svg>
          </div>

          {/* Details & Terminal Panel */}
          <div className={styles.detailsArea}>
            <div className={styles.detailsCard}>
              <div className={styles.detailsHeader}>
                <span className={styles.detailsIcon}>{activeStep.icon}</span>
                <div className={styles.detailsTitleWrapper}>
                  <h4 className={styles.detailsTitle}>{activeStep.title}</h4>
                  <span className={styles.detailsSubtitle}>Pipeline Stage {activeStepIdx + 1}/5</span>
                </div>
              </div>
              
              <p className={styles.detailsDesc}>{activeStep.desc}</p>
              
              <div className={styles.ioWrapper}>
                <div className={styles.ioBox}>
                  <span className={styles.ioLabel}>INPUT DATA</span>
                  <div className={styles.ioContentInput}>{activeStep.input}</div>
                </div>

                <div className={styles.ioBox}>
                  <span className={styles.ioLabel}>AI PROCESSING OUTPUT</span>
                  <div className={styles.ioContentOutput}>
                    {Object.entries(activeStep.output).map(([key, val]) => (
                      <div key={key} className={styles.outputRow}>
                        <span className={styles.outputKey}>{key}:</span>
                        <span className={styles.outputVal}>
                          {Array.isArray(val) ? (
                            <div className={styles.outputBadgeList}>
                              {val.map((v, i) => (
                                <span key={i} className={styles.keywordBadge}>
                                  {v}
                                </span>
                              ))}
                            </div>
                          ) : typeof val === 'string' && val.startsWith('⚠️') ? (
                            <span className={styles.alertVal}>{val}</span>
                          ) : typeof val === 'string' && val.includes('즉시 제외') ? (
                            <span className={styles.dangerVal}>{val}</span>
                          ) : (
                            <strong>{val}</strong>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
