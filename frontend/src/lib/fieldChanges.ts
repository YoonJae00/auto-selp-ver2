// Shared field-change formatting for the source-change badge and 변동 내역 page.

export type FieldChanges =
  | Record<string, { old: string | number | null; new: string | number | null }>
  | null
  | undefined;

export interface ChangeInfo {
  change_type: 'new' | 'updated' | 'removed' | null;
  changed_fields: string[] | null;
  field_changes?: FieldChanges;
}

export const KOREAN_FIELD_LABELS: Record<string, string> = {
  wholesale_status: '품절상태',
  price_wholesale: '도매가',
  price_wholesale_raw: '도매가(원본)',
  price_retail: '소비자가',
  price_min_selling: '최소판매가',
  origin: '원산지',
  option_values_raw: '옵션',
  option_variants: '옵션 구성',
  standard_options: '표준 옵션',
  images_list: '목록 이미지',
  image_detail: '상세 이미지',
  original_name: '상품명',
  wholesale_product_id: '도매상품번호',
  wholesale_registered_at: '등록일',
};

// field_changes → display lines ("label: old → new", or "label: 변경됨" when both null).
export function fieldChangeLines(changes: FieldChanges): string[] {
  if (!changes) return [];
  return Object.entries(changes).map(([field, { old, new: next }]) => {
    const label = KOREAN_FIELD_LABELS[field] || field;
    return old === null && next === null ? `${label}: 변경됨` : `${label}: ${old} → ${next}`;
  });
}

// Tooltip for the source-change badge: old → new lines when available, else field-name list.
export function changeTooltip(change: ChangeInfo): string {
  if (change.change_type === 'new') return '새 도매처 상품';
  if (change.change_type === 'removed') return '도매처 목록에서 사라진 단종 상품';
  const lines = fieldChangeLines(change.field_changes);
  if (lines.length) return lines.join('\n');
  return change.changed_fields?.length ? `변경 항목: ${change.changed_fields.join(', ')}` : '변동';
}
