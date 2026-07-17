'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { fieldChangeLines, FieldChanges } from '@/lib/fieldChanges';
import styles from './changeHistory.module.css';

interface ProductImport {
  id: string;
  filename: string;
  status: string;
  total_count: number;
  new_count: number;
  updated_count: number;
  removed_count: number;
  unchanged_count: number;
  wholesale_site_id: string | null;
  wholesale_site_name: string | null;
  created_at: string;
}

interface ChangeLog {
  id: string;
  product_id: string | null;
  product_code: string | null;
  original_name: string;
  change_type: 'new' | 'updated' | 'removed';
  changed_fields: string[];
  field_changes: FieldChanges;
  created_at: string;
}

interface ChangeLogList {
  total: number;
  items: ChangeLog[];
}

const PAGE_SIZE = 50;

const CHANGE_LABELS: Record<ChangeLog['change_type'], string> = {
  new: '신상품',
  updated: '변동',
  removed: '단종',
};

const CHANGE_BADGE_CLASS: Record<ChangeLog['change_type'], string> = {
  new: styles.sourceChangeNew,
  updated: styles.sourceChangeUpdated,
  removed: styles.sourceChangeRemoved,
};

const FILTERS: { key: string; label: string }[] = [
  { key: '', label: '전체' },
  { key: 'new', label: '신규' },
  { key: 'updated', label: '변동' },
  { key: 'removed', label: '단종' },
];

const STATUS_LABELS: Record<string, string> = {
  completed: '완료',
  processing: '가공 중',
  pending: '대기',
  imported: '가져옴',
  failed: '실패',
};

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function ChangeHistoryPanel() {
  const [imports, setImports] = useState<ProductImport[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [changes, setChanges] = useState<ChangeLog[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);

  const [isLoadingImports, setIsLoadingImports] = useState(true);
  const [isLoadingChanges, setIsLoadingChanges] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load upload runs; keep only runs that produced at least one change.
  useEffect(() => {
    const fetchImports = async () => {
      setIsLoadingImports(true);
      setError(null);
      try {
        const data = await api.get<ProductImport[]>('/api/processor/imports');
        const withChanges = data.filter(
          (imp) => imp.new_count + imp.updated_count + imp.removed_count > 0
        );
        setImports(withChanges);
        setSelectedId((prev) => prev ?? withChanges[0]?.id ?? null);
      } catch (err: any) {
        setError(err.message || '업로드 이력을 불러오는 중 오류가 발생했습니다.');
      } finally {
        setIsLoadingImports(false);
      }
    };
    fetchImports();
  }, []);

  const fetchChanges = useCallback(async () => {
    if (!selectedId) {
      setChanges([]);
      setTotal(0);
      return;
    }
    setIsLoadingChanges(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.append('page', String(page));
      params.append('page_size', String(PAGE_SIZE));
      if (filter) params.append('change_type', filter);
      const data = await api.get<ChangeLogList>(
        `/api/processor/imports/${selectedId}/changes?${params.toString()}`
      );
      setChanges(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message || '변동 내역을 불러오는 중 오류가 발생했습니다.');
    } finally {
      setIsLoadingChanges(false);
    }
  }, [selectedId, filter, page]);

  useEffect(() => {
    fetchChanges();
  }, [fetchChanges]);

  const selectRun = (id: string) => {
    setSelectedId(id);
    setFilter('');
    setPage(1);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Change History</p>
          <h1 className={styles.title}>변동 내역</h1>
        </div>
      </div>

      <div className={styles.layout}>
        {/* Upload runs list */}
        <div className={styles.runsPanel}>
          {isLoadingImports ? (
            <div className={styles.loadingState}>업로드 이력을 불러오는 중입니다...</div>
          ) : imports.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyText}>변동 내역이 없습니다.</div>
              <div className={styles.emptySubtext}>도매처 상품을 업로드하면 변동 내역이 기록됩니다.</div>
            </div>
          ) : (
            imports.map((imp) => (
              <button
                key={imp.id}
                className={`${styles.runCard} ${selectedId === imp.id ? styles.runCardActive : ''}`}
                onClick={() => selectRun(imp.id)}
                type="button"
              >
                <div className={styles.runTop}>
                  <span className={styles.runFilename} title={imp.filename}>{imp.filename}</span>
                  <span className={styles.runDate}>{formatDateTime(imp.created_at)}</span>
                </div>
                <div className={styles.runMeta}>
                  <span className={styles.runSupplier}>{imp.wholesale_site_name || '도매처 미지정'}</span>
                  <span className={`${styles.statusPill} ${styles[imp.status] || ''}`}>
                    {STATUS_LABELS[imp.status] || imp.status}
                  </span>
                </div>
                <div className={styles.countBadges}>
                  <span className={styles.countNew}>신규 {imp.new_count}</span>
                  <span className={styles.countUpdated}>변동 {imp.updated_count}</span>
                  <span className={styles.countRemoved}>단종 {imp.removed_count}</span>
                  <span className={styles.countUnchanged}>변경 없음 {imp.unchanged_count}</span>
                </div>
              </button>
            ))
          )}
        </div>

        {/* Change detail */}
        <div className={styles.detailPanel}>
          <div className={styles.filterChips}>
            {FILTERS.map((f) => (
              <button
                key={f.key || 'all'}
                className={`${styles.chip} ${filter === f.key ? styles.chipActive : ''}`}
                onClick={() => { setFilter(f.key); setPage(1); }}
                type="button"
              >
                {f.label}
              </button>
            ))}
          </div>

          {error && <div className={styles.errorState}>{error}</div>}

          {isLoadingChanges ? (
            <div className={styles.loadingState}>변동 내역을 불러오는 중입니다...</div>
          ) : !selectedId ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyText}>업로드 이력을 선택하세요.</div>
            </div>
          ) : changes.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyText}>해당 조건의 변동 내역이 없습니다.</div>
            </div>
          ) : (
            <div className={styles.tableWrapper}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th className={styles.typeCol}>유형</th>
                    <th className={styles.codeCol}>상품코드</th>
                    <th>상품명</th>
                    <th>변경 내용</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((c) => {
                    const lines = fieldChangeLines(c.field_changes);
                    return (
                      <tr key={c.id}>
                        <td>
                          <span className={`${styles.sourceChangeBadge} ${CHANGE_BADGE_CLASS[c.change_type]}`}>
                            {CHANGE_LABELS[c.change_type]}
                          </span>
                        </td>
                        <td className={styles.codeCell}>{c.product_code || '-'}</td>
                        <td className={styles.nameCell} title={c.original_name}>{c.original_name}</td>
                        <td>
                          {lines.length > 0 ? (
                            <div className={styles.changeLines}>
                              {lines.map((line, i) => (
                                <span key={i} className={styles.changeLine}>{line}</span>
                              ))}
                            </div>
                          ) : c.change_type === 'new' ? (
                            <span className={styles.emptyInline}>신규 등록</span>
                          ) : (
                            <span className={styles.emptyInline}>-</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!isLoadingChanges && total > PAGE_SIZE && (
            <div className={styles.pagination}>
              <div className={styles.pageInfo}>
                전체 {total}건 중 {(page - 1) * PAGE_SIZE + 1}-{Math.min(page * PAGE_SIZE, total)}건 표시
              </div>
              <div className={styles.pageControls}>
                <button
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                  className={styles.pageButton}
                >
                  이전
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                  className={styles.pageButton}
                >
                  다음
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
