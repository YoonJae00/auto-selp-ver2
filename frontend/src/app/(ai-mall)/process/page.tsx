'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useSettingsStore } from '@/store/settingsStore';
import { useTaskStore } from '@/store/taskStore';
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from './process.module.css';

interface WholesaleSite {
  id: string;
  name: string;
  homepage_url: string | null;
  column_mapping: Record<string, string> | null;
}

interface ProductPlatformMapping {
  id: string;
  platform_name: string;
  category_id: string | null;
  category_path: string | null;
  sync_status: string;
  mapped_attributes: Record<string, any> | null;
}

interface Product {
  id: string;
  wholesale_site_id: string | null;
  product_code: string | null;
  wholesale_product_id: string | null;
  price_wholesale: number | null;
  price_retail: number | null;
  price_min_selling: number | null;
  origin: string | null;
  option_values_raw: string | null;
  option_variants?: { name: string; price_wholesale: number | null; position: number }[] | null;
  images_list: string[] | null;
  image_detail: string | null;
  wholesale_status: string | null;
  original_name: string;
  refined_name: string | null;
  keywords: string[] | null;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  platform_mappings?: ProductPlatformMapping[] | null;
}

interface ProductListResponse {
  total: number;
  page: number;
  size: number;
  items: Product[];
}

const formatPrice = (value: number | null) => {
  if (value === null || value === undefined) return '-';
  return `${value.toLocaleString('ko-KR')}원`;
};

const firstImage = (product: Product) => {
  const image = product.images_list?.find(Boolean) || product.image_detail;
  return image || '';
};

const processingStatusLabel: Record<Product['status'], string> = {
  pending: '대기',
  processing: '가공 중',
  completed: '완료',
  failed: '실패',
};

const renderAttributes = (product: Product) => {
  if (!product.platform_mappings || product.platform_mappings.length === 0) {
    return <span className={styles.emptyAttributes}>-</span>;
  }

  const coupangMapping = product.platform_mappings.find((m) => m.platform_name === 'coupang');
  const naverMapping = product.platform_mappings.find((m) => m.platform_name === 'naver');

  const attrsList: { key: string; value: string }[] = [];

  if (coupangMapping?.mapped_attributes) {
    const coupangAttrs = coupangMapping.mapped_attributes;
    const prodAttrs = coupangAttrs.product_attributes || [];
    const itemAttrs = coupangAttrs.item_attributes || [];

    prodAttrs.forEach((attr: any) => {
      if (attr.attributeTypeName && attr.attributeValueName) {
        attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
      }
    });

    itemAttrs.forEach((attr: any) => {
      if (attr.attributeTypeName && attr.attributeValueName) {
        if (!attrsList.some((a) => a.key === attr.attributeTypeName)) {
          attrsList.push({ key: attr.attributeTypeName, value: attr.attributeValueName });
        }
      }
    });
  }

  if (attrsList.length === 0 && Array.isArray(naverMapping?.mapped_attributes)) {
    const naverAttrs = naverMapping.mapped_attributes;
    naverAttrs.forEach((attr: any) => {
      if (attr.attributeRealValue) {
        attrsList.push({ key: `속성 #${attr.attributeSeq}`, value: attr.attributeRealValue });
      }
    });
  }

  if (attrsList.length === 0) {
    return <span className={styles.emptyAttributes}>-</span>;
  }

  return (
    <div className={styles.attributeCloud}>
      {attrsList.map((attr, idx) => (
        <span key={`${product.id}-attr-${idx}`} className={styles.attributeTag}>
          <span className={styles.attributeKey}>{attr.key}</span>: {attr.value}
        </span>
      ))}
    </div>
  );
};

