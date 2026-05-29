# Hotfix Plan: Expand Product Columns with Raw Metadata & AI Attributes (2026-05-30)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상품 관리 테이블에 대표 썸네일, 상세이미지 URL 바로가기, AI 정밀 가공 속성 리스트, 원본 메타데이터 JSON 뷰어 및 브랜드명, 원본 옵션 등 누락된 모든 가치 있는 데이터 필드들을 열 설정에 실시간 연동 가능한 정식 컬럼으로 추가 구현합니다.

**Architecture:** 기존 Native D&D 및 localStorage 열 설정 상태 모델을 그대로 계승하여, `DEFAULT_ORDER` 및 `COLUMNS_REGISTRY`를 17개에서 23개 이상의 모든 데이터 열 구조로 확장합니다. CSS Module에 필요한 프리미엄 마감 디자인 요소들(썸네일 줌인, 상세 보기 링크, JSON 뷰어 절대좌표 팝업)을 추가하고 Next.js 컴파일 검증을 마칩니다.

**Tech Stack:** Next.js (App Router), TypeScript, Vanilla CSS.

---

## 🛠️ 구현 작업 계획 (Tasks)

### Task 1: CSS Module 추가 스타일 정의
**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/products.module.css`

- [ ] **Step 1: CSS 클래스 추가**
  썸네일 이미지, 가공 속성 태그, 원본 JSON 뷰어 팝업 절대좌표 처리를 위한 CSS를 추가합니다.
  
  ```css
  /* 테이블 썸네일 이미지 및 마우스 호버 확대 효과 */
  .tableThumbnail {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    object-fit: cover;
    border: 1px solid var(--hairline);
    transition: transform 0.2s ease-in-out;
    cursor: pointer;
  }
  
  .tableThumbnail:hover {
    transform: scale(2.5);
    z-index: 10;
    position: relative;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
  
  /* 상세 보기 링크 버튼 */
  .detailLinkBtn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 5px 9px;
    background: #f4f6f8;
    color: var(--primary) !important;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    text-decoration: none;
    border: 1px solid rgba(0, 0, 0, 0.03);
    transition: all 0.15s ease-in-out;
  }
  
  .detailLinkBtn:hover {
    background: #eef5fc;
    border-color: var(--primary);
  }
  
  /* 가공 경고 뱃지 */
  .warningPill {
    display: inline-flex;
    align-items: center;
    padding: 3px 7px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 650;
    color: #ff3b30;
    background: rgba(255, 59, 48, 0.1);
    border: 1px solid rgba(255, 59, 48, 0.2);
  }
  
  /* 가공 속성 컴팩트 태그 */
  .attributeGroup {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-width: 320px;
  }
  
  .platformAttrTitle {
    font-size: 10px;
    font-weight: 800;
    color: var(--ink-muted-48);
    text-transform: uppercase;
    margin-bottom: 2px;
  }
  
  .attributeTag {
    display: inline-block;
    font-size: 11px;
    background: #f0f4f8;
    color: var(--ink-muted-80);
    padding: 2px 6px;
    border-radius: 4px;
    margin: 2px;
    border: 1px solid rgba(0, 0, 0, 0.04);
  }
  
  /* 원본 데이터 뷰어 Details */
  .rawMetaDetails {
    position: relative;
    max-width: 200px;
  }
  
  .rawMetaSummary {
    list-style: none;
    cursor: pointer;
    font-size: 11px;
    font-weight: 700;
    color: var(--primary);
    padding: 5px 9px;
    border-radius: 6px;
    background: #f4f6f8;
    display: inline-block;
    border: 1px solid rgba(0, 0, 0, 0.03);
    user-select: none;
  }
  
  .rawMetaSummary::-webkit-details-marker {
    display: none;
  }
  
  .rawMetaSummary:hover {
    background: #eef5fc;
  }
  
  .rawMetaContent {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 50;
    width: 300px;
    max-height: 240px;
    overflow-y: auto;
    background: #ffffff;
    border: 1px solid var(--hairline);
    border-radius: 8px;
    padding: 10px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
    font-size: 12px;
    text-align: left;
  }
  
  .rawMetaLine {
    margin-bottom: 5px;
    line-height: 1.4;
    word-break: break-all;
    border-bottom: 1px dashed rgba(0, 0, 0, 0.03);
    padding-bottom: 4px;
  }
  
  .rawMetaLine:last-child {
    margin-bottom: 0;
    border-bottom: none;
    padding-bottom: 0;
  }
  
  .rawMetaKey {
    color: var(--ink-muted-80);
    margin-right: 6px;
    font-weight: 700;
  }
  
  .rawMetaVal {
    color: var(--ink);
  }
  ```

- [ ] **Step 2: 커밋**
  ```bash
  git commit -am "style: add styles for new metadata and thumbnail columns"
  ```

---

### Task 2: Page Registry 및 렌더링 스위치 케이스 확장
**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/page.tsx`

