# Process Table AI Columns Misalignment (2026-05-22)

## Summary
상품 가공 탭의 표에서 `가공된 상품명`, `키워드` 헤더를 추가한 뒤, 실제 행 셀이 추가되지 않아 열 정렬이 깨졌고 `상태`, `가공상태`가 비어 보이는 문제를 수정했다.

## Symptoms
- `가공된 상품명`과 `키워드`가 보이지 않거나 기대 위치에 보이지 않음
- 마지막 `상태`, `가공상태`가 빈 것처럼 보임
- 일부 열 데이터가 오른쪽으로 밀려 보임

## Root Cause
- 테이블 헤더는 11열로 확장되었지만, tbody 행 렌더링은 기존 9열 구조를 유지함
- 컬럼 수 불일치로 인해 셀-헤더 매핑이 무너짐

## Fix
- `frontend/src/app/(ai-mall)/process/page.tsx`
  - `Product` 타입에 `keywords` 반영
  - 본문 행에 `가공된 상품명`, `키워드` 셀 추가
  - `가공상태`를 한글 라벨(`대기/가공 중/완료/실패`)로 변환해 표시
  - `상태`(도매 상태) 공백 시 `미정` 표기
- `frontend/src/app/(ai-mall)/process/process.module.css`
  - AI 가공 결과 전용 시각 스타일 추가
  - `AI 정제` 라벨, 그라디언트 카드, 키워드 pill cloud 적용

## Why This Works
- 헤더/행 열 수를 일치시켜 셀 매핑을 정상화
- completed 상태에서만 AI 가공 결과를 강조 노출해 데이터 의미와 UI 의도를 맞춤

## Validation Checklist
- [ ] 상품 가공 탭 진입 후 표 헤더가 다음 순서로 보이는지 확인
  - 상품명 / 가공된 상품명 / 키워드 / ... / 상태 / 가공상태
- [ ] completed 상품에서만 가공된 상품명/키워드가 표시되는지 확인
- [ ] pending/processing/failed 상품에서 AI 결과는 `가공 전` 또는 `-`로 표시되는지 확인
- [ ] `상태`와 `가공상태`가 비어 보이지 않는지 확인

## Commit
- `ca2b170` fix(process): show refined name and keywords with AI-style result cells
