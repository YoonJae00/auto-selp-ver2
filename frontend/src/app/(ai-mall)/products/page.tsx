'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from './products.module.css';

interface PlatformMapping {
  id: string;
  platform_name: string;
  category_id: string | null;
  category_path: string | null;
  sync_status: string;
  sync_error: string | null;
  mapped_attributes: any;
  price_changed?: boolean;
  stock_changed?: boolean;
}

interface Product {
  id: string;
  original_name: string;
  refined_name: string | null;
  option_values_raw?: string | null;
  option_variants?: { name: string; price_wholesale: number | null; position: number }[] | null;
  keywords: string[] | null;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  warnings: any;
  created_at: string;
  platform_mappings: PlatformMapping[];
}

interface ProductImport {
  id: string;
  filename: string;
  status: string;
  total_count: number;
  processed_count: number;
  created_at: string;
}

interface ProductListResponse {
  total: number;
  page: number;
  size: number;
  items: Product[];
}

interface WholesaleSite {
  id: string;
  name: string;
  homepage_url: string | null;
  column_mapping: any;
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [imports, setImports] = useState<ProductImport[]>([]);
  const [wholesaleSites, setWholesaleSites] = useState<WholesaleSite[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [size] = useState(15);
  
  // Filters
  const [search, setSearch] = useState('');
  const [searchDebounced, setSearchDebounced] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [importFilter, setImportFilter] = useState('');
  const [wholesaleFilter, setWholesaleFilter] = useState('');
  const [needsSyncFilter, setNeedsSyncFilter] = useState(false);
  
  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  
  // UI states
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounce search input
  useEffect(() => {
    const handler = setTimeout(() => {
      setSearchDebounced(search);
      setPage(1); // Reset to first page when search changes
    }, 300);
    return () => clearTimeout(handler);
  }, [search]);

  // Fetch Imports list on mount
  useEffect(() => {
    const fetchImports = async () => {
      try {
        const data = await api.get<ProductImport[]>('/api/processor/imports');
        setImports(data);
      } catch (err: any) {
        console.error('Failed to load imports history:', err);
      }
    };
    fetchImports();
  }, []);

  // Fetch Wholesale Sites on mount
  useEffect(() => {
    const fetchSites = async () => {
      try {
        const data = await api.get<WholesaleSite[]>('/api/processor/wholesale-sites');
        setWholesaleSites(data);
      } catch (err: any) {
        console.error('Failed to load wholesale sites:', err);
      }
    };
    fetchSites();
  }, []);

  // Fetch paginated products based on query criteria
  const fetchProducts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const queryParams = new URLSearchParams();
      queryParams.append('page', String(page));
      queryParams.append('size', String(size));
      if (searchDebounced) queryParams.append('search', searchDebounced);
      if (statusFilter) queryParams.append('status', statusFilter);
      if (importFilter) queryParams.append('import_id', importFilter);
      if (wholesaleFilter) queryParams.append('wholesale_site_id', wholesaleFilter);
      if (needsSyncFilter) queryParams.append('needs_sync', 'true');

      const response = await api.get<ProductListResponse>(`/api/processor/products?${queryParams.toString()}`);
      setProducts(response.items);
      setTotal(response.total);
    } catch (err: any) {
      setError(err.message || '상품 목록을 불러오는 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [page, size, searchDebounced, statusFilter, importFilter, wholesaleFilter, needsSyncFilter]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  // Reset selection when products change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [products]);

  // Select/Deselect handlers
  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const allIds = products.map((p) => p.id);
      setSelectedIds(new Set(allIds));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    const updated = new Set(selectedIds);
    if (checked) {
      updated.add(id);
    } else {
      updated.delete(id);
    }
    setSelectedIds(updated);
  };

  // Export selected or all completed products as Excel
  const handleExport = async () => {
    setIsExporting(true);
    try {
      const body = {
        product_ids: Array.from(selectedIds),
      };

      const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost';
      const response = await fetch(`${BASE_URL}/api/processor/products/export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
        credentials: 'include', // Pass session/jwt cookie directly
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || '엑셀 출력 실패');
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      
      const timeStamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      link.download = `autoselp_export_${timeStamp}.xlsx`;
      
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err: any) {
      alert('엑셀 내보내기 중 오류가 발생했습니다: ' + err.message);
    } finally {
      setIsExporting(false);
    }
  };

  // Stats calculation
  const totalPages = Math.ceil(total / size) || 1;
  const isAllSelected = products.length > 0 && selectedIds.size === products.length;
  const formatPrice = (value?: number | null) =>
    typeof value === 'number' ? `${value.toLocaleString('ko-KR')}원` : '-';

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Catalog Operations</p>
          <h1 className={styles.title}>상품 관리</h1>
        </div>
        <div className={styles.actionGroup}>
          <PillButton 
            variant="secondary" 
            onClick={() => {}} 
            className={styles.syncButton}
            type="button"
            disabled={true}
          >
            쇼핑몰 동기화 예정
          </PillButton>
          <PillButton 
            variant="primary" 
            onClick={handleExport} 
            className={styles.actionButton}
            type="button"
            disabled={isExporting}
          >
            {isExporting ? '내보내는 중...' : '엑셀 내보내기'}
            {selectedIds.size > 0 && ` (${selectedIds.size}개 선택됨)`}
          </PillButton>
        </div>
      </div>

      {/* Stats Cards */}
      <div className={styles.statsSection}>
        <div className={styles.statCard}>
          <h4>전체 등록 상품</h4>
          <div className={styles.statValue}>{total}개</div>
        </div>
        <div className={styles.statCard}>
          <h4>선택한 상품</h4>
          <div className={styles.statValue}>{selectedIds.size}개</div>
        </div>
        <div className={styles.statCard}>
          <h4>최근 업로드 파일 수</h4>
          <div className={styles.statValue}>{imports.length}회</div>
        </div>
      </div>

      {/* Filters Toolbar */}
      <div className={styles.filterBar}>
        <div className={styles.searchGroup}>
          <span className={styles.searchIcon}>🔍</span>
          <input 
            type="text" 
            placeholder="원래 상품명으로 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={styles.searchInput}
          />
        </div>

        <div className={styles.selectGroup}>
          <span className={styles.selectLabel}>도매처</span>
          <select 
            value={wholesaleFilter} 
            onChange={(e) => { setWholesaleFilter(e.target.value); setPage(1); }}
            className={styles.select}
          >
            <option value="">전체 도매처</option>
            {wholesaleSites.map((site) => (
              <option key={site.id} value={site.id}>
                {site.name}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.selectGroup}>
          <span className={styles.selectLabel}>가공 상태</span>
          <select 
            value={statusFilter} 
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className={styles.select}
          >
            <option value="">전체 상태</option>
            <option value="pending">대기 중 (Pending)</option>
            <option value="processing">가공 중 (Processing)</option>
            <option value="completed">완료 (Completed)</option>
            <option value="failed">실패 (Failed)</option>
          </select>
        </div>

        <div className={styles.selectGroup}>
          <span className={styles.selectLabel}>업로드 배치</span>
          <select 
            value={importFilter} 
            onChange={(e) => { setImportFilter(e.target.value); setPage(1); }}
            className={styles.select}
          >
            <option value="">전체 업로드 이력</option>
            {imports.map((imp) => (
              <option key={imp.id} value={imp.id}>
                {imp.filename} ({imp.total_count}개)
              </option>
            ))}
          </select>
        </div>

        <label className={styles.checkboxLabel}>
          <input 
            type="checkbox"
            checked={needsSyncFilter}
            onChange={(e) => { setNeedsSyncFilter(e.target.checked); setPage(1); }}
            className={styles.checkbox}
          />
          업데이트 대기 상품만 보기
        </label>
      </div>

      {/* Products Table Section */}
      <div className={styles.tableSection}>
        {error && <div className={styles.errorState}>{error}</div>}
        
        {isLoading ? (
          <div className={styles.loadingState}>
            데이터를 불러오는 중입니다...
          </div>
        ) : products.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyText}>등록된 상품이 없습니다.</div>
            <div className={styles.emptySubtext}>상품 가공 탭에서 새로운 엑셀 파일을 업로드하고 가공해 보세요.</div>
          </div>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.checkboxCol}>
                    <input 
                      type="checkbox" 
                      checked={isAllSelected}
                      onChange={handleSelectAll}
                      className={styles.checkbox}
                    />
                  </th>
                  <th>상품 명칭 (원래 상품명 / 정제상품명)</th>
                  <th>정제 키워드</th>
                  <th>옵션</th>
                  <th>마켓 카테고리 매핑</th>
                  <th>상태</th>
                  <th>등록 시각</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => {
                  // Mappings extraction
                  const naverMapping = p.platform_mappings.find((m) => m.platform_name === 'naver');
                  const coupangMapping = p.platform_mappings.find((m) => m.platform_name === 'coupang');
                  const priceChanged = p.platform_mappings.some((m) => m.price_changed);
                  const stockChanged = p.platform_mappings.some((m) => m.stock_changed);

                  return (
                    <tr key={p.id}>
                      <td className={styles.checkboxCol}>
                        <input 
                          type="checkbox"
                          checked={selectedIds.has(p.id)}
                          onChange={(e) => handleSelectOne(p.id, e.target.checked)}
                          className={styles.checkbox}
                        />
                      </td>
                      <td>
                        <div className={styles.nameWrapper}>
                          <span className={styles.refName}>
                            {p.refined_name ? p.refined_name : <span className={styles.refNameEmpty}>가공 전</span>}
                            {priceChanged && <span className={styles.changeBadgeOrange}>가격 변동</span>}
                            {stockChanged && <span className={styles.changeBadgeRed}>품절 변동</span>}
                          </span>
                          <span className={styles.origName}>원본: {p.original_name}</span>
                        </div>
                      </td>
                      <td>
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
                      <td>
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
                      <td>
                        <div className={styles.categoryCell}>
                          <div className={styles.marketBadge}>
                            <span className={`${styles.marketLabel} ${styles.naver}`}>Naver</span>
                            {naverMapping && (naverMapping.category_path || naverMapping.category_id) ? (
                              <span className={styles.categoryPath} title={naverMapping.category_path || ''}>
                                {naverMapping.category_path || naverMapping.category_id}
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
                      <td>
                        <span className={`${styles.statusPill} ${styles[p.status]}`}>
                          {p.status === 'completed' && '완료'}
                          {p.status === 'processing' && '가공 중'}
                          {p.status === 'pending' && '대기'}
                          {p.status === 'failed' && '실패'}
                        </span>
                      </td>
                      <td className={styles.dateCell}>
                        {new Date(p.created_at).toLocaleString('ko-KR', {
                          month: 'numeric',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Row */}
        {!isLoading && products.length > 0 && (
          <div className={styles.pagination}>
            <div className={styles.pageInfo}>
              전체 {total}개 중 {(page - 1) * size + 1}-{Math.min(page * size, total)}개 표시
            </div>
            <div className={styles.pageControls}>
              <button 
                disabled={page === 1} 
                onClick={() => setPage(page - 1)}
                className={styles.pageButton}
              >
                이전
              </button>
              {Array.from({ length: totalPages }).map((_, i) => {
                const pNum = i + 1;
                // Only show a range of page buttons to avoid overflow if pages are high
                if (totalPages > 5 && Math.abs(page - pNum) > 2 && pNum !== 1 && pNum !== totalPages) {
                  if (pNum === 2 || pNum === totalPages - 1) {
                    return <span key={pNum} className={styles.pageEllipsis}>...</span>;
                  }
                  return null;
                }
                return (
                  <button 
                    key={pNum} 
                    onClick={() => setPage(pNum)}
                    className={`${styles.pageButton} ${page === pNum ? styles.activePage : ''}`}
                  >
                    {pNum}
                  </button>
                );
              })}
              <button 
                disabled={page === totalPages} 
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
  );
}
