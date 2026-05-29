# 상품 관리 테이블 열 노출 설정 및 드래그 순서 재정렬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상품 관리 테이블에서 모든 17개 필드를 자유롭게 노출 여부를 조절하고, 테이블 헤더를 마우스 드래그 앤 드롭하여 열 순서를 변경하며, 설정을 `localStorage`에 자동 보관합니다.

**Architecture:** HTML5 Native Drag & Drop API와 React Client-side State를 조합해 외부 종속성 없이 가볍고 부드러운 테이블 열 재정렬을 구현합니다. Next.js Hydration을 고려해 `useEffect` 마운트 후 로컬 스토리지 데이터 복구 프로세스를 안정적으로 처리합니다.

**Tech Stack:** Next.js (App Router), TypeScript, Vanilla CSS (CSS Modules), LocalStorage.

---

## 🛠️ 구현 작업 계획 (Tasks)

### Task 1: CSS 스타일 구현
**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/products.module.css`

- [x] **Step 1: CSS 클래스 추가**
  기존 CSS 파일 하단에 드래그 앤 드롭 효과 지시자 및 열 설정 팝오버용 Glassmorphism 스타일을 추가합니다.
  
  ```css
  /* 열 설정 버튼 및 팝오버 컨테이너 */
  .columnSettingsContainer {
    position: relative;
    display: inline-block;
  }
  
  .columnSettingsPopover {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    z-index: 100;
    width: 240px;
    max-height: 380px;
    overflow-y: auto;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--hairline);
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  }
  
  .popoverHeader {
    font-size: 11px;
    font-weight: 750;
    color: var(--ink-muted-48);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--hairline);
  }
  
  .popoverList {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  
  .popoverItem {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    cursor: pointer;
    color: var(--ink-muted-80);
    user-select: none;
  }
  
  .popoverItem input {
    cursor: pointer;
  }
  
  /* 드래그 상태 전용 CSS */
  .thDraggable {
    cursor: grab;
    user-select: none;
    position: relative;
  }
  
  .thDraggable:active {
    cursor: grabbing;
  }
  
  .thDragging {
    opacity: 0.3;
    background: #eef1f6 !important;
  }
  
  /* 드롭 안내 블루 인디케이터 (Apple Blue) */
  .dragIndicatorLeft::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background-color: var(--primary);
    box-shadow: 0 0 4px var(--primary);
    z-index: 10;
  }
  
  .dragIndicatorRight::before {
    content: '';
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background-color: var(--primary);
    box-shadow: 0 0 4px var(--primary);
    z-index: 10;
  }
  ```

- [x] **Step 2: CSS 파일 검증**
  에러 없이 CSS 스타일이 파싱되는지 눈으로 확인합니다.
- [x] **Step 3: 커밋 수행**
  ```bash
  git add frontend/src/app/\(ai-mall\)/products/products.module.css
  git commit -m "style: add dynamic column reordering & settings popover CSS"
  ```

---

### Task 2: 컬럼 관리 React State 정의 및 로컬 스토리지 동기화
**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/page.tsx`