export default function ProcessPage() {
  const { llmProvider, visionLlmProvider, kiprisEnabled } = useSettingsStore();
  const { tasks, addTask } = useTaskStore();

  const [wholesaleSites, setWholesaleSites] = useState<WholesaleSite[]>([]);
  const [activeSiteId, setActiveSiteId] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoadingSites, setIsLoadingSites] = useState(true);
  const [isLoadingProducts, setIsLoadingProducts] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [completedOnly, setCompletedOnly] = useState(false);
  const [sortMode, setSortMode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearchQuery, setActiveSearchQuery] = useState('');
  const [pageSize, setPageSize] = useState(30);

  const activeSite = useMemo(
    () => wholesaleSites.find((site) => site.id === activeSiteId) || null,
    [activeSiteId, wholesaleSites],
  );
  const totalPages = Math.ceil(total / pageSize) || 1;
  const isAllSelected = products.length > 0 && products.every((product) => selectedIds.has(product.id));

  useEffect(() => {
    const fetchSites = async () => {
      setIsLoadingSites(true);
      setError(null);
      try {
        const data = await api.get<WholesaleSite[]>('/api/processor/wholesale-sites');
        setWholesaleSites(data);
        if (data.length > 0) setActiveSiteId(data[0].id);
      } catch (err: any) {
        setError(err.message || '도매처 목록을 불러오지 못했습니다.');
      } finally {
        setIsLoadingSites(false);
      }
    };

    fetchSites();
  }, []);

  const fetchProducts = useCallback(async () => {
    if (!activeSiteId) {
      setProducts([]);
      setTotal(0);
      return;
    }

    setIsLoadingProducts(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        size: String(pageSize),
        wholesale_site_id: activeSiteId,
      });
      if (activeSearchQuery.trim()) {
        params.append('search', activeSearchQuery.trim());
      }
      const effectiveStatus = completedOnly ? 'completed' : statusFilter;
      if (effectiveStatus) params.append('status', effectiveStatus);
      if (sortMode === 'price_asc') {
        params.append('sort_by', 'price_wholesale');
        params.append('sort_order', 'asc');
      } else if (sortMode === 'price_desc') {
        params.append('sort_by', 'price_wholesale');
        params.append('sort_order', 'desc');
      } else if (sortMode === 'option_count_desc') {
        params.append('sort_by', 'option_count');
        params.append('sort_order', 'desc');
      }

      const response = await api.get<ProductListResponse>(`/api/processor/products?${params.toString()}`);
      setProducts(response.items);
      setTotal(response.total);
    } catch (err: any) {
      setError(err.message || '상품 목록을 불러오지 못했습니다.');
    } finally {
      setIsLoadingProducts(false);
    }
  }, [activeSiteId, page, pageSize, statusFilter, completedOnly, sortMode, activeSearchQuery]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  useEffect(() => {
    setSelectedIds(new Set());
    setPage(1);
    setSearchQuery('');
    setActiveSearchQuery('');
  }, [activeSiteId]);

  useEffect(() => {
    setSelectedIds(new Set());
    setPage(1);
  }, [statusFilter, completedOnly, sortMode, activeSearchQuery, pageSize]);

  // Memoize a map of completed rows by product name from all active tasks
  const completedRowsMap = useMemo(() => {
    const map = new Map<string, {
      refined_name: string | null;
      keywords: string[] | null;
      status: 'completed' | 'failed' | 'processing';
      error?: string;
    }>();

    tasks.forEach((task) => {
      // Process finished/active task rows
      if (task.completedRows) {
        task.completedRows.forEach((row) => {
          const refiningStage = row.stages?.find(s => s.name === 'refining') as any;
          const keywordsStage = row.stages?.find(s => s.name === 'keywords') as any;
          
          map.set(row.name, {
            refined_name: refiningStage?.refined_name || null,
            keywords: keywordsStage?.keywords || null,
            status: row.error ? 'failed' : 'completed',
            error: row.error,
          });
        });
      }

      // If a task is PROGRESS, mark the current item as processing
      if (task.status === 'PROGRESS' && task.currentName) {
        if (!map.has(task.currentName)) {
          map.set(task.currentName, {
            refined_name: null,
            keywords: null,
            status: 'processing',
          });
        }
      }
    });

    return map;
  }, [tasks]);

  // Automatically fetch products when a running task completes or fails to sync with DB
  const prevActiveTaskIdsRef = useRef<string[]>([]);
  useEffect(() => {
    const activeTasks = tasks.filter(t => t.status === 'PENDING' || t.status === 'PROGRESS');
    const activeIds = activeTasks.map(t => t.id);
    const prevActiveIds = prevActiveTaskIdsRef.current;
    
    // Check if any task that was active has finished (SUCCESS or FAILURE)
    const justFinished = prevActiveIds.some(id => {
      const task = tasks.find(t => t.id === id);
      return task && (task.status === 'SUCCESS' || task.status === 'FAILURE');
    });

    if (justFinished) {
      fetchProducts();
    }

    prevActiveTaskIdsRef.current = activeIds;
  }, [tasks, fetchProducts]);

  const toggleProduct = (productId: string, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(productId);
      else next.delete(productId);
      return next;
    });
  };

  const togglePage = (checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      products.forEach((product) => {
        if (checked) next.add(product.id);
        else next.delete(product.id);
      });
      return next;
    });
  };

  const handleStartSelectedProcessing = async () => {
    if (!activeSite || selectedIds.size === 0) return;

    setIsStarting(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await api.post<{ task_id: string; filename: string; total: number }>('/api/processor/process-products', {
        product_ids: Array.from(selectedIds),
        column_mapping: activeSite.column_mapping || { original_name: 'original_name' },
        llm_provider: llmProvider,
        vision_llm_provider: visionLlmProvider,
        kipris_enabled: kiprisEnabled,
      });

      addTask({
        id: response.task_id,
        filename: `${activeSite.name} 선택 상품`,
        progress: 0,
        total: response.total,
        status: 'PENDING',
        startTime: Date.now(),
      });

      setSuccess(`${response.total}개 상품 가공을 시작했습니다. 좌측 하단 진행 캡슐에서 상태를 확인할 수 있습니다.`);
      setSelectedIds(new Set());
      fetchProducts();
    } catch (err: any) {
      setError(err.message || '상품 가공 시작 중 오류가 발생했습니다.');
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>상품 가공</h1>
          <p className={styles.subtitle}>도매처를 선택한 뒤 DB에 저장된 상품 중 필요한 것만 골라 가공합니다.</p>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {success && <div className={styles.success}>{success}</div>}

      <section className={styles.supplierRail} aria-label="도매처 선택">
        {isLoadingSites && <div className={styles.emptyState}>도매처를 불러오는 중입니다.</div>}
        {!isLoadingSites && wholesaleSites.length === 0 && (
          <div className={styles.emptyState}>먼저 업로드 화면에서 도매처를 추가하고 상품 엑셀을 DB에 저장해 주세요.</div>
        )}
        {wholesaleSites.map((site) => (
          <button
            key={site.id}
            type="button"
            className={`${styles.supplierButton} ${activeSiteId === site.id ? styles.activeSupplier : ''}`}
            onClick={() => setActiveSiteId(site.id)}
          >
            <span className={styles.supplierName}>{site.name}</span>
            <span className={styles.supplierMeta}>
              {site.column_mapping ? `${Object.keys(site.column_mapping).length}개 매핑` : '매핑 없음'}
            </span>
          </button>
        ))}
      </section>

      {activeSite && (
        <section className={styles.productSection}>
          <div className={styles.tableToolbar}>
            <div>
              <h2 className={styles.sectionTitle}>{activeSite.name} 상품 목록</h2>
              <p className={styles.sectionDesc}>총 {total.toLocaleString('ko-KR')}개 중 현재 페이지 {products.length}개 표시</p>
            </div>
            <div className={styles.toolbarActions}>
              <PillButton
                variant="primary"
                onClick={handleStartSelectedProcessing}
                disabled={selectedIds.size === 0 || isStarting}
                type="button"
              >
                {isStarting ? '가공 시작 중...' : `선택 상품 가공 (${selectedIds.size})`}
              </PillButton>
            </div>
          </div>

          <div className={styles.filterBar} aria-label="상품 필터">
            <div className={styles.filterLeft}>
              <div className={styles.searchGroup}>
                <input
                  type="text"
                  className={styles.searchInput}
                  placeholder="상품명으로 검색..."
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      setActiveSearchQuery(searchQuery);
                    }
                  }}
                />
                {searchQuery && (
                  <button
                    type="button"
                    className={styles.clearSearchButton}
                    onClick={() => {
                      setSearchQuery('');
                      setActiveSearchQuery('');
                    }}
                    title="검색어 지우기"
                  >
                    ✕
                  </button>
                )}
              </div>

              <label className={styles.filterGroup}>
                <span>가공 상태</span>
                <select
                  value={statusFilter}
                  onChange={(event) => {
                    setStatusFilter(event.target.value);
                    setCompletedOnly(event.target.value === 'completed');
                  }}
                >
                  <option value="">전체 상태</option>
                  <option value="pending">대기</option>
                  <option value="processing">가공 중</option>
                  <option value="completed">완료</option>
                  <option value="failed">실패</option>
                </select>
              </label>

              <label className={styles.filterGroup}>
                <span>정렬</span>
                <select
                  value={sortMode}
                  onChange={(event) => setSortMode(event.target.value)}
                >
                  <option value="">기본순</option>
                  <option value="price_asc">낮은 도매가순</option>
                  <option value="price_desc">높은 도매가순</option>
                  <option value="option_count_desc">옵션 많은 순</option>
                </select>
              </label>

              <label className={styles.filterGroup}>
                <span>보기 개수</span>
                <select
                  value={pageSize}
                  onChange={(event) => setPageSize(Number(event.target.value))}
                >
                  <option value={10}>10개씩 보기</option>
                  <option value={30}>30개씩 보기</option>
                  <option value={50}>50개씩 보기</option>
                  <option value={100}>100개씩 보기</option>
                  <option value={200}>200개씩 보기</option>
                </select>
              </label>

              <label className={`${styles.filterToggle} ${completedOnly ? styles.activeFilterToggle : ''}`}>
                <input
                  type="checkbox"
                  checked={completedOnly}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setCompletedOnly(checked);
                    setStatusFilter(checked ? 'completed' : '');
                  }}
                />
                가공 완료만 보기
              </label>
            </div>

            <div className={styles.filterRight}>
              <div className={styles.topPagination}>
                <button
                  type="button"
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                  disabled={page <= 1 || isLoadingProducts}
                >
                  이전
                </button>
                <span>{page} / {totalPages}</span>
                <button
                  type="button"
                  onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                  disabled={page >= totalPages || isLoadingProducts}
                >
                  다음
                </button>
              </div>
            </div>
          </div>

          <div className={styles.sheetFrame}>
            <table className={styles.productTable}>
              <thead>
                <tr>
                  <th className={styles.checkboxCell}>
                    <input
                      type="checkbox"
                      checked={isAllSelected}
                      onChange={(event) => togglePage(event.target.checked)}
                      title="현재 페이지 전체 선택"
                      aria-label="현재 페이지 전체 선택"
                    />
                  </th>
                  <th className={styles.imageCell}>원본 사진</th>
                  <th>상품명</th>
                  <th>옵션</th>
                  <th>가공된 상품명</th>
                  <th>키워드</th>
                  <th>도매처 코드</th>
                  <th>도매가</th>
                  <th>속성</th>
                  <th>가공상태</th>
                </tr>
              </thead>
              <tbody>
                {isLoadingProducts && (
                  <tr>
                    <td colSpan={10} className={styles.tableMessage}>상품을 불러오는 중입니다.</td>
                  </tr>
                )}
                {!isLoadingProducts && products.length === 0 && (
                  <tr>
                    <td colSpan={10} className={styles.tableMessage}>이 조건에 맞는 상품이 없습니다.</td>
                  </tr>
                )}
                {!isLoadingProducts && products.map((product) => {
                  const imageUrl = firstImage(product);
                  const realTimeUpdate = completedRowsMap.get(product.original_name);
                  const displayStatus = realTimeUpdate ? realTimeUpdate.status : product.status;
                  const displayRefinedName = realTimeUpdate && realTimeUpdate.refined_name ? realTimeUpdate.refined_name : product.refined_name;
                  const displayKeywords = realTimeUpdate && realTimeUpdate.keywords ? realTimeUpdate.keywords : product.keywords;
                  const hasAiResult = displayStatus === 'completed' && (!!displayRefinedName || (displayKeywords?.length ?? 0) > 0);
                  return (
                    <tr key={product.id} className={selectedIds.has(product.id) ? styles.selectedRow : ''}>
                      <td className={styles.checkboxCell}>
                        <input
                          type="checkbox"
                          checked={selectedIds.has(product.id)}
                          onChange={(event) => toggleProduct(product.id, event.target.checked)}
                        />
                      </td>
                      <td className={styles.imageCell}>
                        {imageUrl ? (
                          <img src={imageUrl} alt="" className={styles.productImage} />
                        ) : (
                          <div className={styles.imagePlaceholder}>이미지 없음</div>
                        )}
                      </td>
                      <td className={styles.nameCell}>
                        <strong>{product.original_name}</strong>
                        <span>
                          {product.option_variants && product.option_variants.length > 0
                            ? `옵션 ${product.option_variants.length}개`
                            : '단일 상품'}
                        </span>
                      </td>
                      <td>
                        {product.option_variants && product.option_variants.length > 0 ? (
                          <details className={styles.optionDetails}>
                            <summary className={styles.optionSummary}>
                              <span className={styles.optionCount}>옵션 {product.option_variants.length}개</span>
                              <span className={styles.optionPreview}>
                                {product.option_variants[0].name} · {formatPrice(product.option_variants[0].price_wholesale)}
                              </span>
                            </summary>
                            <ul className={styles.optionTree}>
                              {product.option_variants.map((option, index) => (
                                <li key={`${product.id}-${option.name}-${index}`} className={styles.optionItem}>
                                  <span className={styles.optionName}>{option.name}</span>
                                  <span className={styles.optionPrice}>{formatPrice(option.price_wholesale)}</span>
                                </li>
                              ))}
                            </ul>
                          </details>
                        ) : product.option_values_raw ? (
                          <div className={styles.optionFallback}>{product.option_values_raw}</div>
                        ) : (
                          <span className={styles.optionEmpty}>없음</span>
                        )}
                      </td>
                      <td>
                        {hasAiResult ? (
                          <div className={styles.aiResultCell}>
                            <span className={styles.aiResultLabel}>AI 정제</span>
                            <div className={styles.aiRefinedName}>{displayRefinedName || '-'}</div>
                          </div>
                        ) : (
                          <span className={styles.aiResultEmpty}>
                            {displayStatus === 'processing' ? '가공 중...' : '가공 전'}
                          </span>
                        )}
                      </td>
                      <td>
                        {hasAiResult && displayKeywords && displayKeywords.length > 0 ? (
                          <div className={styles.keywordCloud}>
                            {displayKeywords.slice(0, 6).map((keyword) => (
                              <span key={`${product.id}-${keyword}`} className={styles.keywordPill}>
                                {keyword}
                              </span>
                            ))}
                            {displayKeywords.length > 6 && (
                              <span className={styles.keywordMore}>+{displayKeywords.length - 6}</span>
                            )}
                          </div>
                        ) : (
                          <span className={styles.aiResultEmpty}>-</span>
                        )}
                      </td>
                      <td>{product.product_code || product.wholesale_product_id || '-'}</td>
                      <td className={styles.priceCell}>{formatPrice(product.price_wholesale)}</td>
                      <td>{renderAttributes(product)}</td>
                      <td>
                        <span className={`${styles.statusBadge} ${styles[`status_${displayStatus}`] || ''}`}>
                          {processingStatusLabel[displayStatus]}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className={styles.pagination}>
            <button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1}>
              이전
            </button>
            <span>{page} / {totalPages}</span>
            <button type="button" onClick={() => setPage((value) => Math.min(totalPages, value + 1))} disabled={page >= totalPages}>
              다음
            </button>
          </div>
        </section>
      )}

      {/* Floating Action Bar */}
      {selectedIds.size > 0 && (
        <div className={styles.floatingActionBar}>
          <div className={styles.floatingContent}>
            <span className={styles.floatingText}>
              ✨ 현재 <strong>{selectedIds.size}</strong>개의 상품이 선택되었습니다.
            </span>
            <div className={styles.floatingButtons}>
              <PillButton
                variant="primary"
                onClick={handleStartSelectedProcessing}
                disabled={isStarting}
                type="button"
              >
                {isStarting ? '가공 시작 중...' : '선택 상품 가공'}
              </PillButton>
              <button
                type="button"
                className={styles.floatingCancelButton}
                onClick={() => setSelectedIds(new Set())}
              >
                선택 취소
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
