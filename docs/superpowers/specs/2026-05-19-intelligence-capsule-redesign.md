# Intelligence Capsule & 상품 가공 UX 재설계 요구사항

**작성일:** 2026-05-19  
**범위:** IntelligenceCapsule 전면 재설계 + Process 페이지 UX 개선

---

## 배경 및 문제 정의

- 상품 100~200개를 처리하는 장시간 백그라운드 작업에서, 기존 UI는 "작업 중.." 표시 외에 유의미한 정보 없음
- IntelligenceCapsule이 화면 상단 중앙에 위치해 콘텐츠를 가리고 존재감이 과도함
- 드롭다운 패널이 너무 좁아 작업 상세 정보를 표현하기 어려움
- 가공 시작 후 사용자가 다른 페이지로 이동할 수 없는 구조적 문제

---

## 목표

1. 사용자가 가공 작업을 걸어두고 **다른 페이지에서 자유롭게 작업** 가능
2. 캡슐 클릭 시 **LangGraph Trace 스타일의 트리 구조**로 상세 진행 현황 확인 가능
3. 완료된 상품도 소요시간과 단계별 결과 열람 가능
4. 캡슐이 작업 중일 때 **Apple Watch 스타일의 ambient 회전 glow** 효과로 존재감 표현

---

## 사용자 플로우

```
1. 상품 가공 페이지에서 가공 시작
   → "백그라운드로 전환됩니다" 안내 토스트 표시
   → 사용자는 다른 페이지로 자유롭게 이동 가능

2. 좌측 하단 캡슐 (항상 표시 - 작업 있을 때)
   → 작업 중: 회전하는 ambient glow 애니메이션
   → 완료: glow 사라지고 "완료" 상태 표시

3. 캡슐 클릭
   → 좌측 하단에서 위로 슬라이드하는 사이드 드로어 (width: 380px)
   → 작업 목록 표시: 파일명, 진행률 바, 상태 배지

4. 작업 항목 클릭
   → 드로어 내에서 트리 상세 뷰로 전환 (← 뒤로가기 버튼 포함)
   → 각 상품 행 표시: 완료/진행중/대기 상태 + 소요시간
   → 현재 처리 중 상품만 단계 자동 펼침
   → 완료된 상품도 클릭하면 단계 펼쳐볼 수 있음
```

---

## UI 상세 스펙

### 캡슐 (IntelligenceCapsule)

- **위치**: 좌측 하단 고정 (`position: fixed; bottom: 24px; left: calc(var(--sidebar-width) + 24px)`)
- **크기**: 높이 44px, 최소 너비 140px, 패딩 0 20px
- **비활성**: 반투명 글래스 (배경 `rgba(255,255,255,0.7)`, blur)
- **작업 중 (active)**: 캡슐 외곽에 conic-gradient 회전 glow
  - 색상: `#a78bfa → #60a5fa → #34d399 → #a78bfa` (보라/파랑/민트 순환)
  - 속도: 6초 1회전 (은은하고 부드럽게)
  - blur: 12px, opacity: 0.7
- **콘텐츠**: `⚡ 가공 중... (63%)` 또는 `✅ 가공 완료`

### 사이드 드로어

- **위치**: 좌측 하단에서 위로 슬라이드 (`bottom: 80px; left: calc(var(--sidebar-width) + 16px)`)
- **크기**: 너비 380px, 최대 높이 560px (스크롤)
- **헤더**: "Intelligence Tasks" 타이틀 + 완료 항목 지우기 버튼
- **애니메이션**: `translateY(20px) → translateY(0)` + opacity fade-in

### 트리 상세 뷰 (작업 클릭 후)

```
← 목록으로
📄 상품목록.xlsx
   ████████████░░░░  78%  진행 중

├── ✅ 무선이어폰 갤럭시버즈    2.1s
├── ✅ 애플 에어팟 프로         1.8s
│   (클릭 시 펼쳐짐)
│   ├── ✅ 상품명 정제   0.4s
│   ├── ✅ 키워드 생성   1.2s
│   └── ✅ 카테고리 매핑 0.2s
├── 🔄 나이키 에어포스         (shimmer 애니메이션)
│   ├── ✅ 상품명 정제   0.3s
│   ├── 🔄 키워드 생성   [반짝임...]
│   └── ⏳ 카테고리 매핑
├── ⏳ 소니 WH-1000XM5
└── ⏳ 삼성 버즈2 프로
```

- **완료 상품**: 소요시간 표시, 클릭 → 단계 접고 펼치기 (accordion)
- **진행 중 상품**: 자동 펼침, 현재 단계에 shimmer 애니메이션
- **대기 상품**: 흐리게 표시 (opacity: 0.4)

---

## 백엔드 변경 사항

### tasks.py - meta 구조 확장

```python
# 기존
meta = { 'percent': 63, 'current': 5, 'total': 8, 'stage': 'keywords', 'current_name': '나이키...' }

# 변경 후
meta = {
  'percent': 63,
  'current': 5,
  'total': 8,
  'stage': 'keywords',           # 현재 단계
  'current_name': '나이키...',   # 현재 상품명
  'current_stage_start': 1716..., # 현재 단계 시작 timestamp
  'completed_rows': [            # 완료된 상품 누적
    {
      'name': '무선이어폰',
      'total_ms': 2100,
      'stages': [
        { 'name': 'refining', 'ms': 400 },
        { 'name': 'keywords', 'ms': 1500 },
        { 'name': 'categorizing', 'ms': 200 }
      ]
    },
    ...
  ],
  'warnings': {}
}
```

---

## 프론트엔드 변경 사항

### taskStore.ts - Task 인터페이스 확장

```typescript
interface CompletedRowStage {
  name: string;
  ms: number;
}

interface CompletedRow {
  name: string;
  total_ms: number;
  stages: CompletedRowStage[];
}

interface Task {
  // 기존 필드 유지
  stage?: 'refining' | 'keywords' | 'categorizing' | 'completed_row';
  currentName?: string;
  completedRows?: CompletedRow[];  // 추가
}
```

### process/page.tsx - UX 변경

- 가공 시작 버튼 클릭 시: 토스트 메시지 "백그라운드에서 처리 중입니다. 다른 작업을 계속하세요." 표시 후 `/` 또는 현 위치 유지
- PROCESSING 단계 뷰 제거 또는 최소화 (캡슐로 위임)

---

## 성공 기준

- [ ] 가공 시작 후 다른 페이지 이동해도 캡슐이 진행 상황 표시
- [ ] 캡슐 active 상태에서 회전 glow 애니메이션 동작
- [ ] 드로어에서 트리 상세 뷰 진입/복귀 가능
- [ ] 완료된 상품 클릭 시 단계별 소요시간 표시
- [ ] 진행 중인 상품의 현재 단계에 shimmer 애니메이션 동작
