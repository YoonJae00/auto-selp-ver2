'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import PillButton from '@/components/UI/PillButton/PillButton';
import ChangeHistoryPanel from './ChangeHistoryPanel';
import styles from './upload.module.css';

interface WholesaleSite {
  id: string;
  name: string;
  homepage_url: string | null;
  column_mapping: Record<string, MappingValue> | null;
}

interface UploadResponse {
  file_id: string;
  filename: string;
  columns: string[];
  preview: any[];
}

interface UploadDraft {
  uploadData: UploadResponse;
  columnMapping: Record<string, MappingValue>;
}

interface MappingRule {
  source?: string | null;
  default?: string | null;
  pattern?: string | null;
  regex_group?: number | string;
  regex_all?: boolean;
  join_with?: string;
  value_map?: Record<string, string>;
}

type MappingValue = string | MappingRule;

interface MappingPreviewResponse {
  column_mapping: Record<string, MappingValue>;
  preview: Record<string, any>[];
  standard_example: Record<string, any>;
  warnings: Array<string | { row?: number; field?: string; message?: string }>;
  notes?: string | string[] | null;
}

interface AiMappingChange {
  fieldKey: string;
  before?: MappingValue;
  after?: MappingValue;
}

interface AiCorrectionResult {
  changes: AiMappingChange[];
  notes: string[];
}

const SYSTEM_FIELD_GROUPS = [
  {
    title: '필수 상품 필드',
    fields: [
      { key: 'wholesale_status', label: '판매 상태 (필수)', required: true, standardKey: 'wholesale_status', defaultFallbacks: ['상태', '품절상태', '품절여부', '판매상태'], helpText: '도매처에서 제공하는 현재 판매 가능 상태입니다.', format: '텍스트 상태값 또는 품절 여부', sample: '판매중 / 정상 / 품절 / 일시품절' },
      { key: 'wholesale_product_id', label: '도매처 상품 번호 (필수)', required: true, standardKey: 'wholesale_product_id', defaultFallbacks: ['제품번호', '제품id', '상품id'], helpText: '도매처 DB에서 상품을 고유하게 식별하는 번호입니다.', format: '숫자 또는 문자 ID', sample: '12345678 / WS-2026-001' },
      { key: 'product_code', label: '도매처 상품 코드 (필수)', required: true, standardKey: 'product_code', defaultFallbacks: ['상품코드', '도매코드', '자체상품코드', '코드'], helpText: '도매처가 관리하는 상품 코드 또는 자체 상품 코드입니다.', format: '문자, 숫자, 하이픈 조합', sample: 'A1009-BK / P-000348' },
      { key: 'original_name', label: '원본 상품명 (필수)', required: true, standardKey: 'original_name', defaultFallbacks: ['상품명', '원본상품명', '제품명'], helpText: '도매처 엑셀에 있는 원본 상품명입니다. 가공 전 기준 이름으로 저장됩니다.', format: '상품명 텍스트', sample: '여성 루즈핏 코튼 셔츠' },
      { key: 'origin', label: '원산지 (필수)', required: true, standardKey: 'origin', defaultFallbacks: ['원산지', '제조국', '제조국가'], helpText: '상품 제조 국가 또는 원산지입니다. 마켓 등록 시 필수로 쓰입니다.', format: '국가명 또는 국내 지역명', sample: '대한민국 / 중국 / 베트남' },
      { key: 'price_wholesale_raw', label: '기본 공급가 (필수)', required: true, standardKey: 'price_wholesale_raw', defaultFallbacks: ['공급가', '도매가', '공급가격', '도매가격', '가격'], helpText: '옵션이 없거나 기본 옵션에 적용되는 도매 공급가입니다.', format: '숫자, 콤마, 원 표시 허용', sample: '12900 / 12,900 / 12900원' },
      { key: 'image_list_1', label: '대표 이미지 (필수)', required: true, standardKey: 'image_list_1', defaultFallbacks: ['목록이미지1', '대표이미지', '상품이미지', '이미지'], helpText: '상품 목록과 대표 이미지로 사용할 첫 번째 이미지입니다.', format: '이미지 URL', sample: 'https://example.com/item-main.jpg' },
      { key: 'image_detail', label: '상세 설명 이미지 (필수)', required: true, standardKey: 'image_detail', defaultFallbacks: ['상세이미지', '상세설명이미지'], helpText: '상세페이지 본문에 들어갈 설명 이미지입니다.', format: '단일 URL 또는 여러 URL 목록', sample: 'https://example.com/detail-1.jpg, https://example.com/detail-2.jpg' }
    ]
  },
  {
    title: '선택 상품 필드',
    fields: [
      { key: 'price_retail', label: '권장 소비자가', required: false, standardKey: 'price_retail', defaultFallbacks: ['소비자가', '소매가', '소매가격'], helpText: '도매처가 제안하는 소비자가 또는 정가입니다.', format: '숫자, 콤마, 원 표시 허용', sample: '29900 / 29,900원' },
      { key: 'price_min_selling', label: '최소 판매가', required: false, standardKey: 'price_min_selling', defaultFallbacks: ['판매준수가', '최소판매가', '최저가'], helpText: '마켓에서 이 가격보다 낮게 팔지 않아야 하는 기준가입니다.', format: '숫자, 콤마, 원 표시 허용', sample: '19900 / 19,900원' },
      { key: 'image_list_2', label: '추가 이미지 2', required: false, standardKey: 'image_list_2', defaultFallbacks: ['목록이미지2'], helpText: '대표 이미지 외 추가 상품 이미지입니다.', format: '이미지 URL', sample: 'https://example.com/item-sub-2.jpg' },
      { key: 'image_list_3', label: '추가 이미지 3', required: false, standardKey: 'image_list_3', defaultFallbacks: ['목록이미지3'], helpText: '대표 이미지 외 추가 상품 이미지입니다.', format: '이미지 URL', sample: 'https://example.com/item-sub-3.jpg' },
      { key: 'image_list_4', label: '추가 이미지 4', required: false, standardKey: 'image_list_4', defaultFallbacks: ['목록이미지4'], helpText: '대표 이미지 외 추가 상품 이미지입니다.', format: '이미지 URL', sample: 'https://example.com/item-sub-4.jpg' },
      { key: 'image_list_5', label: '추가 이미지 5', required: false, standardKey: 'image_list_5', defaultFallbacks: ['목록이미지5'], helpText: '대표 이미지 외 추가 상품 이미지입니다.', format: '이미지 URL', sample: 'https://example.com/item-sub-5.jpg' },
      { key: 'wholesale_registered_at', label: '도매처 등록일', required: false, standardKey: 'wholesale_registered_at', defaultFallbacks: ['등록일', '상품등록일'], helpText: '도매처에 상품이 등록된 날짜입니다.', format: '날짜 텍스트. YYYY-MM-DD 권장', sample: '2026-06-02 / 2026.06.02' }
    ]
  },
  {
    title: '옵션 필드',
    fields: [
      {
        key: 'option_values_raw',
        label: '옵션 값 목록',
        required: false,
        standardKey: 'option_values_raw',
        defaultFallbacks: ['옵션값', '옵션', '선택사항', '옵션명'],
        helpText: '옵션이 있는 상품의 옵션명 또는 조합 옵션 목록입니다. 옵션이 없는 상품은 비워둘 수 있습니다.',
        format: '콤마(,)는 옵션 행 구분, 파이프(|)는 조합 속성 구분, 콜론(:)은 속성명과 값을 구분합니다.',
        sample: '색상:블랙|사이즈:M, 색상:블랙|사이즈:L',
        examples: [
          '단일 옵션: 블랙, 화이트, 그레이',
          '조합 옵션: 색상:블랙|사이즈:M, 색상:블랙|사이즈:L',
          '가격 포함: 색상:블랙|사이즈:M|공급가:12900',
          '옵션 없음: 컬럼을 선택하지 않거나 값을 비워둡니다.'
        ],
        note: '나중에 네이버/쿠팡 등록용 조합 옵션으로 변환하기 쉽도록 속성명은 색상, 사이즈처럼 일관되게 쓰는 것이 좋습니다.'
      },
      {
        key: 'option_image_urls_raw',
        label: '옵션별 이미지 URL',
        required: false,
        standardKey: 'option_image_urls_raw',
        defaultFallbacks: ['옵션이미지', '옵션 이미지', '옵션이미지url', '옵션이미지주소'],
        helpText: '옵션별 대표 이미지를 연결하는 URL 목록입니다. 옵션 이미지가 없으면 비워둘 수 있습니다.',
        format: '왼쪽 옵션명은 옵션 값 목록의 옵션명 또는 조합 옵션명과 최대한 동일하게 맞춥니다.',
        sample: '색상:블랙|사이즈:M=https://example.com/black-m.jpg',
        examples: [
          '단일 옵션 이미지: 블랙=https://example.com/black.jpg',
          '조합 옵션 이미지: 색상:블랙|사이즈:M=https://example.com/black-m.jpg',
          '여러 옵션 이미지: 블랙=https://example.com/black.jpg, 화이트=https://example.com/white.jpg',
          '이미지 없음: 컬럼을 선택하지 않거나 값을 비워둡니다.'
        ],
        note: '옵션명 매칭이 다르면 이미지가 해당 옵션에 붙지 않을 수 있습니다.'
      },
      {
        key: 'option_price_deltas_raw',
        label: '옵션 추가금 목록',
        required: false,
        standardKey: 'option_price_deltas_raw',
        defaultFallbacks: ['옵션추가금', '옵션가격', '추가금', '옵션별가격'],
        helpText: '옵션 순서에 맞춘 추가 공급가 목록입니다.',
        format: '옵션 값과 같은 순서의 숫자 목록',
        sample: '0, 1000, 2000'
      },
      {
        key: 'option_skus_raw',
        label: '옵션 SKU 목록',
        required: false,
        standardKey: 'option_skus_raw',
        defaultFallbacks: ['옵션sku', '옵션코드', '옵션상품코드'],
        helpText: '옵션별 재고 관리를 위한 고유 코드 목록입니다.',
        format: '옵션 값과 같은 순서의 코드 목록',
        sample: 'BLACK-M, BLACK-L, WHITE-M'
      }
    ]
  }
] as const;

