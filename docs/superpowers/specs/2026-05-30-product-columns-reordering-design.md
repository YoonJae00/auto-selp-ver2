# 설계 사양서: 상품 관리 열 노출 설정 및 드래그 순서 재정렬 (2026-05-30)

본 문서는 상품 관리 탭 테이블의 모든 속성(필드)을 자유롭게 확인하고, 헤더를 마우스 드래그 앤 드롭(Drag & Drop)하여 순서를 자유롭게 변경할 수 있도록 하는 기능의 세부 설계 사양을 정의합니다. 사용자가 정의한 열 설정과 순서는 브라우저의 `localStorage`에 즉시 동기화되어 페이지 새로고침 후에도 유지되도록 설계되었습니다.

---

## 1. 기능 개요

### 1.1 목표
상품 관리 테이블에서 다음 기능을 스토어 관리자에게 제공합니다:
- **모든 17개 상품 속성(필드)**을 테이블 열로 확인 가능하게 구성합니다.
- **열 설정(필드 선택) 드롭다운 팝오버**를 통해 개별 열의 노출 여부를 실시간으로 켜고 끌 수 있게 합니다.
- **헤더 마우스 드래그 앤 드롭**을 통해 열의 좌우 순서를 자유롭게 재정렬할 수 있게 합니다.
- 사용자의 열 순서 및 노출 상태를 **`localStorage`에 안전하게 보존**하여 다시 접속해도 그대로 유지되도록 합니다.

### 1.2 UX/UI 디자인 가이드라인 (Apple-inspired Style)
- **부드러운 반응형 피드백**: 체크박스를 해제하거나 열을 드롭하는 즉시 UI에 딜레이 없이 반영됩니다.
- **명확한 시각적 피드백**:
  - 드래그 시작 시, 드래그 중인 헤더 셀이 반투명(`opacity: 0.4`)해지며 마우스를 따라다니는 고스트 셀 효과를 줍니다.
  - 마우스가 다른 열 헤더 위로 지나갈 때(Hover), 드롭될 위치(좌측 혹은 우측 경계선)에 **애플 공식 시그니처 블루 색상(`var(--primary)` / Apple Blue)**의 수직 점선/두꺼운 라인 가이드를 노출합니다.
  - 마우스 커서가 드래그 가능한 헤더 위에 가면 `cursor: grab`, 드래그 시 `cursor: grabbing`으로 자연스럽게 변합니다.
- **고급스러운 드롭다운 팝오버**: 열 설정 버튼 클릭 시 노출되는 리스트는 뒷배경이 흐려지는 Glassmorphism 효과(`backdrop-filter: blur(20px)`)와 부드러운 그림자(Micro-shadow)를 적용해 프리미엄 디자인을 완성합니다.

---

## 2. 기술 아키텍처 및 상태 관리

### 2.1 로컬 저장소 스키마
`localStorage` 내 `autoselp_product_columns_config` 키로 설정 객체를 JSON 문자열 형태로 저장합니다.
```json
{
  "order": [
    "checkbox",
    "refined_name",
    "original_name",
    "keywords",
    "option_variants",
    "platform_mappings",
    "status",
    "created_at",
    "product_code",
    "wholesale_product_id",
    "price_wholesale",
    "price_retail",
    "price_min_selling",
    "origin",
    "brand_name",
    "wholesale_status",
    "wholesale_registered_at"
  ],
  "visibility": {
    "checkbox": true,
    "refined_name": true,
    "original_name": true,
    "keywords": true,
    "option_variants": true,
    "platform_mappings": true,
    "status": true,
    "created_at": true,
    "product_code": false,
    "wholesale_product_id": false,
    "price_wholesale": false,
    "price_retail": false,
    "price_min_selling": false,
    "origin": false,
    "brand_name": false,
    "wholesale_status": false,
    "wholesale_registered_at": false
  }
}
```