- [ ] **Step 1: 컬럼 리스트 및 한글 설정 확장**
  기본 노출 및 전체 컬럼 세트(23개 이상)로 순서 및 가시성 매핑 리스트를 전면 개편합니다.
  
  ```typescript
  // page.tsx 내 상단 상수 수정
  const DEFAULT_ORDER = [
    'checkbox',
    'main_image',
    'refined_name',
    'original_name',
    'brand_name',
    'keywords',
    'option_variants',
    'option_values_raw',
    'platform_mappings',
    'mapped_attributes',
    'warnings',
    'status',
    'raw_metadata',
    'image_detail',
    'product_code',
    'wholesale_product_id',
    'price_wholesale',
    'price_retail',
    'price_min_selling',
    'origin',
    'wholesale_status',
    'wholesale_registered_at',
    'created_at'
  ];
  
  const DEFAULT_VISIBILITY: Record<string, boolean> = {
    checkbox: true,
    main_image: true,
    refined_name: true,
    original_name: true,
    brand_name: true,
    keywords: true,
    option_variants: true,
    option_values_raw: false,
    platform_mappings: true,
    mapped_attributes: true,
    warnings: true,
    status: true,
    raw_metadata: true,
    image_detail: false,
    product_code: false,
    wholesale_product_id: false,
    price_wholesale: false,
    price_retail: false,
    price_min_selling: false,
    origin: false,
    wholesale_status: false,
    wholesale_registered_at: false,
    created_at: true
  };
  
  const COLUMNS_REGISTRY: Record<string, string> = {
    checkbox: '',
    main_image: '대표 이미지',
    refined_name: '상품 명칭',
    original_name: '원래 상품명',
    brand_name: '브랜드명',
    keywords: '정제 키워드',
    option_variants: '옵션',
    option_values_raw: '옵션 원본',
    platform_mappings: '마켓 카테고리 매핑',
    mapped_attributes: '가공 속성',
    warnings: 'AI 가공 경고',
    status: '가공 상태',
    raw_metadata: '원본 데이터',
    image_detail: '상세이미지 URL',
    product_code: '상품 코드',
    wholesale_product_id: '도매처 상품 ID',
    price_wholesale: '도매가',
    price_retail: '소매가',
    price_min_selling: '최소 판매가',
    origin: '원산지',
    wholesale_status: '도매 상태',
    wholesale_registered_at: '도매 등록일',
    created_at: '등록 시각'
  };
  ```