- [ ] **Step 1: 컬럼 메타데이터 정의 및 React State 선언**
  `ProductsPage` 상단 컴포넌트 바깥에 컬럼 레지스트리 및 기본값을 정의하고, 컴포넌트 내부 State를 구성합니다. Next.js의 클라이언트 컴포넌트 내부 `useEffect` 마운트 시점에 로컬스토리지를 검사해 복원합니다.
  
  ```typescript
  // page.tsx의 ProductsPage 바깥에 배치
  const DEFAULT_ORDER = [
    'checkbox',
    'refined_name',
    'original_name',
    'keywords',
    'option_variants',
    'platform_mappings',
    'status',
    'created_at',
    'product_code',
    'wholesale_product_id',
    'price_wholesale',
    'price_retail',
    'price_min_selling',
    'origin',
    'brand_name',
    'wholesale_status',
    'wholesale_registered_at'
  ];
  
  const DEFAULT_VISIBILITY: Record<string, boolean> = {
    checkbox: true,
    refined_name: true,
    original_name: true,
    keywords: true,
    option_variants: true,
    platform_mappings: true,
    status: true,
    created_at: true,
    product_code: false,
    wholesale_product_id: false,
    price_wholesale: false,
    price_retail: false,
    price_min_selling: false,
    origin: false,
    brand_name: false,
    wholesale_status: false,
    wholesale_registered_at: false
  };
  
  const COLUMNS_REGISTRY: Record<string, string> = {
    checkbox: '',
    refined_name: '상품 명칭',
    original_name: '원래 상품명',
    keywords: '정제 키워드',
    option_variants: '옵션',
    platform_mappings: '마켓 카테고리 매핑',
    status: '가공 상태',
    created_at: '등록 시각',
    product_code: '상품 코드',
    wholesale_product_id: '도매처 상품 ID',
    price_wholesale: '도매가',
    price_retail: '소매가',
    price_min_selling: '최소 판매가',
    origin: '원산지',
    brand_name: '브랜드명',
    wholesale_status: '도매 상태',
    wholesale_registered_at: '도매 등록일'
  };
  ```

  `ProductsPage` 내부에 상태와 초기 로드 효과 구현:
  ```typescript
  const [columnOrder, setColumnOrder] = useState<string[]>(DEFAULT_ORDER);
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(DEFAULT_VISIBILITY);
  const [showSettings, setShowSettings] = useState(false);
  
  // 드래그 앤 드롭을 위한 상태
  const [draggedColKey, setDraggedColKey] = useState<string | null>(null);
  const [dragOverColKey, setDragOverColKey] = useState<string | null>(null);
  const [dragDirection, setDragDirection] = useState<'left' | 'right' | null>(null);
  
  // 마운트 직후 localStorage에서 설정 복구 (SSR 하이드레이션 오류 우회)
  useEffect(() => {
    try {
      const saved = localStorage.getItem('autoselp_product_columns_config');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.order && Array.isArray(parsed.order)) {
          setColumnOrder(parsed.order);
        }
        if (parsed.visibility) {
          // checkbox는 무조건 true 고정 보호
          setColumnVisibility({ ...parsed.visibility, checkbox: true });
        }
      }
    } catch (e) {
      console.error('Failed to load columns config from localStorage', e);
    }
  }, []);
  
  // 열 변경 시 로컬스토리지 저장 유틸
  const updateConfig = (newOrder: string[], newVisibility: Record<string, boolean>) => {
    setColumnOrder(newOrder);
    setColumnVisibility(newVisibility);
    try {
      localStorage.setItem('autoselp_product_columns_config', JSON.stringify({
        order: newOrder,
        visibility: newVisibility
      }));
    } catch (e) {
      console.error(e);
    }
  };
  ```

- [ ] **Step 2: 수동 열 토글 함수 구현**
  체크박스로 열을 켜고 끌 때 호출되는 유틸을 컴포넌트 내부에 추가합니다.
  ```typescript
  const toggleColumnVisibility = (key: string) => {
    if (key === 'checkbox') return; // 체크박스는 비활성화 불가
    const updated = { ...columnVisibility, [key]: !columnVisibility[key] };
    updateConfig(columnOrder, updated);
  };
  ```
- [ ] **Step 3: 커밋 수행**
  ```bash
  git commit -am "feat: add columns state and localStorage sync logic"
  ```

---