### 2.2 클라이언트 사이드 React 상태 정의
Next.js의 SSR 환경에서 `window`/`localStorage` 미존재로 인해 발생할 수 있는 Hydration Mismatch를 안전하게 예방하기 위해, 컴포넌트 마운트 이후(`useEffect`) 상태를 동기화하거나 안전한 지연 초기화(Lazy Initializer) 패턴을 활용합니다.

```typescript
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

const DEFAULT_VISIBILITY = {
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
```

---

## 3. 컴포넌트 및 테이블 레이아웃 구현 계획

### 3.1 전체 컬럼 레지스트리 정의
각 열 키에 매핑되는 한글 라벨 및 렌더링 세부 설정을 관리합니다.
```typescript
const COLUMNS_REGISTRY: Record<string, { label: string }> = {
  checkbox: { label: '' },
  refined_name: { label: '상품 명칭 (원래 상품명 / 정제상품명)' },
  keywords: { label: '정제 키워드' },
  option_variants: { label: '옵션' },
  platform_mappings: { label: '마켓 카테고리 매핑' },
  status: { label: '상태' },
  created_at: { label: '등록 시각' },
  product_code: { label: '상품 코드' },
  wholesale_product_id: { label: '도매처 상품 ID' },
  price_wholesale: { label: '도매가' },
  price_retail: { label: '소매가' },
  price_min_selling: { label: '최소 판매가' },
  origin: { label: '원산지' },
  brand_name: { label: '브랜드명' },
  wholesale_status: { label: '도매 상태' },
  wholesale_registered_at: { label: '도매 등록일' }
};
```

### 3.2 HTML5 드래그 앤 드롭 이벤트 핸들링 로직
테이블 헤더에 아래와 같이 React 표준 이벤트 바인딩 및 상태 업데이트 코드를 결합합니다.
* `draggedColKey: string | null`: 드래그 중인 열 키를 저장합니다.
* `dragOverColKey: string | null`: 드래그 중인 마우스가 올라가 있는 목표 열 키를 저장합니다.
* `dragDirection: 'left' | 'right' | null`: 마우스가 오버된 열 헤더의 절반 기준으로 어느 쪽에 인접했는지 판별합니다.

```typescript
const handleDragStart = (e: React.DragEvent, colKey: string) => {
  if (colKey === 'checkbox') {
    e.preventDefault(); // 체크박스 열은 순서를 변경할 수 없고 고정됨
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
    // 본래 인덱스에서 제거
    currentOrder.splice(dragIdx, 1);
    // 이동된 위치 계산 후 삽입
    let newIdx = currentOrder.indexOf(targetColKey);
    if (dragDirection === 'right') {
      newIdx += 1;
    }
    currentOrder.splice(newIdx, 0, draggedColKey);

    setColumnOrder(currentOrder);
    localStorage.setItem(
      'autoselp_product_columns_config',
      JSON.stringify({ order: currentOrder, visibility: columnVisibility })
    );
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

---

## 4. UI 레이아웃 및 스타일 사양

### 4.1 열 설정 팝오버
- 드롭다운 트리거 버튼을 필터 툴바 오른쪽 끝(또는 엑셀 내보내기 버튼 왼쪽)에 미려하게 디자인해 배치합니다.
- 클릭 시 상태 `showSettings`를 토글하여 팝오버 창을 띄웁니다.

```css
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
  max-height: 400px;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--hairline);
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
}
```

### 4.2 드래그 시각적 스타일
- 마우스 커서의 형태 조절과 실시간 드롭 라인 지시자를 스타일링합니다.

```css
.thDraggable {
  cursor: grab;
  user-select: none;
}
.thDraggable:active {
  cursor: grabbing;
}
.thDragging {
  opacity: 0.4;
}
.dragIndicatorLeft {
  border-left: 2.5px solid var(--primary) !important;
}
.dragIndicatorRight {
  border-right: 2.5px solid var(--primary) !important;
}
```