type SystemField = (typeof SYSTEM_FIELD_GROUPS)[number]['fields'][number];
const SYSTEM_FIELDS = SYSTEM_FIELD_GROUPS.flatMap<SystemField>(group => group.fields);
const REQUIRED_MAPPING_FIELDS = SYSTEM_FIELDS.filter(field => field.required);

const normalizeHeader = (value: string) => value.trim().replace(/\s+/g, '').toLowerCase();

const findBestColumnMatch = (field: (typeof SYSTEM_FIELDS)[number], columns: string[]) => {
  const normalizedColumns = columns.map(col => ({ original: col, normalized: normalizeHeader(col) }));
  const normalizedFallbacks = field.defaultFallbacks.map(normalizeHeader);

  for (const fallback of normalizedFallbacks) {
    const exactMatch = normalizedColumns.find(col => col.normalized === fallback);
    if (exactMatch) return exactMatch.original;
  }

  for (const fallback of normalizedFallbacks) {
    const substringMatch = normalizedColumns.find(col => col.normalized.includes(fallback));
    if (substringMatch) return substringMatch.original;
  }
};

const mappingSource = (value?: MappingValue) => typeof value === 'string' ? value : value?.source || '';
const mappingDefault = (value?: MappingValue) => typeof value === 'string' ? '' : value?.default || '';
const isMappingConfigured = (value?: MappingValue) => Boolean(mappingSource(value).trim() || mappingDefault(value).trim());

const buildHeuristicMapping = (columns: string[]) => {
  const mapping: Record<string, MappingValue> = {};
  SYSTEM_FIELDS.forEach((field) => {
    const matched = findBestColumnMatch(field, columns);
    if (matched) mapping[field.key] = matched;
    else if (field.required && columns[0]) mapping[field.key] = columns[0];
  });
  return mapping;
};

const mappingRule = (value?: MappingValue) => value && typeof value !== 'string' ? value : null;

const hasMappingTransform = (value?: MappingValue) => {
  const rule = mappingRule(value);
  return Boolean(rule && (
    mappingDefault(rule).trim()
    || rule.pattern
    || rule.regex_all
    || rule.regex_group != null
    || rule.join_with
    || Object.keys(rule.value_map || {}).length
  ));
};

const normalizedMappingValue = (value?: MappingValue) => {
  const rule = mappingRule(value);
  return {
    source: mappingSource(value) || null,
    default: mappingDefault(value) || null,
    pattern: rule?.pattern || null,
    regex_group: rule?.regex_group ?? null,
    regex_all: Boolean(rule?.regex_all),
    join_with: rule?.join_with || null,
    value_map: Object.entries(rule?.value_map || {}).sort(([left], [right]) => left.localeCompare(right)),
  };
};

const diffMappings = (before: Record<string, MappingValue>, after: Record<string, MappingValue>): AiMappingChange[] => (
  SYSTEM_FIELDS.flatMap(field => (
    JSON.stringify(normalizedMappingValue(before[field.key])) === JSON.stringify(normalizedMappingValue(after[field.key]))
      ? []
      : [{ fieldKey: field.key, before: before[field.key], after: after[field.key] }]
  ))
);

const describeMappingValue = (value?: MappingValue) => {
  const rule = mappingRule(value);
  const source = mappingSource(value);
  const defaultValue = mappingDefault(value);
  const valueMap = Object.entries(rule?.value_map || {});
  const parts = [
    source ? `원본 컬럼 · ${source}` : '',
    defaultValue ? `${source ? '빈 값 기본값' : '고정값'} · ${defaultValue}` : '',
    valueMap.length ? `값 치환 · ${valueMap.slice(0, 3).map(([from, to]) => `${from}→${to}`).join(', ')}${valueMap.length > 3 ? ` 외 ${valueMap.length - 3}개` : ''}` : '',
    rule?.pattern ? '정규식 변환' : '',
    rule?.regex_all ? '여러 값 추출' : '',
    rule?.join_with ? `결합 문자 · ${rule.join_with}` : '',
  ].filter(Boolean);
  return parts.join(' / ') || '설정 없음';
};

const formatNotes = (notes?: string | string[] | null) => notes ? (Array.isArray(notes) ? notes : [notes]) : [];
const draftStorageKey = (siteId: string) => `auto-selp:wholesale-upload-draft:${siteId}`;

const readUploadDraft = (siteId: string): UploadDraft | null => {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(draftStorageKey(siteId)) || 'null');
    return parsed?.uploadData?.file_id
      && Array.isArray(parsed.uploadData.columns)
      && parsed.columnMapping
      && typeof parsed.columnMapping === 'object'
      ? parsed
      : null;
  } catch {
    return null;
  }
};

const removeUploadDraft = (siteId: string) => {
  try {
    sessionStorage.removeItem(draftStorageKey(siteId));
  } catch {
    // sessionStorage unavailable: in-memory editing still works
  }
};