### Task 3: HTML5 드래그 앤 드롭(D&D) 핸들러 구현
**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/page.tsx`

- [ ] **Step 1: D&D 핸들러 함수 삽입**
  헤더의 `draggable={true}`에 매핑할 이벤트 함수들을 작성합니다.
  
  ```typescript
  const handleDragStart = (e: React.DragEvent, colKey: string) => {
    if (colKey === 'checkbox') {
      e.preventDefault();
      return;
    }
    setDraggedColKey(colKey);
    e.dataTransfer.effectAllowed = 'move';
  };
  
  const handleDragOver = (e: React.DragEvent, targetColKey: string) => {
    e.preventDefault();
    if (targetColKey === 'checkbox' || targetColKey === draggedColKey) return;
    
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const relX = e.clientX - rect.left;
    const isLeft = relX < rect.width / 2;
    
    setDragOverColKey(targetColKey);
    setDragDirection(isLeft ? 'left' : 'right');
  };
  
  const handleDrop = (e: React.DragEvent, targetColKey: string) => {
    e.preventDefault();
    if (!draggedColKey || targetColKey === 'checkbox' || targetColKey === draggedColKey) return;
  
    const currentOrder = [...columnOrder];
    const dragIdx = currentOrder.indexOf(draggedColKey);
    const targetIdx = currentOrder.indexOf(targetColKey);
  
    if (dragIdx > -1 && targetIdx > -1) {
      currentOrder.splice(dragIdx, 1);
      let newIdx = currentOrder.indexOf(targetColKey);
      if (dragDirection === 'right') {
        newIdx += 1;
      }
      currentOrder.splice(newIdx, 0, draggedColKey);
      updateConfig(currentOrder, columnVisibility);
    }
  
    setDraggedColKey(null);
    setDragOverColKey(null);
    setDragDirection(null);
  };
  
  const handleDragEnd = () => {
    setDraggedColKey(null);
    setDragOverColKey(null);
    setDragDirection(null);
  };
  ```
- [ ] **Step 2: 빌드 확인 및 커밋**
  ```bash
  git commit -am "feat: add drag-and-drop column reordering event handlers"
  ```

---

### Task 4: 동적 렌더링을 적용한 테이블 구조 개편
**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/page.tsx`

- [ ] **Step 1: `<thead>` 리팩토링**
  기존의 고정형 `<thead>`를 `columnOrder` 및 `columnVisibility` 기준의 동적인 루프로 변경합니다.
  
  ```tsx
  {/* 기존 thead 대체 */}
  <thead>
    <tr>
      {columnOrder.map((colKey) => {
        if (!columnVisibility[colKey]) return null;
        
        const isCheckbox = colKey === 'checkbox';
        const label = COLUMNS_REGISTRY[colKey] || '';
        
        let headerClass = '';
        if (!isCheckbox) {
          headerClass = styles.thDraggable;
          if (draggedColKey === colKey) {
            headerClass += ` ${styles.thDragging}`;
          }
          if (dragOverColKey === colKey) {
            headerClass += ` ${dragDirection === 'left' ? styles.dragIndicatorLeft : styles.dragIndicatorRight}`;
          }
        } else {
          headerClass = styles.checkboxCol;
        }
  
        return (
          <th
            key={colKey}
            className={headerClass}
            draggable={!isCheckbox}
            onDragStart={(e) => handleDragStart(e, colKey)}
            onDragOver={(e) => handleDragOver(e, colKey)}
            onDrop={(e) => handleDrop(e, colKey)}
            onDragEnd={handleDragEnd}
          >
            {isCheckbox ? (
              <input 
                type="checkbox" 
                checked={isAllSelected}
                onChange={handleSelectAll}
                className={styles.checkbox}
              />
            ) : (
              label
            )}
          </th>
        );
      })}
    </tr>
  </thead>
  ```