- [ ] **Step 2: `<tbody>` 내 Switch-case 전체 확장**
  추가된 컬럼들에 매핑되는 새로운 렌더링 분기(`case`)를 하나도 빠짐없이 작성합니다.
  
  - `main_image` 분기:
    ```tsx
    case 'main_image': {
      // images_list[0] 검출 또는 raw_metadata의 이미지 주소 검출
      let imgSrc = '';
      if (p.images_list && p.images_list.length > 0) {
        imgSrc = p.images_list[0];
      } else if (p.raw_metadata) {
        imgSrc = p.raw_metadata['목록이미지1'] || p.raw_metadata['목록이미지'] || '';
      }
      return (
        <td key={colKey}>
          {imgSrc ? (
            <img src={imgSrc} className={styles.tableThumbnail} alt="Product Thumb" />
          ) : (
            <span className={styles.emptyInline}>이미지 없음</span>
          )}
        </td>
      );
    }
    ```
    
  - `mapped_attributes` 분기:
    ```tsx
    case 'mapped_attributes': {
      const naver = p.platform_mappings.find((m) => m.platform_name === 'naver');
      const coupang = p.platform_mappings.find((m) => m.platform_name === 'coupang');
      
      const hasNaverAttrs = naver?.mapped_attributes && Object.keys(naver.mapped_attributes).length > 0;
      // 쿠팡 속성은 product_attributes 또는 item_attributes 검출
      const hasCoupangAttrs = coupang?.mapped_attributes && 
        (coupang.mapped_attributes.product_attributes?.length > 0 || 
         coupang.mapped_attributes.item_attributes?.length > 0);
         
      return (
        <td key={colKey}>
          <div className={styles.attributeGroup}>
            {hasNaverAttrs && (
              <div>
                <div className={styles.platformAttrTitle}>Naver</div>
                {Object.entries(naver.mapped_attributes).map(([k, v]) => (
                  <span key={k} className={styles.attributeTag}>{k}: {String(v)}</span>
                ))}
              </div>
            )}
            {hasCoupangAttrs && (
              <div>
                <div className={styles.platformAttrTitle}>Coupang</div>
                {coupang.mapped_attributes.product_attributes?.slice(0, 4).map((attr: any, i: number) => (
                  <span key={i} className={styles.attributeTag}>
                    {attr.attributeTypeName}: {attr.attributeValueName}
                  </span>
                ))}
              </div>
            )}
            {!hasNaverAttrs && !hasCoupangAttrs && (
              <span className={styles.emptyInline}>가공된 속성 없음</span>
            )}
          </div>
        </td>
      );
    }
    ```

  - `warnings` 분기:
    ```tsx
    case 'warnings': {
      const warningCount = p.warnings ? Object.keys(p.warnings).length : 0;
      return (
        <td key={colKey}>
          {warningCount > 0 ? (
            <span 
              className={styles.warningPill} 
              title={JSON.stringify(p.warnings, null, 2)}
              style={{ cursor: 'help' }}
            >
              ⚠️ 경고 {warningCount}건
            </span>
          ) : (
            <span className={styles.emptyInline}>경고 없음</span>
          )}
        </td>
      );
    }
    ```

  - `raw_metadata` 분기:
    ```tsx
    case 'raw_metadata': {
      return (
        <td key={colKey}>
          <details className={styles.rawMetaDetails}>
            <summary className={styles.rawMetaSummary}>🔍 원본 보기</summary>
            <div className={styles.rawMetaContent}>
              {p.raw_metadata && Object.keys(p.raw_metadata).length > 0 ? (
                Object.entries(p.raw_metadata).map(([k, v]) => (
                  <div key={k} className={styles.rawMetaLine}>
                    <strong className={styles.rawMetaKey}>{k}:</strong>
                    <span className={styles.rawMetaVal}>{String(v)}</span>
                  </div>
                ))
              ) : (
                <div className={styles.emptyInline}>원본 정보 없음</div>
              )}
            </div>
          </details>
        </td>
      );
    }
    ```

  - `image_detail` 분기:
    ```tsx
    case 'image_detail': {
      //상세페이지 HTML에서 이미지 추출 또는 원본 텍스트 주소 검출
      let detailUrl = '';
      if (p.image_detail) {
        if (p.image_detail.startsWith('http')) {
          detailUrl = p.image_detail;
        } else {
          // HTML에서 첫 img tag의 src 추출 시도
          const match = p.image_detail.match(/src=["'](https?:\/\/[^"']+)["']/i);
          if (match) {
            detailUrl = match[1];
          }
        }
      } else if (p.raw_metadata) {
        detailUrl = p.raw_metadata['상세이미지'] || '';
        if (detailUrl && !detailUrl.startsWith('http')) {
          const match = detailUrl.match(/src=["'](https?:\/\/[^"']+)["']/i);
          if (match) {
            detailUrl = match[1];
          }
        }
      }
      return (
        <td key={colKey}>
          {detailUrl ? (
            <a 
              href={detailUrl} 
              target="_blank" 
              rel="noopener noreferrer" 
              className={styles.detailLinkBtn}
            >
              🔗 상세 이미지 보기
            </a>
          ) : (
            <span className={styles.emptyInline}>URL 없음</span>
          )}
        </td>
      );
    }
    ```

- [ ] **Step 3: 컴파일 빌드 검사**
  에러 없이 빌드가 되는지 확인 후 커밋합니다.
  ```bash
  git commit -am "hotfix: expand columns with metadata viewer and dynamic platform mappings"
  ```
