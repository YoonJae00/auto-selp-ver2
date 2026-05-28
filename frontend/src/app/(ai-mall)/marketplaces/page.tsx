'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import styles from './marketplaces.module.css';

type MarketCode = 'smartstore' | 'coupang' | string;

interface DraftSummary {
  id: string;
  market_code: MarketCode;
  market_account_id: string;
  display_title: string | null;
  category_id: string | null;
  sale_price: number | null;
  primary_image_url: string | null;
  status: string;
  updated_at: string;
  validation_result?: { status?: string; errors?: Array<{ message: string }>; warnings?: Array<{ message: string }> };
}

interface DraftListResponse {
  items: DraftSummary[];
}

interface DraftDetail extends DraftSummary {
  source_snapshot?: any;
  generated_payload?: any;
  override_patch?: any;
  expected_profit?: number | null;
  expected_margin_rate?: number | null;
  cost_price?: number | null;
}

const MARKET_FILTERS = ['all', 'smartstore', 'coupang'];
const STATUS_FILTERS = ['all', 'needs_review', 'ready', 'submitting', 'submitted', 'failed', 'update_required'];

const formatMarket = (market: string) => (market === 'smartstore' ? 'Smart Store' : market === 'coupang' ? 'Coupang' : market);

export default function MarketplacesPage() {
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [draftDetail, setDraftDetail] = useState<DraftDetail | null>(null);
  const [marketFilter, setMarketFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [isLoading, setIsLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftForm, setDraftForm] = useState({
    title: '',
    salePrice: '',
    categoryId: '',
    origin: '',
    detailContent: '',
    imageUrls: '',
    optionsJson: '[]',
  });

  const loadDrafts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (marketFilter !== 'all') params.set('market_code', marketFilter);
      if (statusFilter !== 'all') params.set('status', statusFilter);
      const data = await api.get<DraftListResponse>(`/api/marketplace/drafts${params.toString() ? `?${params.toString()}` : ''}`);
      setDrafts(data.items);
      if (data.items.length > 0 && !selectedDraftId) {
        setSelectedDraftId(data.items[0].id);
      }
    } catch (err: any) {
      setError(err.message || '등록 초안 목록을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [marketFilter, statusFilter, selectedDraftId]);

  const loadDraftDetail = async (id: string) => {
    setIsDetailLoading(true);
    try {
      const detail = await api.get<DraftDetail>(`/api/marketplace/drafts/${id}`);
      setDraftDetail(detail);
      const payload = detail.override_patch || detail.generated_payload || {};
      setDraftForm({
        title: payload.title || detail.display_title || '',
        salePrice: String(payload.salePrice ?? detail.sale_price ?? ''),
        categoryId: payload.categoryId || detail.category_id || '',
        origin: payload.origin || detail.source_snapshot?.origin || '',
        detailContent: payload.detailContent || detail.source_snapshot?.images?.detail_content || '',
        imageUrls: Array.isArray(payload.images) ? payload.images.join('\n') : Array.isArray(detail.source_snapshot?.images?.list) ? detail.source_snapshot.images.list.join('\n') : '',
        optionsJson: JSON.stringify(payload.options || detail.source_snapshot?.options || [], null, 2),
      });
    } catch (err: any) {
      setError(err.message || '상세 초안을 불러오지 못했습니다.');
    } finally {
      setIsDetailLoading(false);
    }
  };

  useEffect(() => {
    loadDrafts();
  }, [loadDrafts]);

  useEffect(() => {
    if (selectedDraftId) {
      loadDraftDetail(selectedDraftId);
    } else {
      setDraftDetail(null);
    }
  }, [selectedDraftId]);

  const groupedSelection = useMemo(() => {
    const buckets = new Map<string, { market_account_id: string; draft_ids: string[] }>();
    drafts.forEach((draft) => {
      if (!selectedIds.has(draft.id)) return;
      const key = `${draft.market_code}:${draft.market_account_id}`;
      const current = buckets.get(key) || { market_account_id: draft.market_account_id, draft_ids: [] };
      current.draft_ids.push(draft.id);
      buckets.set(key, current);
    });
    return Array.from(buckets.values());
  }, [drafts, selectedIds]);

  const buildOverridePatch = () => {
    const parsedOptions = JSON.parse(draftForm.optionsJson || '[]');
    return {
      title: draftForm.title,
      salePrice: draftForm.salePrice ? Number(draftForm.salePrice) : null,
      categoryId: draftForm.categoryId || null,
      origin: draftForm.origin || null,
      detailContent: draftForm.detailContent || null,
      images: draftForm.imageUrls.split('\n').map((v) => v.trim()).filter(Boolean),
      options: parsedOptions,
    };
  };

  const handleSaveDraft = async (markReady = false) => {
    if (!draftDetail) return;
    setIsSaving(true);
    try {
      await api.patch(`/api/marketplace/drafts/${draftDetail.id}`, {
        override_patch: buildOverridePatch(),
        ...(markReady ? { status: 'ready' } : {}),
      });
      await loadDraftDetail(draftDetail.id);
      await loadDrafts();
    } catch (err: any) {
      setError(err.message || '초안 저장에 실패했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSubmitSelected = async () => {
    if (groupedSelection.length === 0) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await Promise.all(groupedSelection.map((group) =>
        api.post('/api/marketplace/submissions', {
          draft_ids: group.draft_ids,
          market_account_id: group.market_account_id,
        }),
      ));
      setSelectedIds(new Set());
      await loadDrafts();
      if (selectedDraftId) await loadDraftDetail(selectedDraftId);
    } catch (err: any) {
      setError(err.message || '제출 요청에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Marketplace Listing</p>
          <h1 className={styles.title}>마켓 등록 인박스</h1>
        </div>
        <div className={styles.headerActions}>
          <Link href="/marketplaces/accounts" className={styles.linkButton}>계정 설정</Link>
          <button type="button" className={styles.submitButton} onClick={handleSubmitSelected} disabled={isSubmitting || groupedSelection.length === 0}>
            {isSubmitting ? '제출 중...' : `선택 제출 (${selectedIds.size})`}
          </button>
        </div>
      </header>

      <section className={styles.filters}>
        <div className={styles.filterGroup}>
          {MARKET_FILTERS.map((market) => (
            <button key={market} className={marketFilter === market ? styles.activeChip : styles.chip} onClick={() => setMarketFilter(market)} type="button">
              {market === 'all' ? 'All' : formatMarket(market)}
            </button>
          ))}
        </div>
        <div className={styles.filterGroup}>
          {STATUS_FILTERS.map((status) => (
            <button key={status} className={statusFilter === status ? styles.activeChip : styles.chip} onClick={() => setStatusFilter(status)} type="button">
              {status === 'all' ? '전체 상태' : status}
            </button>
          ))}
        </div>
      </section>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.layout}>
        <section className={styles.listPane}>
          {isLoading ? <p className={styles.loading}>목록을 불러오는 중...</p> : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th />
                  <th>마켓</th>
                  <th>상품명</th>
                  <th>카테고리</th>
                  <th>가격</th>
                  <th>검증</th>
                  <th>상태</th>
                  <th>수정일</th>
                </tr>
              </thead>
              <tbody>
                {drafts.map((draft) => (
                  <tr key={draft.id} className={selectedDraftId === draft.id ? styles.activeRow : ''} onClick={() => setSelectedDraftId(draft.id)}>
                    <td onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(draft.id)}
                        onChange={(e) => {
                          const next = new Set(selectedIds);
                          if (e.target.checked) next.add(draft.id);
                          else next.delete(draft.id);
                          setSelectedIds(next);
                        }}
                      />
                    </td>
                    <td>{formatMarket(draft.market_code)}</td>
                    <td>{draft.display_title || '-'}</td>
                    <td>{draft.category_id || '-'}</td>
                    <td>{typeof draft.sale_price === 'number' ? `${draft.sale_price.toLocaleString('ko-KR')}원` : '-'}</td>
                    <td>{draft.validation_result?.status || '-'}</td>
                    <td>{draft.status}</td>
                    <td>{new Date(draft.updated_at).toLocaleDateString('ko-KR')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className={styles.detailPane}>
          {!selectedDraftId && <p className={styles.loading}>선택된 초안이 없습니다.</p>}
          {isDetailLoading && <p className={styles.loading}>상세 정보를 불러오는 중...</p>}
          {draftDetail && !isDetailLoading && (
            <>
              <h2 className={styles.detailTitle}>{formatMarket(draftDetail.market_code)} 초안 상세</h2>
              <div className={styles.grid}>
                <label>상품명<input value={draftForm.title} onChange={(e) => setDraftForm((prev) => ({ ...prev, title: e.target.value }))} /></label>
                <label>판매가<input type="number" value={draftForm.salePrice} onChange={(e) => setDraftForm((prev) => ({ ...prev, salePrice: e.target.value }))} /></label>
                <label>원가<input disabled value={String(draftDetail.cost_price ?? '')} /></label>
                <label>예상수익<input disabled value={String(draftDetail.expected_profit ?? '')} /></label>
                <label>예상마진율<input disabled value={typeof draftDetail.expected_margin_rate === 'number' ? `${draftDetail.expected_margin_rate.toFixed(2)}%` : ''} /></label>
                <label>카테고리<input value={draftForm.categoryId} onChange={(e) => setDraftForm((prev) => ({ ...prev, categoryId: e.target.value }))} /></label>
                <label>원산지<input value={draftForm.origin} onChange={(e) => setDraftForm((prev) => ({ ...prev, origin: e.target.value }))} /></label>
              </div>
              <label className={styles.blockLabel}>대표/추가 이미지 URL (줄바꿈 구분)<textarea value={draftForm.imageUrls} onChange={(e) => setDraftForm((prev) => ({ ...prev, imageUrls: e.target.value }))} /></label>
              <label className={styles.blockLabel}>상세 콘텐츠<textarea value={draftForm.detailContent} onChange={(e) => setDraftForm((prev) => ({ ...prev, detailContent: e.target.value }))} /></label>
              <label className={styles.blockLabel}>옵션 JSON<textarea value={draftForm.optionsJson} onChange={(e) => setDraftForm((prev) => ({ ...prev, optionsJson: e.target.value }))} /></label>

              <div className={styles.marketSection}>
                <h3>{draftDetail.market_code === 'smartstore' ? 'Smart Store 섹션' : 'Coupang 섹션'}</h3>
                <p className={styles.sectionText}>
                  {draftDetail.market_code === 'smartstore'
                    ? '타이틀 레시피 출력, 정책 기반 가격 결과, 이후 태그/속성 확장 영역'
                    : 'SKU(items) 구성, attributes, contents, 쿠팡 전용 타이틀/가격 정책 영역'}
                </p>
              </div>

              <div className={styles.detailActions}>
                <button type="button" className={styles.saveButton} onClick={() => handleSaveDraft(false)} disabled={isSaving}>
                {isSaving ? '저장 중...' : '초안 저장'}
                </button>
                <button type="button" className={styles.readyButton} onClick={() => handleSaveDraft(true)} disabled={isSaving}>
                  검토 완료
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