- [ ] **Step 2: `<tbody>` 내 테이블 행(`<tr>`) 리팩토링**
  기존의 개별 하드코딩된 `<td>` 나열 구조를 `columnOrder.map` 내에서 각 필드 키별 `switch-case`로 깔끔하게 렌더링되도록 개편합니다. 17개 속성 전체에 대해 완벽히 개별 렌더링 로직을 처리해 플레이스홀더를 없앱니다.
  
  ```tsx
  {/* 기존 tbody 내 tr 매핑 내부 리팩토링 */}
  {products.map((p) => {
    const naverMapping = p.platform_mappings.find((m) => m.platform_name === 'naver');
    const coupangMapping = p.platform_mappings.find((m) => m.platform_name === 'coupang');
    const priceChanged = p.platform_mappings.some((m) => m.price_changed);
    const stockChanged = p.platform_mappings.some((m) => m.stock_changed);
  
    return (
      <tr key={p.id}>
        {columnOrder.map((colKey) => {
          if (!columnVisibility[colKey]) return null;
  
          switch (colKey) {
            case 'checkbox':
              return (
                <td key={colKey} className={styles.checkboxCol}>
                  <input 
                    type="checkbox"
                    checked={selectedIds.has(p.id)}
                    onChange={(e) => handleSelectOne(p.id, e.target.checked)}
                    className={styles.checkbox}
                  />
                </td>
              );
            case 'refined_name':
              return (
                <td key={colKey}>
                  <div className={styles.nameWrapper}>
                    <span className={styles.refName}>
                      {p.refined_name ? p.refined_name : <span className={styles.refNameEmpty}>가공 전</span>}
                      {priceChanged && <span className={styles.changeBadgeOrange}>가격 변동</span>}
                      {stockChanged && <span className={styles.changeBadgeRed}>품절 변동</span>}
                    </span>
                    <span className={styles.origName}>원본: {p.original_name}</span>
                  </div>
                </td>
              );
            case 'original_name':
              return (
                <td key={colKey}>
                  <div className={styles.origName} style={{ maxWidth: '300px' }}>
                    {p.original_name}
                  </div>
                </td>
              );
            case 'keywords':
              return (
                <td key={colKey}>
                  <div className={styles.keywordWrapper}>
                    {p.keywords && p.keywords.length > 0 ? (
                      p.keywords.slice(0, 5).map((kw, i) => (
                        <span key={i} className={styles.keywordBadge}>{kw}</span>
                      ))
                    ) : (
                      <span className={styles.emptyInline}>없음</span>
                    )}
                    {p.keywords && p.keywords.length > 5 && (
                      <span className={styles.moreKeywords}>
                        +{p.keywords.length - 5}
                      </span>
                    )}
                  </div>
                </td>
              );
            case 'option_variants':
              return (
                <td key={colKey}>
                  {p.option_variants && p.option_variants.length > 0 ? (
                    <details className={styles.optionDetails}>
                      <summary className={styles.optionSummary}>
                        <span className={styles.optionCount}>옵션 {p.option_variants.length}개</span>
                        <span className={styles.optionPreview}>
                          {p.option_variants[0].name} · {formatPrice(p.option_variants[0].price_wholesale)}
                        </span>
                      </summary>
                      <ul className={styles.optionTree}>
                        {p.option_variants.map((opt, index) => (
                          <li key={`${opt.name}-${index}`} className={styles.optionItem}>
                            <span className={styles.optionName}>{opt.name}</span>
                            <span className={styles.optionPrice}>{formatPrice(opt.price_wholesale)}</span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : p.option_values_raw ? (
                    <div className={styles.optionFallback}>{p.option_values_raw}</div>
                  ) : (
                    <span className={styles.optionEmpty}>없음</span>
                  )}
                </td>
              );
            case 'platform_mappings':
              return (
                <td key={colKey}>
                  <div className={styles.categoryCell}>
                    <div className={styles.marketBadge}>
                      <span className={`${styles.marketLabel} ${styles.naver}`}>Naver</span>
                      {naverMapping && (naverMapping.category_path || naverMapping.category_id) ? (
                        <span className={styles.categoryPath} title={naverMapping.category_path || ''}>
                          {naverMapping.category_id || naverMapping.category_path}
                        </span>
                      ) : (
                        <span className={styles.categoryEmpty}>미매핑</span>
                      )}
                    </div>
                    <div className={styles.marketBadge}>
                      <span className={`${styles.marketLabel} ${styles.coupang}`}>Coupang</span>
                      {coupangMapping && coupangMapping.category_id ? (
                        <span className={styles.categoryPath}>
                          {coupangMapping.category_id}
                        </span>
                      ) : (
                        <span className={styles.categoryEmpty}>미매핑</span>
                      )}
                    </div>
                  </div>
                </td>
              );
            case 'status':
              return (
                <td key={colKey}>
                  <span className={`${styles.statusPill} ${styles[p.status]}`}>
                    {p.status === 'completed' && '완료'}
                    {p.status === 'processing' && '가공 중'}
                    {p.status === 'pending' && '대기'}
                    {p.status === 'failed' && '실패'}
                  </span>
                </td>
              );
            case 'created_at':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {new Date(p.created_at).toLocaleString('ko-KR', {
                    month: 'numeric',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </td>
              );
            case 'product_code':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {p.product_code || <span className={styles.emptyInline}>-</span>}
                </td>
              );
            case 'wholesale_product_id':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {p.wholesale_product_id || <span className={styles.emptyInline}>-</span>}
                </td>
              );
            case 'price_wholesale':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {formatPrice(p.price_wholesale)}
                </td>
              );
            case 'price_retail':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {formatPrice(p.price_retail)}
                </td>
              );
            case 'price_min_selling':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {formatPrice(p.price_min_selling)}
                </td>
              );
            case 'origin':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {p.origin || <span className={styles.emptyInline}>-</span>}
                </td>
              );
            case 'brand_name':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {p.brand_name || <span className={styles.emptyInline}>-</span>}
                </td>
              );
            case 'wholesale_status':
              return (
                <td key={colKey}>
                  {p.wholesale_status ? (
                    <span className={`${styles.statusPill} ${p.wholesale_status === '품절' ? styles.failed : styles.completed}`}>
                      {p.wholesale_status}
                    </span>
                  ) : (
                    <span className={styles.emptyInline}>-</span>
                  )}
                </td>
              );
            case 'wholesale_registered_at':
              return (
                <td key={colKey} className={styles.dateCell}>
                  {p.wholesale_registered_at || <span className={styles.emptyInline}>-</span>}
                </td>
              );
            default:
              return null;
          }
        })}
      </tr>
    );
  })}
  ```