const displayPreviewValue = (value: any) => {
  if (value == null || value === '') return '';
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const previewFieldValue = (row: Record<string, any> | undefined, field: SystemField) => {
  if (!row) return '';
  const imageIndex = field.key.startsWith('image_list_') ? Number(field.key.slice(-1)) - 1 : -1;
  if (imageIndex >= 0) return row.images_list?.[imageIndex];
  if (field.key === 'option_price_deltas_raw') return row.standard_options?.map((option: any) => option.option_price_delta).filter((value: any) => value != null);
  if (field.key === 'option_skus_raw') return row.standard_options?.map((option: any) => option.option_sku).filter(Boolean);
  if (field.key === 'option_image_urls_raw') return row.standard_options?.map((option: any) => option.option_main_image_url).filter(Boolean);
  return row[field.standardKey];
};

const displayWarning = (warning: MappingPreviewResponse['warnings'][number]) => {
  if (typeof warning === 'string') return warning;
  const fieldLabel = SYSTEM_FIELDS.find(field => field.key === warning.field)?.label.replace(' (필수)', '') || warning.field;
  const message = warning.message === 'Required value is blank.' ? '필수 값이 비어 있습니다.' : warning.message;
  return [warning.row ? `${warning.row}행` : '', fieldLabel, message].filter(Boolean).join(' · ') || '매핑 결과를 확인해 주세요.';
};

// AI Mapping Studio panel — shared by the main upload flow and the edit-mapping modal.
function MappingStudioPanel({ instruction, onInstructionChange, onSubmit, isCorrecting, isValidating, result }: {
  instruction: string;
  onInstructionChange: (value: string) => void;
  onSubmit: () => void;
  isCorrecting: boolean;
  isValidating: boolean;
  result: AiCorrectionResult | null;
}) {
  return (
    <section className={styles.correctionPanel} aria-labelledby="ai-mapping-studio-title" aria-busy={isCorrecting}>
      <div className={styles.studioMain}>
        <div className={styles.studioHeading}>
          <span className={styles.studioBadge}><i aria-hidden="true" /> AI Mapping Studio</span>
          <h3 id="ai-mapping-studio-title">원하는 결과를 말로 알려주세요</h3>
          <p>AI는 한 번만 규칙을 고치고, 이후 모든 상품에는 같은 규칙을 적용합니다.</p>
        </div>
        <div className={styles.studioComposer}>
          <textarea
            className={styles.instructionInput}
            value={instruction}
            onChange={(event) => onInstructionChange(event.target.value)}
            placeholder="예: 원산지는 모두 상세정보 참조로, 판매 상태는 값이 없으면 판매중으로 바꿔줘"
            aria-label="AI 매핑 수정 요청"
            disabled={isCorrecting}
            rows={3}
          />
          <div className={styles.studioComposerFooter}>
            <span aria-live="polite">{instruction.trim() ? '요청을 보낼 준비가 됐습니다.' : '자연어로 바꿀 규칙을 입력하세요.'}</span>
            <PillButton
              variant="primary"
              className={styles.studioButton}
              onClick={onSubmit}
              disabled={isCorrecting || isValidating || !instruction.trim()}
              type="button"
            >
              {isCorrecting ? '수정 중...' : <>AI로 수정 <span aria-hidden="true">↗</span></>}
            </PillButton>
          </div>
        </div>
      </div>

      {result && (
        <div className={styles.aiCorrectionResult} aria-live="polite">
          <div className={styles.resultHeader}>
            <span>AI 수정 결과</span>
            <strong>{result.changes.length > 0 ? `${result.changes.length}개 규칙 변경` : '변경된 규칙 없음'}</strong>
          </div>
          {result.changes.length > 0 ? (
            <div className={styles.resultChanges}>
              {result.changes.map(change => (
                <div key={change.fieldKey} className={styles.resultChangeRow}>
                  <strong>{SYSTEM_FIELDS.find(field => field.key === change.fieldKey)?.label.replace(' (필수)', '') || change.fieldKey}</strong>
                  <div>
                    <span className={styles.beforeRule}>{describeMappingValue(change.before)}</span>
                    <span className={styles.changeArrow} aria-hidden="true">→</span>
                    <span className={styles.afterRule}>{describeMappingValue(change.after)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.noChanges}>현재 규칙이 이미 요청 내용과 일치합니다.</p>
          )}
          {result.notes.length > 0 && (
            <div className={styles.resultNotes}>
              <span>AI 설명</span>
              <p>{result.notes.join(' · ')}</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// 표준 형식 매핑 미리보기 — shared by the main upload flow and the edit-mapping modal.
function StandardPreviewPanel({ result, isValidated }: { result: MappingPreviewResponse; isValidated: boolean }) {
  return (
    <div className={styles.standardPreview}>
      <div className={styles.standardPreviewHeader}>
        <div>
          <h3>표준 형식 매핑 미리보기</h3>
          <p>형식 예시와 변환된 상품 최대 5개를 비교해 주세요.</p>
        </div>
        {!isValidated && <span className={styles.previewNotice}>현재 규칙은 검증 전입니다</span>}
      </div>
      {result.warnings?.length > 0 && (
        <div className={styles.warningList}>
          <strong>확인 필요</strong>
          <ul>
            {result.warnings.map((warning, index) => (
              <li key={index}>{displayWarning(warning)}</li>
            ))}
          </ul>
        </div>
      )}
      {result.notes && (
        <p className={styles.mappingNotes}>
          {Array.isArray(result.notes) ? result.notes.join(' · ') : result.notes}
        </p>
      )}
      <div className={styles.previewTableContainer}>
        <table className={styles.previewTable}>
          <thead>
            <tr>
              <th className={styles.rowNumber}>구분</th>
              {SYSTEM_FIELDS.map((field) => <th key={field.key}>{field.label.replace(' (필수)', '')}</th>)}
            </tr>
          </thead>
          <tbody>
            {[result.standard_example, ...result.preview.slice(0, 5)].map((row, rowIndex) => (
              <tr key={rowIndex} className={rowIndex === 0 ? styles.examplePreviewRow : ''}>
                <td className={styles.rowNumber}>{rowIndex === 0 ? '형식 예시' : `상품 ${rowIndex}`}</td>
                {SYSTEM_FIELDS.map((field) => {
                  const value = displayPreviewValue(previewFieldValue(row, field));
                  const isMissing = field.required && rowIndex > 0 && !value;
                  return (
                    <td
                      key={field.key}
                      className={isMissing ? styles.missingValue : ''}
                      title={isMissing ? `${field.label}: 필수 값 없음` : value}
                    >
                      {isMissing ? '필수 값 없음' : value || '-'}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const lastUploadKey = (siteId: string) => `auto-selp:last-upload:${siteId}`;

export default function UploadPage() {
  const [wholesaleSites, setWholesaleSites] = useState<WholesaleSite[]>([]);
  const [activeSite, setActiveSite] = useState<WholesaleSite | null>(null);
  
  // Modals & Forms
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newUrl, setNewUrl] = useState('');
  
  // File Uploading & Mapping States
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, MappingValue>>({});
  const [mappingResult, setMappingResult] = useState<MappingPreviewResponse | null>(null);
  const [mappingInstruction, setMappingInstruction] = useState('');
  const [mappingError, setMappingError] = useState<string | null>(null);
  const [initialMappingNotes, setInitialMappingNotes] = useState<string[]>([]);
  const [aiCorrectionResult, setAiCorrectionResult] = useState<AiCorrectionResult | null>(null);
  const [draftSiteId, setDraftSiteId] = useState<string | null>(null);
  const [draftMappingCounts, setDraftMappingCounts] = useState<Record<string, number>>({});
  const [isMappingValidated, setIsMappingValidated] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isCorrecting, setIsCorrecting] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(true); // Added for accordion toggle
  const [isStudioOpen, setIsStudioOpen] = useState(true); // collapse mapping studio for auto-validated mapped suppliers
  const [activeTab, setActiveTab] = useState<'upload' | 'history'>('upload');
  const [savedRun, setSavedRun] = useState(false); // show 업로드 이력 link after a successful save

  // Edit-mapping-without-file modal
  const [editMappingSite, setEditMappingSite] = useState<WholesaleSite | null>(null);
  const [editMapping, setEditMapping] = useState<Record<string, MappingValue>>({});
  const [editMappingError, setEditMappingError] = useState<string | null>(null);
  const [editMappingSaving, setEditMappingSaving] = useState(false);
  const [editLastUpload, setEditLastUpload] = useState<UploadResponse | null>(null); // saved file_id/columns for AI 수정·미리보기
  const [editInstruction, setEditInstruction] = useState('');
  const [editCorrectionResult, setEditCorrectionResult] = useState<AiCorrectionResult | null>(null);
  const [editMappingResult, setEditMappingResult] = useState<MappingPreviewResponse | null>(null);
  const [editIsCorrecting, setEditIsCorrecting] = useState(false);
  const [editIsValidating, setEditIsValidating] = useState(false);
  const [editIsValidated, setEditIsValidated] = useState(false);
  
  // Feedback
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const missingRequiredFields = REQUIRED_MAPPING_FIELDS.filter(field => !isMappingConfigured(columnMapping[field.key]));
  const configuredMappingCount = SYSTEM_FIELDS.filter(field => isMappingConfigured(columnMapping[field.key])).length;
  const recentlyChangedFieldKeys = new Set(aiCorrectionResult?.changes.map(change => change.fieldKey) || []);
  const hadSavedMapping = Object.values(activeSite?.column_mapping || {}).some(isMappingConfigured);

  // Fetch Wholesale Sites
  const fetchSites = useCallback(async () => {
    try {
      const data = await api.get<WholesaleSite[]>('/api/processor/wholesale-sites');
      setWholesaleSites(data);
      setDraftMappingCounts(Object.fromEntries(data.flatMap((site) => {
        const draft = readUploadDraft(site.id);
        return draft ? [[site.id, Object.values(draft.columnMapping).filter(isMappingConfigured).length]] : [];
      })));
      if (data.length > 0 && !activeSite) {
        setActiveSite(data[0]);
      }
    } catch (err: any) {
      setError('도매처 목록을 불러오지 못했습니다.');
    }
  }, [activeSite]);

  useEffect(() => {
    fetchSites();
  }, [fetchSites]);

  // Core mapping validation shared by 매핑 검증, upload auto-validate, and draft restore.
  // Sets columnMapping/mappingResult/isMappingValidated/mappingError; returns success. Throws on network error.
  const validateMapping = useCallback(async (fileId: string, mapping: Record<string, MappingValue>): Promise<boolean> => {
    if (!activeSite) return false;
    const missing = REQUIRED_MAPPING_FIELDS.filter(field => !isMappingConfigured(mapping[field.key]));
    if (missing.length > 0) {
      setMappingError(`필수 매핑 ${missing.length}개를 연결하거나 고정값을 지정해 주세요.`);
      setIsMappingValidated(false);
      return false;
    }
    const result = await api.post<MappingPreviewResponse>(
      `/api/processor/wholesale-sites/${activeSite.id}/mapping-preview`,
      { file_id: fileId, column_mapping: mapping },
    );
    setColumnMapping(result.column_mapping);
    setMappingResult(result);
    const invalid = REQUIRED_MAPPING_FIELDS.filter(field => !isMappingConfigured(result.column_mapping[field.key]));
    setIsMappingValidated(invalid.length === 0);
    if (invalid.length > 0) {
      setMappingError(`검증 결과 필수 매핑 ${invalid.length}개가 유효하지 않습니다. 컬럼 또는 고정값을 다시 확인해 주세요.`);
      return false;
    }
    setMappingError(null);
    return true;
  }, [activeSite]);

  useEffect(() => {
    const siteId = activeSite?.id || null;
    if (draftSiteId === siteId) return;

    const draft = siteId ? readUploadDraft(siteId) : null;
    setUploadData(draft?.uploadData || null);
    setColumnMapping(draft?.columnMapping || activeSite?.column_mapping || {});
    setMappingResult(null);
    setMappingInstruction('');
    setMappingError(null);
    setInitialMappingNotes([]);
    setAiCorrectionResult(null);
    setIsMappingValidated(false);
    setIsStudioOpen(true);
    setSavedRun(false);
    setDraftSiteId(siteId);
    if (draft && siteId) {
      void (async () => {
        try {
          setIsStudioOpen(!(await validateMapping(draft.uploadData.file_id, draft.columnMapping)));
        } catch {
          setIsStudioOpen(true);
        }
      })();
    }
  }, [activeSite, draftSiteId, validateMapping]);

  useEffect(() => {
    if (!activeSite || draftSiteId !== activeSite.id || !uploadData) return;

    try {
      sessionStorage.setItem(draftStorageKey(activeSite.id), JSON.stringify({ uploadData, columnMapping }));
    } catch {
      // sessionStorage unavailable: in-memory editing still works
    }
    const count = Object.values(columnMapping).filter(isMappingConfigured).length;
    setDraftMappingCounts(current => current[activeSite.id] === count ? current : { ...current, [activeSite.id]: count });
  }, [activeSite, draftSiteId, uploadData, columnMapping]);

  // Create site
  const handleCreateSite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setError(null);
    try {
      const created = await api.post<WholesaleSite>('/api/processor/wholesale-sites', {
        name: newName,
        homepage_url: newUrl || null,
        column_mapping: {}
      });
      setWholesaleSites([created, ...wholesaleSites]);
      setActiveSite(created);
      setShowCreateModal(false);
      setNewName('');
      setNewUrl('');
      setSuccess('도매처가 추가되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err.message || '도매처 추가에 실패했습니다.');
    }
  };

  // Delete site
  const handleDeleteSite = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('정말 이 도매처를 삭제하시겠습니까? 관련 매핑 정보도 함께 삭제됩니다.')) return;
    setError(null);
    try {
      await api.delete(`/api/processor/wholesale-sites/${id}`);
      removeUploadDraft(id);
      setDraftMappingCounts(current => {
        const next = { ...current };
        delete next[id];
        return next;
      });
      const filtered = wholesaleSites.filter(s => s.id !== id);
      setWholesaleSites(filtered);
      if (activeSite?.id === id) {
        setActiveSite(filtered.length > 0 ? filtered[0] : null);
      }
      setSuccess('도매처가 삭제되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err.message || '도매처 삭제에 실패했습니다.');
    }
  };

  // File selection & drag-and-drop
  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadExcelFile(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadExcelFile(file);
  };

  const uploadExcelFile = async (file: File) => {
    if (!activeSite) {
      setError('먼저 도매처를 선택하거나 생성해 주세요.');
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    setError(null);
    setIsUploading(true);
    setUploadData(null);
    setMappingResult(null);
    setMappingError(null);
    setInitialMappingNotes([]);
    setAiCorrectionResult(null);
    setIsMappingValidated(false);
    setIsStudioOpen(true);
    setSavedRun(false);
    setSuccess(null);

    try {
      const data = await api.post<UploadResponse>('/api/processor/upload', formData);
      setUploadData(data);
      setDraftSiteId(activeSite.id);
      try {
        localStorage.setItem(lastUploadKey(activeSite.id), JSON.stringify({ file_id: data.file_id, filename: data.filename, columns: data.columns }));
      } catch {
        // localStorage unavailable: AI 수정/미리보기는 다음 세션에 비활성화될 뿐 업로드는 정상 동작
      }

      const savedMapping = activeSite.column_mapping || {};
      if (Object.values(savedMapping).some(isMappingConfigured)) {
        setColumnMapping(savedMapping);
        try {
          const ok = await validateMapping(data.file_id, savedMapping);
          setIsStudioOpen(!ok);
          if (ok) setSuccess('저장된 매핑으로 자동 검증까지 완료했습니다. 바로 업데이트를 실행하세요.');
        } catch (validateError: any) {
          setIsStudioOpen(true);
          setError(validateError.message || '저장된 매핑 자동 검증에 실패했습니다. 매핑을 확인해 주세요.');
        }
      } else {
        setIsSuggesting(true);
        try {
          const suggestion = await api.post<MappingPreviewResponse>(
            `/api/processor/wholesale-sites/${activeSite.id}/mapping-suggestion`,
            { file_id: data.file_id },
          );
          setColumnMapping(suggestion.column_mapping);
          setMappingResult(suggestion);
          setInitialMappingNotes(formatNotes(suggestion.notes));
          setSuccess('AI가 1차 매핑과 변환 규칙을 만들었습니다. 내용을 확인한 뒤 매핑을 검증해 주세요.');
        } catch (suggestionError: any) {
          setColumnMapping(buildHeuristicMapping(data.columns));
          setError(`AI 자동 매핑에 실패해 기본 컬럼 매핑을 적용했습니다. 직접 수정할 수 있습니다. (${suggestionError.message || '알 수 없는 오류'})`);
        } finally {
          setIsSuggesting(false);
        }
      }
    } catch (err: any) {
      setError(err.message || '엑셀 파일 해석에 실패했습니다.');
    } finally {
      setIsUploading(false);
    }
  };

  // Save Column Template mapping to WholesaleSite
  const handleSaveTemplate = async () => {
    if (!activeSite) return;
    const missing = REQUIRED_MAPPING_FIELDS.filter(field => !isMappingConfigured(columnMapping[field.key]));
    if (missing.length > 0) {
      setError(null);
      setMappingError(`필수 매핑 ${missing.length}개를 연결하거나 고정값을 지정해 주세요.`);
      return;
    }
    if (!isMappingValidated) {
      setError(null);
      setMappingError('템플릿을 저장하기 전에 현재 규칙을 매핑 검증해 주세요.');
      return;
    }
    setError(null);
    setMappingError(null);
    try {
      const updated = await api.put<WholesaleSite>(`/api/processor/wholesale-sites/${activeSite.id}`, {
        name: activeSite.name,
        homepage_url: activeSite.homepage_url,
        column_mapping: columnMapping
      });
      
      // Update local state list
      setWholesaleSites(wholesaleSites.map(s => s.id === activeSite.id ? updated : s));
      setActiveSite(updated);
      
      setSuccess('도매처 엑셀 템플릿 매핑이 저장되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err.message || '템플릿 저장 실패');
    }
  };

  const handleValidateMapping = async () => {
    if (!activeSite || !uploadData) return;
    setError(null);
    setMappingError(null);
    setSuccess(null);
    setIsValidating(true);
    try {
      if (await validateMapping(uploadData.file_id, columnMapping)) {
        setSuccess('매핑 검증이 완료되었습니다. 표준 형식 미리보기와 경고를 확인해 주세요.');
      }
    } catch (err: any) {
      setIsMappingValidated(false);
      setError(err.message || '매핑 검증에 실패했습니다.');
    } finally {
      setIsValidating(false);
    }
  };

  const handleAiCorrection = async () => {
    if (!activeSite || !uploadData || !mappingInstruction.trim()) return;
    const beforeMapping = columnMapping;
    setError(null);
    setMappingError(null);
    setSuccess(null);
    setIsCorrecting(true);
    setIsMappingValidated(false);
    try {
      const suggestion = await api.post<MappingPreviewResponse>(
        `/api/processor/wholesale-sites/${activeSite.id}/mapping-suggestion`,
        {
          file_id: uploadData.file_id,
          column_mapping: columnMapping,
          instruction: mappingInstruction.trim(),
        },
      );
      setColumnMapping(suggestion.column_mapping);
      setMappingResult(suggestion);
      setMappingInstruction('');
      setAiCorrectionResult({
        changes: diffMappings(beforeMapping, suggestion.column_mapping),
        notes: formatNotes(suggestion.notes),
      });
      setSuccess('AI가 요청대로 매핑 규칙을 수정했습니다. 다시 매핑 검증을 해 주세요.');
    } catch (err: any) {
      setError(err.message || 'AI 매핑 수정에 실패했습니다. 현재 매핑은 그대로 유지됩니다.');
    } finally {
      setIsCorrecting(false);
    }
  };

  // Store uploaded supplier products in DB without product processing.
  const handleSaveProductsToDb = async () => {
    if (!activeSite || !uploadData) return;
    const missing = REQUIRED_MAPPING_FIELDS.filter(field => !isMappingConfigured(columnMapping[field.key]));
    if (missing.length > 0) {
      setError(null);
      setMappingError(`필수 매핑 ${missing.length}개를 연결하거나 고정값을 지정해 주세요.`);
      return;
    }
    if (!isMappingValidated) {
      setError(null);
      setMappingError('상품을 저장하기 전에 현재 규칙을 매핑 검증해 주세요.');
      return;
    }
    
    setError(null);
    setMappingError(null);
    setIsProcessing(true);
    try {
      const res = await api.post<{ task_id: string | null; import_id: string; total: number; new_count: number; updated_count: number; unchanged_count: number; removed_count: number; reprocessed_count: number }>('/api/processor/process-db', {
        file_id: uploadData.file_id,
        column_mapping: columnMapping,
        wholesale_site_id: activeSite.id,
        llm_provider: 'gemini',
        kipris_enabled: true,
        start_processing: false
      });

      setSuccess(`신규 ${res.new_count}개, 변동 ${res.updated_count}개, 단종 ${res.removed_count}개, 변경 없음 ${res.unchanged_count}개입니다. AI 재가공 대상 ${res.total}개만 상품 가공으로 보냈고, 나머지 변동은 상품 관리에 바로 반영했습니다.`);
      setSavedRun(true);
      removeUploadDraft(activeSite.id);
      setDraftMappingCounts(current => {
        const next = { ...current };
        delete next[activeSite.id];
        return next;
      });
      // Clear file upload state
      setUploadData(null);
    } catch (err: any) {
      setError(err.message || '상품 DB 저장 중 오류가 발생했습니다.');
    } finally {
      setIsProcessing(false);
    }
  };

  // --- Edit mapping without re-uploading a file ---
  // Suggest source column names seen across every saved mapping (no file = no live column list).
  const sourceSuggestions = Array.from(new Set(
    wholesaleSites.flatMap(site => Object.values(site.column_mapping || {}).map(mappingSource).filter(Boolean))
  ));
  const editMissingFields = REQUIRED_MAPPING_FIELDS.filter(field => !isMappingConfigured(editMapping[field.key]));

  const openEditMapping = (site: WholesaleSite, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditMappingSite(site);
    setEditMapping(site.column_mapping || {});
    setEditMappingError(null);
    setEditInstruction('');
    setEditCorrectionResult(null);
    setEditMappingResult(null);
    setEditIsValidated(false);
    let lastUpload: UploadResponse | null = null;
    try {
      const parsed = JSON.parse(localStorage.getItem(lastUploadKey(site.id)) || 'null');
      if (parsed?.file_id && Array.isArray(parsed.columns)) lastUpload = { preview: [], ...parsed };
    } catch {
      lastUpload = null;
    }
    setEditLastUpload(lastUpload);
  };

  // Shared 404 handling: the sample file expired server-side, drop to text-only fallback.
  const handleEditSampleExpired = (siteId: string) => {
    try { localStorage.removeItem(lastUploadKey(siteId)); } catch { /* ignore */ }
    setEditLastUpload(null);
    setEditMappingResult(null);
    setEditIsValidated(false);
    setEditMappingError('샘플 파일이 만료되어 AI 수정/미리보기를 쓸 수 없습니다. 새 파일을 업로드하면 다시 활성화됩니다.');
  };

  const handleEditAiCorrection = async () => {
    if (!editMappingSite || !editLastUpload || !editInstruction.trim()) return;
    const before = editMapping;
    setEditMappingError(null);
    setEditIsCorrecting(true);
    setEditIsValidated(false);
    try {
      const suggestion = await api.post<MappingPreviewResponse>(
        `/api/processor/wholesale-sites/${editMappingSite.id}/mapping-suggestion`,
        { file_id: editLastUpload.file_id, column_mapping: editMapping, instruction: editInstruction.trim() },
      );
      setEditMapping(suggestion.column_mapping);
      setEditMappingResult(suggestion);
      setEditInstruction('');
      setEditCorrectionResult({
        changes: diffMappings(before, suggestion.column_mapping),
        notes: formatNotes(suggestion.notes),
      });
    } catch (err: any) {
      if (err?.status === 404) handleEditSampleExpired(editMappingSite.id);
      else setEditMappingError(err.message || 'AI 매핑 수정에 실패했습니다.');
    } finally {
      setEditIsCorrecting(false);
    }
  };

  // Manual field edits invalidate a prior preview validation.
  const editSetField = (key: string, source: string, defaultValue: string) => {
    setEditField(key, source, defaultValue);
    setEditIsValidated(false);
  };

  const handleEditValidate = async () => {
    if (!editMappingSite || !editLastUpload) return;
    setEditMappingError(null);
    setEditIsValidating(true);
    try {
      const result = await api.post<MappingPreviewResponse>(
        `/api/processor/wholesale-sites/${editMappingSite.id}/mapping-preview`,
        { file_id: editLastUpload.file_id, column_mapping: editMapping },
      );
      setEditMapping(result.column_mapping);
      setEditMappingResult(result);
      setEditIsValidated(REQUIRED_MAPPING_FIELDS.every(field => isMappingConfigured(result.column_mapping[field.key])));
    } catch (err: any) {
      if (err?.status === 404) handleEditSampleExpired(editMappingSite.id);
      else setEditMappingError(err.message || '매핑 검증에 실패했습니다.');
    } finally {
      setEditIsValidating(false);
    }
  };

  // Set source/default for one field, preserving any advanced rule (pattern/regex/join/value_map).
  const setEditField = (key: string, nextSource: string, nextDefault: string) => {
    setEditMapping(current => {
      const next = { ...current };
      const rule = mappingRule(current[key]);
      const hasAdvanced = Boolean(rule && (rule.pattern || rule.regex_all || rule.regex_group != null || rule.join_with || Object.keys(rule.value_map || {}).length));
      const src = nextSource.trim();
      const def = nextDefault.trim();
      if (!src && !def) {
        delete next[key];
      } else if (hasAdvanced) {
        next[key] = { ...rule, source: src || null, default: def || null };
      } else if (def) {
        next[key] = { source: src || null, default: def };
      } else {
        next[key] = src; // string stays string when no default/advanced rule
      }
      return next;
    });
  };

  const handleSaveEditMapping = async () => {
    if (!editMappingSite) return;
    if (editMissingFields.length > 0) {
      setEditMappingError(`필수 매핑 ${editMissingFields.length}개를 연결하거나 고정값을 지정해 주세요.`);
      return;
    }
    setEditMappingError(null);
    setEditMappingSaving(true);
    try {
      const updated = await api.put<WholesaleSite>(`/api/processor/wholesale-sites/${editMappingSite.id}`, {
        name: editMappingSite.name,
        homepage_url: editMappingSite.homepage_url,
        column_mapping: editMapping,
      });
      setWholesaleSites(list => list.map(s => s.id === updated.id ? updated : s));
      if (activeSite?.id === updated.id) setActiveSite(updated);
      setEditMappingSite(null);
      setSuccess('도매처 매핑이 저장되었습니다.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setEditMappingError(err.message || '매핑 저장에 실패했습니다.');
    } finally {
      setEditMappingSaving(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>도매처 상품 업로드</h1>
        <PillButton 
          variant="primary" 
          onClick={() => setShowCreateModal(true)}
          type="button"
        >
          ➕ 새 도매처 추가
        </PillButton>
      </div>

      <div className={styles.tabBar} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'upload'}
          className={`${styles.tab} ${activeTab === 'upload' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          상품 업로드
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'history'}
          className={`${styles.tab} ${activeTab === 'history' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('history')}
        >
          업로드 이력
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {success && <div className={styles.success}>{success}</div>}
      {savedRun && activeTab === 'upload' && (
        <button
          type="button"
          className={styles.historyLink}
          onClick={() => { setActiveTab('history'); setSavedRun(false); }}
        >
          📋 업로드 이력에서 변동 확인
        </button>
      )}

      {activeTab === 'history' ? (
        <ChangeHistoryPanel />
      ) : (
        <>
      {/* Grid of wholesale sites */}
      <div className={styles.sitesGrid}>
        {wholesaleSites.map((site) => {
          const isSelected = activeSite?.id === site.id;
          const mappedCount = Object.keys(site.column_mapping || {}).length;
          const draftMappedCount = draftMappingCounts[site.id];
          const hasDraft = draftMappedCount !== undefined;
          
          return (
            <div 
              key={site.id} 
              className={`${styles.siteCard} ${isSelected ? styles.activeCard : ''}`}
              onClick={() => setActiveSite(site)}
            >
              <div className={styles.siteInfo}>
                <h3>{site.name}</h3>
                <span className={styles.siteUrl}>
                  {site.homepage_url ? site.homepage_url : '웹 주소 정보 없음'}
                </span>
                <span className={`${styles.mappingBadge} ${mappedCount === 0 && !hasDraft ? styles.mappingBadgeEmpty : ''}`}>
                  {mappedCount > 0
                    ? `🔗 ${mappedCount}개 항목 매핑됨`
                    : hasDraft
                      ? `✏️ ${draftMappedCount}개 작성 중`
                      : '⚠️ 템플릿 미설정'}
                </span>
              </div>
              <div className={styles.cardActions}>
                <div className={styles.cardActionsLeft}>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    onClick={(e) => handleDeleteSite(site.id, e)}
                  >
                    삭제
                  </button>
                  {Object.values(site.column_mapping || {}).some(isMappingConfigured) && (
                    <button
                      type="button"
                      className={styles.editMappingBtn}
                      onClick={(e) => openEditMapping(site, e)}
                    >
                      매핑 수정
                    </button>
                  )}
                </div>
                {isSelected && (
                  <span style={{ fontSize: '12px', color: 'var(--primary)', fontWeight: 600 }}>선택됨</span>
                )}
              </div>
            </div>
          );
        })}
        {wholesaleSites.length === 0 && (
          <div style={{ gridColumn: '1 / -1', padding: '40px', textAlign: 'center', background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '20px' }}>
            등록된 도매처가 존재하지 않습니다. 우측 상단의 &quot;새 도매처 추가&quot; 버튼을 눌러 도매처를 생성하세요.
          </div>
        )}
      </div>

      {/* File Upload Section based on selected wholesale site */}
      {activeSite && (
        <div className={styles.uploadSection}>
          <div className={styles.sectionHeader}>
            <h2>{activeSite.name} - 상품 엑셀 업로드</h2>
            <p>도매처에서 받은 엑셀 상품 목록을 DB에 저장합니다. 실제 상품 가공은 상품 가공 화면에서 선택한 상품만 진행합니다.</p>
          </div>

          <div 
            className={`${styles.uploadArea} ${isDragging ? styles.dragging : ''}`}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleFileDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <span className={styles.uploadIcon}>📥</span>
            <h3>{isSuggesting ? 'AI가 매핑 규칙을 만드는 중...' : isUploading ? '업로드 해석 중...' : '엑셀 파일을 업로드해 주세요'}</h3>
            <p>클릭하거나 여기로 파일을 드래그합니다 (.xlsx, .xls)</p>
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }}
              accept=".xlsx,.xls"
              onChange={handleFileSelect}
              disabled={isUploading || isSuggesting}
            />
          </div>

          {(isUploading || isSuggesting) && (
            <div className={styles.mappingLoadingCard} role="status" aria-live="polite" aria-busy="true">
              <div className={styles.loadingSignal} aria-hidden="true"><span /></div>
              <div className={styles.loadingCopy}>
                <span className={styles.loadingEyebrow}>AI Mapping Engine</span>
                <strong>{isSuggesting ? '상품 양식을 분석해 매핑 규칙을 만들고 있습니다' : '엑셀 헤더와 상품 샘플을 읽고 있습니다'}</strong>
                <p>완료되면 검증 가능한 컬럼 매핑만 표시합니다.</p>
              </div>
              <div className={styles.loadingSkeleton} aria-hidden="true">
                <span /><span /><span />
              </div>
            </div>
          )}

          {/* Visual Column Mapper */}
          {uploadData && !isUploading && !isSuggesting && (
            <div className={styles.mappingWrapper}>
              {/* Excel Data Preview Section */}
              <div className={styles.previewWrapper}>
                <button 
                  type="button" 
                  className={styles.accordionHeader} 
                  onClick={() => setIsPreviewOpen(!isPreviewOpen)}
                >
                  <span className={styles.accordionTitle}>
                    📊 업로드 파일 데이터 미리보기 (상위 5개 행)
                  </span>
                  <span className={styles.accordionIcon}>
                    {isPreviewOpen ? '🔼 접기' : '🔽 펼치기'}
                  </span>
                </button>
                
                {isPreviewOpen && (
                  <div className={styles.previewTableContainer}>
                    <table className={styles.previewTable}>
                      <thead>
                        <tr>
                          <th className={styles.rowNumber}>No.</th>
                          {uploadData.columns.map((col, idx) => (
                            <th key={`${col}-${idx}`}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {uploadData.preview.map((row, idx) => (
                          <tr key={idx}>
                            <td className={styles.rowNumber}>{idx + 1}</td>
                            {uploadData.columns.map((col, colIdx) => (
                              <td key={`${col}-${colIdx}`} title={row[col] != null ? String(row[col]) : ''}>
                                {row[col] != null ? String(row[col]) : ''}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <button
                type="button"
                className={styles.studioToggle}
                onClick={() => setIsStudioOpen(open => !open)}
                aria-expanded={isStudioOpen}
              >
                ⚙️ 매핑 규칙 {isStudioOpen ? '접기' : '보기/수정'}
              </button>

              {isStudioOpen && (
                <>
              <div className={styles.mapperSectionHeader}>
                <div>
                  <span className={styles.mapperEyebrow}>Mapping Workspace</span>
                  <h2>컬럼 매핑</h2>
                  <p>엑셀 원본 컬럼과 고정값, AI 변환 규칙을 확인하고 필요하면 직접 수정하세요.</p>
                </div>
                <div className={styles.mappingStats} aria-label="매핑 현황">
                  <span><strong>{configuredMappingCount}</strong> / {SYSTEM_FIELDS.length} 매핑</span>
                  <span className={missingRequiredFields.length ? styles.missingStat : styles.completeStat}>
                    필수 누락 {missingRequiredFields.length}
                  </span>
                </div>
              </div>

              {initialMappingNotes.length > 0 && (
                <div className={styles.initialNotes}>
                  <strong>AI 1차 분석</strong>
                  <span>{initialMappingNotes.join(' · ')}</span>
                </div>
              )}

              {(missingRequiredFields.length > 0 || mappingError) && (
                <div className={styles.mappingInlineError} role="alert" aria-live="polite">
                  <div>
                    <strong>{mappingError || `필수 매핑 ${missingRequiredFields.length}개가 필요합니다.`}</strong>
                    <span>엑셀 컬럼을 선택하거나 AI가 만든 고정값을 확인해 주세요.</span>
                  </div>
                  {missingRequiredFields.length > 0 && (
                    <div className={styles.missingFieldChips}>
                      {missingRequiredFields.map(field => (
                        <span key={field.key}>{field.label.replace(' (필수)', '')}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {SYSTEM_FIELD_GROUPS.map((group) => (
                <div key={group.title} className={styles.mapperGroup}>
                  <h3 className={styles.mapperGroupTitle}>
                    <span>{group.title}</span>
                    <small>{group.fields.filter(field => isMappingConfigured(columnMapping[field.key])).length} / {group.fields.length}</small>
                  </h3>
                  <div className={styles.mapperGrid}>
                    {group.fields.map((field) => {
                      const value = columnMapping[field.key];
                      const source = mappingSource(value);
                      const defaultValue = mappingDefault(value);
                      const rule = mappingRule(value);
                      const valueMapEntries = Object.entries(rule?.value_map || {});
                      const isConfigured = isMappingConfigured(value);
                      const wasJustChanged = recentlyChangedFieldKeys.has(field.key);
                      return (
                        <div
                          key={field.key}
                          className={`${styles.mappingField} ${isConfigured ? styles.mappingFieldConfigured : ''} ${wasJustChanged ? styles.mappingFieldChanged : ''}`}
                        >
                          <div className={styles.mappingFieldHeader}>
                            <span className={styles.fieldLabel}>
                              {field.label}
                              <span className={styles.helpWrap}>
                                <button
                                  type="button"
                                  className={styles.helpTrigger}
                                  aria-label={`${field.label} 형식 도움말`}
                                >
                                  ?
                                </button>
                                <span
                                  className={`${styles.helpTooltip} ${'examples' in field ? styles.optionHelpTooltip : ''}`}
                                  role="tooltip"
                                >
                                  <strong>{field.helpText}</strong>
                                  <span>형식: {field.format}</span>
                                  <span>샘플: {field.sample}</span>
                                  {'examples' in field && (
                                    <>
                                      <span className={styles.exampleTitle}>옵션 예시</span>
                                      <span className={styles.exampleTable}>
                                        {field.examples.map((example) => (
                                          <span key={example} className={styles.exampleRow}>
                                            <span className={styles.exampleType}>{example.split(': ')[0]}</span>
                                            <code className={styles.exampleCode}>{example.split(': ').slice(1).join(': ')}</code>
                                          </span>
                                        ))}
                                      </span>
                                      <span className={styles.optionHelpNote}>{field.note}</span>
                                    </>
                                  )}
                                </span>
                              </span>
                            </span>
                            <span className={styles.fieldBadges}>
                              {wasJustChanged && <span className={styles.justChangedBadge}>방금 수정됨</span>}
                              {hasMappingTransform(value) && <span className={styles.aiRuleBadge}>AI 변환</span>}
                              <span className={isConfigured ? styles.configuredBadge : styles.unconfiguredBadge}>
                                {isConfigured ? '설정됨' : '미설정'}
                              </span>
                            </span>
                          </div>

                          <label className={styles.sourceControl} htmlFor={`mapping-${field.key}`}>
                            <span>엑셀 원본 컬럼</span>
                            <select
                              id={`mapping-${field.key}`}
                              className={styles.select}
                              value={source}
                              onChange={(event) => {
                                setColumnMapping({ ...columnMapping, [field.key]: event.target.value });
                                setIsMappingValidated(false);
                                setMappingError(null);
                                setSuccess(null);
                              }}
                            >
                              <option value="">-- 선택 안함 --</option>
                              {source && !uploadData.columns.includes(source) && (
                                <option value={source}>⚠ {source} (파일에 없음)</option>
                              )}
                              {uploadData.columns.map(col => (
                                <option key={col} value={col}>{col}</option>
                              ))}
                            </select>
                          </label>

                          <div className={styles.ruleChips} aria-label={`${field.label} 현재 규칙`}>
                            {source && <span className={styles.sourceRuleChip}>원본 · {source}</span>}
                            {defaultValue && <span className={styles.defaultRuleChip}>{source ? '빈 값 기본값' : '고정값'} · {defaultValue}</span>}
                            {valueMapEntries.length > 0 && <span className={styles.valueMapRuleChip}>값 치환 · {valueMapEntries.length}개</span>}
                            {rule?.pattern && <span className={styles.transformRuleChip}>정규식 변환</span>}
                            {rule?.regex_all && <span className={styles.transformRuleChip}>여러 값 추출</span>}
                            {rule?.join_with && <span className={styles.transformRuleChip}>결합 · {rule.join_with}</span>}
                            {!source && !defaultValue && !hasMappingTransform(value) && <span className={styles.emptyRuleChip}>규칙 없음</span>}
                          </div>

                          {defaultValue && (
                            <div className={styles.fixedValueRule}>
                              <span>{source ? '값이 비었을 때' : '고정값'}</span>
                              <strong>{defaultValue}</strong>
                            </div>
                          )}

                          {valueMapEntries.length > 0 && (
                            <div className={styles.valueMapSummary}>
                              <span>값 치환</span>
                              <strong>{valueMapEntries.slice(0, 3).map(([from, to]) => `${from} → ${to}`).join(' · ')}{valueMapEntries.length > 3 ? ` · 외 ${valueMapEntries.length - 3}개` : ''}</strong>
                            </div>
                          )}

                          {rule?.pattern && (
                            <div className={styles.regexDetail}>
                              <span>정규식</span>
                              <code>{rule.pattern}</code>
                              {rule.regex_group != null && <small>그룹 {rule.regex_group}</small>}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              <MappingStudioPanel
                instruction={mappingInstruction}
                onInstructionChange={setMappingInstruction}
                onSubmit={handleAiCorrection}
                isCorrecting={isCorrecting}
                isValidating={isValidating}
                result={aiCorrectionResult}
              />

              <div className={styles.validationBar}>
                <span className={`${styles.validationState} ${isMappingValidated ? styles.validationComplete : styles.validationRequired}`}>
                  {isMappingValidated ? '✓ 검증 완료' : '↻ 재검증 필요'}
                </span>
                <PillButton
                  variant="primary"
                  onClick={handleValidateMapping}
                  disabled={isValidating || isSuggesting}
                  type="button"
                >
                  {isValidating ? '검증 중...' : '매핑 검증'}
                </PillButton>
              </div>
                </>
              )}

              {mappingResult && <StandardPreviewPanel result={mappingResult} isValidated={isMappingValidated} />}

              <div className={styles.mapperActions}>
                <PillButton 
                  variant="secondary"
                  onClick={handleSaveTemplate}
                  disabled={!isMappingValidated || isProcessing}
                  type="button"
                >
                  💾 도매처 템플릿 저장
                </PillButton>
                <PillButton 
                  variant="primary"
                  onClick={handleSaveProductsToDb}
                  disabled={isProcessing || !isMappingValidated}
                  type="button"
                >
                  {isProcessing
                    ? (hadSavedMapping ? '업데이트 중...' : 'DB 저장 중...')
                    : (hadSavedMapping ? '업데이트 실행' : 'DB에 상품 저장')}
                </PillButton>
              </div>
            </div>
          )}
        </div>
      )}
        </>
      )}

      {/* Edit saved mapping without re-uploading a file */}
      {editMappingSite && (
        <div className={styles.modalOverlay} onClick={() => setEditMappingSite(null)}>
          <div className={`${styles.modalContent} ${styles.editMappingModal}`} onClick={(e) => e.stopPropagation()}>
            <h2 className={styles.modalTitle}>{editMappingSite.name} - 매핑 수정</h2>
            <p className={styles.editMappingHint}>
              {editLastUpload
                ? `마지막 업로드 파일(${editLastUpload.filename})로 AI 수정과 매핑 미리보기를 쓸 수 있습니다. 저장한 매핑은 다음 엑셀 업로드 시 자동 검증됩니다.`
                : '파일 없이 저장된 매핑을 수정합니다. 새 파일을 업로드하면 AI 수정·미리보기가 활성화되고, 저장한 매핑은 다음 업로드 시 자동 검증됩니다.'}
            </p>

            {editMappingError && (
              <div className={styles.mappingInlineError} role="alert">
                <div><strong>{editMappingError}</strong></div>
              </div>
            )}

            <datalist id="edit-mapping-sources">
              {sourceSuggestions.map(col => <option key={col} value={col} />)}
            </datalist>

            <div className={styles.editMappingBody}>
              {SYSTEM_FIELD_GROUPS.map(group => (
                <div key={group.title} className={styles.editMappingGroup}>
                  <h3 className={styles.mapperGroupTitle}><span>{group.title}</span></h3>
                  {group.fields.map(field => {
                    const value = editMapping[field.key];
                    const source = mappingSource(value);
                    return (
                      <div key={field.key} className={styles.editMappingRow}>
                        <span className={styles.editMappingLabel}>
                          {field.label}
                          {hasMappingTransform(value) && (
                            <span className={styles.editMappingRuleNote} title={describeMappingValue(value)}>
                              고급 규칙 유지: {describeMappingValue(value)}
                            </span>
                          )}
                        </span>
                        <div className={styles.editMappingInputs}>
                          {editLastUpload ? (
                            <select
                              className={styles.select}
                              value={source}
                              onChange={(e) => editSetField(field.key, e.target.value, mappingDefault(value))}
                            >
                              <option value="">-- 선택 안함 --</option>
                              {source && !editLastUpload.columns.includes(source) && (
                                <option value={source}>⚠ {source} (파일에 없음)</option>
                              )}
                              {editLastUpload.columns.map(col => (
                                <option key={col} value={col}>{col}</option>
                              ))}
                            </select>
                          ) : (
                            <input
                              type="text"
                              className={styles.input}
                              list="edit-mapping-sources"
                              placeholder="원본 컬럼"
                              value={source}
                              onChange={(e) => editSetField(field.key, e.target.value, mappingDefault(value))}
                            />
                          )}
                          <input
                            type="text"
                            className={styles.input}
                            placeholder="기본값/고정값"
                            value={mappingDefault(value)}
                            onChange={(e) => editSetField(field.key, source, e.target.value)}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}

              {editLastUpload && (
                <>
                  <MappingStudioPanel
                    instruction={editInstruction}
                    onInstructionChange={setEditInstruction}
                    onSubmit={handleEditAiCorrection}
                    isCorrecting={editIsCorrecting}
                    isValidating={editIsValidating}
                    result={editCorrectionResult}
                  />

                  <div className={styles.validationBar}>
                    <span className={`${styles.validationState} ${editIsValidated ? styles.validationComplete : styles.validationRequired}`}>
                      {editIsValidated ? '✓ 검증 완료' : '↻ 미리보기로 확인'}
                    </span>
                    <PillButton
                      variant="primary"
                      onClick={handleEditValidate}
                      disabled={editIsValidating || editIsCorrecting}
                      type="button"
                    >
                      {editIsValidating ? '검증 중...' : '매핑 검증'}
                    </PillButton>
                  </div>

                  {editMappingResult && <StandardPreviewPanel result={editMappingResult} isValidated={editIsValidated} />}
                </>
              )}
            </div>

            <div className={styles.modalActions}>
              <PillButton variant="secondary" onClick={() => setEditMappingSite(null)} type="button">
                취소
              </PillButton>
              <PillButton
                variant="primary"
                onClick={handleSaveEditMapping}
                disabled={editMappingSaving || editMissingFields.length > 0}
                type="button"
              >
                {editMappingSaving ? '저장 중...' : '매핑 저장'}
              </PillButton>
            </div>
          </div>
        </div>
      )}

      {/* Create site interactive Modal */}
      {showCreateModal && (
        <div className={styles.modalOverlay} onClick={() => setShowCreateModal(false)}>
          <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <h2 className={styles.modalTitle}>새 도매처 생성</h2>
            <form onSubmit={handleCreateSite}>
              <div className={styles.formGroup}>
                <label>도매처 명칭</label>
                <input 
                  type="text" 
                  className={styles.input}
                  placeholder="예: 도매꾹, 온채널, 신상마켓"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  required
                />
              </div>
              <div className={styles.formGroup}>
                <label>도매처 웹사이트 (선택)</label>
                <input 
                  type="url" 
                  className={styles.input}
                  placeholder="예: https://domeggook.com"
                  value={newUrl}
                  onChange={(e) => setNewUrl(e.target.value)}
                />
              </div>
              <div className={styles.modalActions}>
                <PillButton 
                  variant="secondary" 
                  onClick={() => setShowCreateModal(false)}
                  type="button"
                >
                  취소
                </PillButton>
                <PillButton 
                  variant="primary" 
                  type="submit"
                >
                  생성
                </PillButton>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