- [ ] **Step 3: 커밋 수행**
  ```bash
  git commit -am "feat: refactor table header and body with dynamic column registry"
  ```

---

### Task 5: 팝오버 열 설정 UI 마운트
**Files:**
- Modify: `frontend/src/app/(ai-mall)/products/page.tsx`

- [ ] **Step 1: 필터바 우측 끝에 드롭다운 UI 구현**
  필터바 내부의 마지막 요소 쯤(혹은 검색필드들 직후)에 "열 설정" 컨트롤러 팝오버를 마운트합니다.
  
  ```tsx
  {/* filterBar 내부 맨 마지막에 배치 */}
  <div className={styles.columnSettingsContainer}>
    <PillButton
      variant="secondary"
      onClick={() => setShowSettings(!showSettings)}
      type="button"
      className={styles.actionButton}
    >
      ⚙️ 열 설정 ∨
    </PillButton>
    
    {showSettings && (
      <div className={styles.columnSettingsPopover}>
        <div className={styles.popoverHeader}>표시 필드 선택</div>
        <div className={styles.popoverList}>
          {DEFAULT_ORDER.map((key) => {
            if (key === 'checkbox') return null; // 체크박스는 항상 노출 고정
            return (
              <label key={key} className={styles.popoverItem}>
                <input
                  type="checkbox"
                  checked={!!columnVisibility[key]}
                  onChange={() => toggleColumnVisibility(key)}
                />
                <span>{COLUMNS_REGISTRY[key]}</span>
              </label>
            );
          })}
        </div>
      </div>
    )}
  </div>
  ```

- [ ] **Step 2: 팝오버 바깥 클릭 시 닫히는 UX 보강 (선택 사항이나 권장)**
  화면 아무 곳이나 누르면 팝오버가 부드럽게 닫히도록 `useEffect` 클릭 리스너를 결합해 마감 품질을 높입니다.
  
  ```typescript
  useEffect(() => {
    if (!showSettings) return;
    const handleOutsideClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(`.${styles.columnSettingsContainer}`)) {
        setShowSettings(false);
      }
    };
    document.addEventListener('click', handleOutsideClick);
    return () => document.removeEventListener('click', handleOutsideClick);
  }, [showSettings]);
  ```

- [ ] **Step 3: 최종 빌드 및 검증 후 최종 커밋**
  ```bash
  git commit -am "feat: mount dynamic column setting popover control UI"
  ```
