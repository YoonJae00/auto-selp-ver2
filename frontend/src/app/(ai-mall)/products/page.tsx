'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from './products.module.css';
import DeleteConfirmModal from '@/components/UI/DeleteConfirmModal/DeleteConfirmModal';

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

type StandardOption = {
  option_sku: string | null;
  option_display_name: string;
  option_supply_price: number | null;
  option_price_delta: number | null;
  option_stock_quantity: number | null;
  option_status: string | null;
  option_main_image_url: string | null;
  option_position: number;
};

interface Product {
  id: string;
  original_name: string;
  refined_name: string | null;
  option_values_raw?: string | null;
  option_variants?: { name: string; price_wholesale: number | null; position: number }[] | null;
  standard_options?: StandardOption[] | null;
  keywords: string[] | null;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  change_type: 'new' | 'updated' | null;
  changed_fields: string[] | null;
  warnings: any;
  created_at: string;
  platform_mappings: PlatformMapping[];
  // Column configuration fields
  product_code?: string | null;
  wholesale_product_id?: string | null;
  price_wholesale?: number | null;
  price_retail?: number | null;
  price_min_selling?: number | null;
  origin?: string | null;
  brand_name?: string | null;
  wholesale_status?: string | null;
  wholesale_registered_at?: string | null;
  images_list?: string[] | null;
  raw_metadata?: any | null;
  image_detail?: string | null;
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

const DEFAULT_ORDER = [
  'checkbox',
  'main_image',
  'refined_name',
  'original_name',
  'brand_name',
  'keywords',
  'option_variants',
  'option_values_raw',
  'platform_mappings',
  'mapped_attributes',
  'warnings',
  'status',
  'raw_metadata',
  'image_detail',
  'product_code',
  'wholesale_product_id',
  'price_wholesale',
  'price_retail',
  'price_min_selling',
  'origin',
  'wholesale_status',
  'wholesale_registered_at',
  'created_at'
];

const COLUMN_CONFIG_VERSION = 2;

const DEFAULT_VISIBILITY: Record<string, boolean> = {
  checkbox: true,
  main_image: true,
  refined_name: true,
  original_name: false,
  brand_name: false,
  keywords: false,
  option_variants: true,
  option_values_raw: false,
  platform_mappings: true,
  mapped_attributes: false,
  warnings: true,
  status: true,
  raw_metadata: false,
  image_detail: false,
  product_code: false,
  wholesale_product_id: false,
  price_wholesale: true,
  price_retail: false,
  price_min_selling: false,
  origin: false,
  wholesale_status: false,
  wholesale_registered_at: false,
  created_at: true
};

const COLUMNS_REGISTRY: Record<string, string> = {
  checkbox: '',
  main_image: '이미지',
  refined_name: '상품 정보',
  original_name: '기존 상품명',
  brand_name: '브랜드명',
  keywords: '정제 키워드',
  option_variants: '옵션 · 공급가',
  option_values_raw: '옵션 원본',
  platform_mappings: '마켓 매핑',
  mapped_attributes: '가공 속성',
  warnings: '확인 필요',
  status: '가공 상태',
  raw_metadata: '원본 데이터',
  image_detail: '상세이미지 URL',
  product_code: '상품 코드',
  wholesale_product_id: '도매처 상품 ID',
  price_wholesale: '도매가',
  price_retail: '소매가',
  price_min_selling: '최소 판매가',
  origin: '원산지',
  wholesale_status: '도매 상태',
  wholesale_registered_at: '도매 등록일',
  created_at: '등록일'
};

const WARNING_FIELD_LABELS: Record<string, string> = {
  price_wholesale_raw: '공급가',
  option_variants: '옵션',
  image_detail: '상세 이미지',
  supplier_name: '도매처',
  supplier_product_id: '도매처 상품 ID',
  supplier_product_code: '상품 코드',
  supplier_status: '판매 상태',
  raw_product_name: '기존 상품명'
};

const WARNING_MESSAGE_LABELS: Record<string, string> = {
  'Required value is blank.': '필수 값이 비어 있습니다.',
  'One or more option prices could not be parsed.': '옵션 가격 일부를 숫자로 읽을 수 없습니다.',
  'Option count and price count differ.': '옵션 개수와 가격 개수가 일치하지 않습니다.',
  trademark: '상표권 검토가 필요한 키워드입니다.'
};

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
  const [sortMode, setSortMode] = useState('');
  
  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  
  // UI states
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Deletion states
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteConfig, setDeleteConfig] = useState<{
    mode: 'selected' | 'wholesale';
    count: number;
    wholesaleSiteId?: string;
  } | null>(null);
  const [warningSyncedCount, setWarningSyncedCount] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Column settings & drag-and-drop states
  const [columnOrder, setColumnOrder] = useState<string[]>(DEFAULT_ORDER);
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(DEFAULT_VISIBILITY);
  const [showSettings, setShowSettings] = useState(false);
  const [draggedColKey, setDraggedColKey] = useState<string | null>(null);
  const [dragOverColKey, setDragOverColKey] = useState<string | null>(null);
  const [dragDirection, setDragDirection] = useState<'left' | 'right' | null>(null);

  // Load configuration from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem('autoselp_product_columns_config');
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.version === COLUMN_CONFIG_VERSION && parsed.order && Array.isArray(parsed.order)) {
          const filteredOrder = parsed.order.filter((k: string) => COLUMNS_REGISTRY[k] !== undefined);
          const missingKeys = DEFAULT_ORDER.filter((k) => !filteredOrder.includes(k));
          setColumnOrder([...filteredOrder, ...missingKeys]);
        }
        if (
          parsed.version === COLUMN_CONFIG_VERSION &&
          parsed.visibility &&
          typeof parsed.visibility === 'object'
        ) {
          setColumnVisibility({ ...DEFAULT_VISIBILITY, ...parsed.visibility });
        }
      }
    } catch (e) {
      console.error('Failed to load columns config from localStorage:', e);
    }
  }, []);

  // Persist configuration to localStorage
  const updateConfig = (newOrder: string[], newVisibility: Record<string, boolean>) => {
    try {
      localStorage.setItem(
        'autoselp_product_columns_config',
        JSON.stringify({ version: COLUMN_CONFIG_VERSION, order: newOrder, visibility: newVisibility })
      );
    } catch (e) {
      console.error('Failed to save columns config to localStorage:', e);
    }
  };

  // Toggle dynamic column visibility
  const toggleColumnVisibility = (key: string) => {
    if (key === 'checkbox') return;
    const updated = {
      ...columnVisibility,
      [key]: !columnVisibility[key]
    };
    setColumnVisibility(updated);
    updateConfig(columnOrder, updated);
  };

  // Outside click to close column settings popover
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      const container = document.getElementById('column-settings-container');
      if (container && !container.contains(e.target as Node)) {
        setShowSettings(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, []);

  // Drag & Drop event handlers
  const handleDragStart = (e: React.DragEvent<HTMLTableHeaderCellElement>, key: string) => {
    if (key === 'checkbox') return;
    setDraggedColKey(key);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent<HTMLTableHeaderCellElement>, key: string) => {
    if (key === 'checkbox' || !draggedColKey || draggedColKey === key) return;
    e.preventDefault();

    const targetRect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - targetRect.left;
    const midpoint = targetRect.width / 2;

    const direction: 'left' | 'right' = mouseX < midpoint ? 'left' : 'right';
    setDragOverColKey(key);
    setDragDirection(direction);
  };

  const handleDrop = (e: React.DragEvent<HTMLTableHeaderCellElement>, targetKey: string) => {
    if (targetKey === 'checkbox' || !draggedColKey || draggedColKey === targetKey) return;
    e.preventDefault();

    const activeIndex = columnOrder.indexOf(draggedColKey);
    let targetIndex = columnOrder.indexOf(targetKey);

    if (activeIndex === -1 || targetIndex === -1) return;

    const updatedOrder = columnOrder.filter((key) => key !== draggedColKey);

    if (dragDirection === 'right') {
      targetIndex = updatedOrder.indexOf(targetKey) + 1;
    } else {
      targetIndex = updatedOrder.indexOf(targetKey);
    }

    updatedOrder.splice(targetIndex, 0, draggedColKey);
    setColumnOrder(updatedOrder);
    updateConfig(updatedOrder, columnVisibility);

    setDraggedColKey(null);
    setDragOverColKey(null);
    setDragDirection(null);
  };

  const handleDragEnd = () => {
    setDraggedColKey(null);
    setDragOverColKey(null);
    setDragDirection(null);
  };

  // Debounce search input
  useEffect(() => {
    const handler = setTimeout(() => {
      setSearchDebounced(search);
      setPage(1);
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
      if (sortMode === 'option_count_desc') {
        queryParams.append('sort_by', 'option_count');
        queryParams.append('sort_order', 'desc');
      }

      const response = await api.get<ProductListResponse>(`/api/processor/products?${queryParams.toString()}`);
      setProducts(response.items);
      setTotal(response.total);
    } catch (err: any) {
      setError(err.message || '상품 목록을 불러오는 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, [page, size, searchDebounced, statusFilter, importFilter, wholesaleFilter, needsSyncFilter, sortMode]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  // API deletion handler
  const handleDeleteProducts = useCallback(async (force = false) => {
    if (!deleteConfig) return;
    setIsDeleting(true);
    setDeleteError(null);

    try {
      const payload = {
        product_ids: deleteConfig.mode === 'selected' ? Array.from(selectedIds) : null,
        wholesale_site_id: deleteConfig.mode === 'wholesale' ? deleteConfig.wholesaleSiteId : null,
        force: force
      };

      const response = await api.post<{
        success: boolean;
        deleted_count: number;
        warning_synced_count: number;
        message: string;
      }>('/api/processor/products/delete', payload);

      if (response.success) {
        setDeleteModalOpen(false);
        setDeleteConfig(null);
        setWarningSyncedCount(0);
        setSelectedIds(new Set());
        setPage(1); // Go back to page 1 to load updated products
        fetchProducts();
      } else {
        setWarningSyncedCount(response.warning_synced_count);
      }
    } catch (err: any) {
      setDeleteError(err.message || '상품 삭제를 처리하는 중 예외가 발생했습니다.');
    } finally {
      setIsDeleting(false);
    }
  }, [deleteConfig, selectedIds, fetchProducts]);

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
        credentials: 'include',
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
  const visibleColumnCount = columnOrder.filter(
    (key) => key !== 'checkbox' && columnVisibility[key] !== false
  ).length;
  const matchedSite = wholesaleSites.find(s => s.id === wholesaleFilter);
  const formatPrice = (value?: number | null) =>
    typeof value === 'number' ? `${value.toLocaleString('ko-KR')}원` : '-';
  const renderStandardOptions = (product: Product) => {
    if (!product.standard_options || product.standard_options.length === 0) {
      return <span className={styles.emptyInline}>옵션 없음</span>;
    }

    const first = product.standard_options[0];
    const firstLabel = first.option_display_name || first.option_sku || '-';

    return (
      <div className={styles.standardOptionPreview}>
        {first.option_main_image_url ? (
          <img src={first.option_main_image_url} alt="" className={styles.standardOptionImage} />
        ) : null}
        <div className={styles.standardOptionText}>
          <span className={styles.optionCount}>옵션 {product.standard_options.length}개</span>
          <span>{firstLabel}</span>
          <span>{formatPrice(first.option_supply_price)}</span>
        </div>
      </div>
    );
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Catalog Operations</p>
          <h1 className={styles.title}>상품 관리</h1>
        </div>
        <div className={styles.actionGroup}>
          {wholesaleFilter && (
            <button 
              className={styles.deleteWholesaleBtn}
              onClick={() => {
                setDeleteConfig({
                  mode: 'wholesale',
                  count: total,
                  wholesaleSiteId: wholesaleFilter
                });
                setWarningSyncedCount(0);
                setDeleteError(null);
                setDeleteModalOpen(true);
              }}
              type="button"
            >
              &quot;{matchedSite?.name || '도매처'}&quot; 상품 전체 삭제
            </button>
          )}
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
            placeholder="기존 상품명으로 검색..."
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

        <div className={styles.selectGroup}>
          <span className={styles.selectLabel}>정렬</span>
          <select
            value={sortMode}
            onChange={(e) => { setSortMode(e.target.value); setPage(1); }}
            className={styles.select}
          >
            <option value="">기본순</option>
            <option value="option_count_desc">옵션 많은 순</option>
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

        {/* Column Settings Button & Popover */}
        <div className={styles.columnSettingsContainer} id="column-settings-container">
          <button
            className={`${styles.columnSettingsButton} ${showSettings ? styles.columnSettingsButtonActive : ''}`}
            onClick={() => setShowSettings(!showSettings)}
            type="button"
            aria-expanded={showSettings}
            aria-haspopup="dialog"
            aria-controls="column-settings-popover"
          >
            <svg className={styles.settingsIcon} viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 7h10m4 0h2M14 4v6M4 17h3m4 0h9M10 14v6" />
            </svg>
            <span>표시 항목</span>
            <span className={styles.visibleColumnCount}>{visibleColumnCount}</span>
            <svg className={styles.settingsChevron} viewBox="0 0 20 20" aria-hidden="true">
              <path d="m6 8 4 4 4-4" />
            </svg>
          </button>
          {showSettings && (
            <div
              id="column-settings-popover"
              className={styles.columnSettingsPopover}
              role="dialog"
              aria-label="표시할 열 선택"
            >
              <div className={styles.popoverHeader}>
                <div>
                  <strong>표시 항목</strong>
                  <span>필요한 열만 선택하세요</span>
                </div>
                <span>{visibleColumnCount}/{columnOrder.length - 1}</span>
              </div>
              <div className={styles.popoverList}>
                {columnOrder.map((colKey) => {
                  if (colKey === 'checkbox') return null;
                  return (
                    <label key={colKey} className={styles.popoverItem}>
                      <input 
                        type="checkbox"
                        checked={columnVisibility[colKey] !== false}
                        onChange={() => toggleColumnVisibility(colKey)}
                      />
                      {COLUMNS_REGISTRY[colKey]}
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Products Table Section */}
      <div className={styles.tableSection}>
        {selectedIds.size > 0 && (
          <div className={styles.selectionToolbar}>
            <div className={styles.selectionSummary} aria-live="polite">
              <span className={styles.selectionIcon} aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="m6 12 4 4 8-9" />
                </svg>
              </span>
              <div className={styles.selectionCopy}>
                <strong>{selectedIds.size}개 상품 선택됨</strong>
                <span>선택한 상품을 일괄 관리합니다</span>
              </div>
            </div>
            <div className={styles.selectionActions}>
              <button
                className={styles.clearSelectionButton}
                onClick={() => setSelectedIds(new Set())}
                type="button"
              >
                선택 해제
              </button>
              <button
                className={styles.deleteSelectedBtn}
                onClick={() => {
                  setDeleteConfig({ mode: 'selected', count: selectedIds.size });
                  setWarningSyncedCount(0);
                  setDeleteError(null);
                  setDeleteModalOpen(true);
                }}
                type="button"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
                </svg>
                선택 삭제
              </button>
            </div>
          </div>
        )}
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
                  {columnOrder.map((colKey) => {
                    const isVisible = columnVisibility[colKey] !== false;
                    if (!isVisible) return null;

                    if (colKey === 'checkbox') {
                      return (
                        <th key="checkbox" className={styles.checkboxCol}>
                          <input 
                            type="checkbox" 
                            checked={isAllSelected}
                            onChange={handleSelectAll}
                            className={styles.checkbox}
                          />
                        </th>
                      );
                    }

                    const label = COLUMNS_REGISTRY[colKey];
                    const isDragging = draggedColKey === colKey;
                    const isDragOver = dragOverColKey === colKey;

                    let thClassName = styles.thDraggable;
                    if (isDragging) {
                      thClassName += ` ${styles.thDragging}`;
                    }
                    if (isDragOver) {
                      if (dragDirection === 'left') {
                        thClassName += ` ${styles.dragIndicatorLeft}`;
                      } else if (dragDirection === 'right') {
                        thClassName += ` ${styles.dragIndicatorRight}`;
                      }
                    }

                    return (
                      <th
                        key={colKey}
                        data-column={colKey}
                        className={thClassName}
                        draggable
                        onDragStart={(e) => handleDragStart(e, colKey)}
                        onDragOver={(e) => handleDragOver(e, colKey)}
                        onDrop={(e) => handleDrop(e, colKey)}
                        onDragEnd={handleDragEnd}
                      >
                        {label}
                      </th>
                    );
                  })}
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
                      {columnOrder.map((colKey) => {
                        const isVisible = columnVisibility[colKey] !== false;
                        if (!isVisible) return null;

                        switch (colKey) {
                          case 'checkbox':
                            return (
                              <td key="checkbox" className={styles.checkboxCol}>
                                <input 
                                  type="checkbox"
                                  checked={selectedIds.has(p.id)}
                                  onChange={(e) => handleSelectOne(p.id, e.target.checked)}
                                  className={styles.checkbox}
                                />
                              </td>
                            );

                          case 'main_image': {
                            // images_list[0] 검출 또는 raw_metadata의 이미지 주소 검출
                            let imgSrc = '';
                            if (p.images_list && p.images_list.length > 0) {
                              imgSrc = p.images_list[0];
                            } else if (p.raw_metadata) {
                              imgSrc = p.raw_metadata['목록이미지1'] || p.raw_metadata['목록이미지'] || '';
                            }
                            return (
                              <td key={colKey}>
                                {imgSrc ? (
                                  <img src={imgSrc} className={styles.tableThumbnail} alt="Product Thumb" />
                                ) : (
                                  <span className={styles.emptyInline}>이미지 없음</span>
                                )}
                              </td>
                            );
                          }

                          case 'refined_name':
                            return (
                              <td key="refined_name">
                                <div className={styles.nameWrapper}>
                                  <span className={styles.refName} title={p.refined_name || '가공 전'}>
                                    {p.refined_name ? p.refined_name : <span className={styles.refNameEmpty}>가공 전</span>}
                                  </span>
                                  {(p.change_type || priceChanged || stockChanged) && (
                                    <span className={styles.nameBadges}>
                                      {p.change_type && (
                                        <span
                                          className={`${styles.sourceChangeBadge} ${p.change_type === 'new' ? styles.sourceChangeNew : styles.sourceChangeUpdated}`}
                                          title={p.change_type === 'updated' && p.changed_fields?.length
                                            ? `변경 항목: ${p.changed_fields.join(', ')}`
                                            : '새 도매처 상품'}
                                        >
                                          {p.change_type === 'new' ? '신상품' : '변동'}
                                        </span>
                                      )}
                                      {priceChanged && <span className={styles.changeBadgeOrange}>가격 변동</span>}
                                      {stockChanged && <span className={styles.changeBadgeRed}>품절 변동</span>}
                                    </span>
                                  )}
                                  <span className={styles.origName} title={p.original_name}>{p.original_name}</span>
                                  {p.brand_name && <span className={styles.nameMeta}>{p.brand_name}</span>}
                                </div>
                              </td>
                            );

                          case 'original_name':
                            return (
                              <td key="original_name">
                                <span className={styles.origName}>{p.original_name}</span>
                              </td>
                            );

                          case 'brand_name': {
                            return (
                              <td key={colKey}>
                                {p.brand_name || <span className={styles.emptyInline}>-</span>}
                              </td>
                            );
                          }

                          case 'keywords':
                            return (
                              <td key="keywords">
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
                              <td key="option_variants">
                                {p.standard_options && p.standard_options.length > 0 ? (
                                  renderStandardOptions(p)
                                ) : p.option_variants && p.option_variants.length > 0 ? (
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
                                ) : (
                                  <span className={styles.emptyInline}>옵션 없음</span>
                                )}
                              </td>
                            );

                          case 'option_values_raw': {
                            return (
                              <td key={colKey}>
                                {p.option_values_raw ? (
                                  <span title={p.option_values_raw} style={{ cursor: 'help' }}>
                                    {p.option_values_raw}
                                  </span>
                                ) : (
                                  <span className={styles.emptyInline}>-</span>
                                )}
                              </td>
                            );
                          }

                          case 'platform_mappings':
                            return (
                              <td key="platform_mappings">
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

                          case 'mapped_attributes': {
                            const naver = p.platform_mappings.find((m) => m.platform_name === 'naver');
                            const coupang = p.platform_mappings.find((m) => m.platform_name === 'coupang');
                            
                            const hasNaverAttrs = naver?.mapped_attributes && Object.keys(naver.mapped_attributes).length > 0;
                            // 쿠팡 속성은 product_attributes 또는 item_attributes 검출
                            const hasCoupangAttrs = coupang?.mapped_attributes && 
                              (coupang.mapped_attributes.product_attributes?.length > 0 || 
                               coupang.mapped_attributes.item_attributes?.length > 0);
                               
                            return (
                              <td key={colKey}>
                                <div className={styles.attributeGroup}>
                                  {hasNaverAttrs && (
                                    <div>
                                      <div className={styles.platformAttrTitle}>Naver</div>
                                      {Object.entries(naver.mapped_attributes).map(([k, v]) => (
                                        <span key={k} className={styles.attributeTag}>{k}: {String(v)}</span>
                                      ))}
                                    </div>
                                  )}
                                  {hasCoupangAttrs && (
                                    <div>
                                      <div className={styles.platformAttrTitle}>Coupang</div>
                                      {coupang.mapped_attributes.product_attributes?.slice(0, 4).map((attr: any, i: number) => (
                                        <span key={i} className={styles.attributeTag}>
                                          {attr.attributeTypeName}: {attr.attributeValueName}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                  {!hasNaverAttrs && !hasCoupangAttrs && (
                                    <span className={styles.emptyInline}>가공된 속성 없음</span>
                                  )}
                                </div>
                              </td>
                            );
                          }

                          case 'warnings': {
                            const productWarnings = Array.isArray(p.warnings)
                              ? p.warnings
                              : Array.isArray(p.warnings?.warnings)
                                ? p.warnings.warnings
                                : [
                                    ...(Array.isArray(p.warnings?.supplier_warnings) ? p.warnings.supplier_warnings : []),
                                    ...(Array.isArray(p.warnings?.processing_warnings) ? p.warnings.processing_warnings : [])
                                  ];
                            const warningCount = productWarnings.length;
                            const tooltipId = `warning-tooltip-${p.id}`;
                            return (
                              <td key={colKey}>
                                {warningCount > 0 ? (
                                  <div className={styles.warningTooltip}>
                                    <button
                                      className={styles.warningPill}
                                      type="button"
                                      aria-describedby={tooltipId}
                                    >
                                      <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M12 9v4m0 4h.01M10.3 4.6 2.7 18a1.5 1.5 0 0 0 1.3 2.2h16a1.5 1.5 0 0 0 1.3-2.2L13.7 4.6a2 2 0 0 0-3.4 0Z" />
                                      </svg>
                                      경고 {warningCount}건
                                    </button>
                                    <div id={tooltipId} className={styles.warningPanel} role="tooltip">
                                      <div className={styles.warningPanelHeader}>
                                        <div>
                                          <strong>확인이 필요한 항목</strong>
                                          <span>상품 정보를 다시 확인해 주세요</span>
                                        </div>
                                        <span className={styles.warningCountBadge}>{warningCount}</span>
                                      </div>
                                      <ul className={styles.warningList}>
                                        {productWarnings.map((warning: any, index: number) => {
                                          const title = warning?.keyword
                                            ? `키워드 · ${warning.keyword}`
                                            : WARNING_FIELD_LABELS[warning?.field] || COLUMNS_REGISTRY[warning?.field] || '상품 정보';
                                          const rawMessage = warning?.message || warning?.reason;
                                          const message = WARNING_MESSAGE_LABELS[rawMessage] || rawMessage || String(warning);
                                          return (
                                            <li key={index} className={styles.warningItem}>
                                              <span className={styles.warningDot} />
                                              <div>
                                                <strong>{title}</strong>
                                                <span>{message}</span>
                                                {warning?.raw_value != null && (
                                                  <code>입력값: {String(warning.raw_value)}</code>
                                                )}
                                                {warning?.option_count != null && warning?.price_count != null && (
                                                  <small>옵션 {warning.option_count}개 · 가격 {warning.price_count}개</small>
                                                )}
                                              </div>
                                            </li>
                                          );
                                        })}
                                      </ul>
                                    </div>
                                  </div>
                                ) : (
                                  <span className={styles.emptyInline}>경고 없음</span>
                                )}
                              </td>
                            );
                          }

                          case 'status':
                            return (
                              <td key="status">
                                <span className={`${styles.statusPill} ${styles[p.status]}`}>
                                  {p.status === 'completed' && '완료'}
                                  {p.status === 'processing' && '가공 중'}
                                  {p.status === 'pending' && '대기'}
                                  {p.status === 'failed' && '실패'}
                                </span>
                              </td>
                            );

                          case 'raw_metadata': {
                            return (
                              <td key={colKey}>
                                <details className={styles.rawMetaDetails}>
                                  <summary className={styles.rawMetaSummary}>🔍 원본 보기</summary>
                                  <div className={styles.rawMetaContent}>
                                    {p.raw_metadata && Object.keys(p.raw_metadata).length > 0 ? (
                                      Object.entries(p.raw_metadata).map(([k, v]) => (
                                        <div key={k} className={styles.rawMetaLine}>
                                          <strong className={styles.rawMetaKey}>{k}:</strong>
                                          <span className={styles.rawMetaVal}>{String(v)}</span>
                                        </div>
                                      ))
                                    ) : (
                                      <div className={styles.emptyInline}>원본 정보 없음</div>
                                    )}
                                  </div>
                                </details>
                              </td>
                            );
                          }

                          case 'image_detail': {
                            //상세페이지 HTML에서 이미지 추출 또는 원본 텍스트 주소 검출
                            let detailUrl = '';
                            if (p.image_detail) {
                              if (p.image_detail.startsWith('http')) {
                                detailUrl = p.image_detail;
                              } else {
                                // HTML에서 첫 img tag의 src 추출 시도
                                const match = p.image_detail.match(/src=["'](https?:\/\/[^"']+)["']/i);
                                if (match) {
                                  detailUrl = match[1];
                                }
                              }
                            } else if (p.raw_metadata) {
                              detailUrl = p.raw_metadata['상세이미지'] || '';
                              if (detailUrl && !detailUrl.startsWith('http')) {
                                const match = detailUrl.match(/src=["'](https?:\/\/[^"']+)["']/i);
                                if (match) {
                                  detailUrl = match[1];
                                }
                              }
                            }
                            return (
                              <td key={colKey}>
                                {detailUrl ? (
                                  <a 
                                    href={detailUrl} 
                                    target="_blank" 
                                    rel="noopener noreferrer" 
                                    className={styles.detailLinkBtn}
                                  >
                                    🔗 상세 이미지 보기
                                  </a>
                                ) : (
                                  <span className={styles.emptyInline}>URL 없음</span>
                                )}
                              </td>
                            );
                          }

                          case 'created_at':
                            return (
                              <td key="created_at" className={styles.dateCell}>
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
                              <td key="product_code">
                                {p.product_code || <span className={styles.emptyInline}>-</span>}
                              </td>
                            );

                          case 'wholesale_product_id':
                            return (
                              <td key="wholesale_product_id">
                                {p.wholesale_product_id || <span className={styles.emptyInline}>-</span>}
                              </td>
                            );

                          case 'price_wholesale':
                            return (
                              <td key="price_wholesale">
                                {formatPrice(p.price_wholesale)}
                              </td>
                            );

                          case 'price_retail':
                            return (
                              <td key="price_retail">
                                {formatPrice(p.price_retail)}
                              </td>
                            );

                          case 'price_min_selling':
                            return (
                              <td key="price_min_selling">
                                {formatPrice(p.price_min_selling)}
                              </td>
                            );

                          case 'origin':
                            return (
                              <td key="origin">
                                {p.origin || <span className={styles.emptyInline}>-</span>}
                              </td>
                            );

                          case 'wholesale_status':
                            return (
                              <td key="wholesale_status">
                                {p.wholesale_status ? (
                                  <span>{p.wholesale_status}</span>
                                ) : (
                                  <span className={styles.emptyInline}>-</span>
                                )}
                              </td>
                            );

                          case 'wholesale_registered_at':
                            return (
                              <td key="wholesale_registered_at" className={styles.dateCell}>
                                {p.wholesale_registered_at ? (
                                  new Date(p.wholesale_registered_at).toLocaleString('ko-KR', {
                                    month: 'numeric',
                                    day: 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                  })
                                ) : (
                                  <span className={styles.emptyInline}>-</span>
                                )}
                              </td>
                            );

                          default:
                            return null;
                        }
                      })}
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

      <DeleteConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => {
          if (!isDeleting) {
            setDeleteModalOpen(false);
            setDeleteConfig(null);
          }
        }}
        onConfirm={handleDeleteProducts}
        count={deleteConfig?.count || 0}
        warningSyncedCount={warningSyncedCount}
        isDeleting={isDeleting}
        error={deleteError}
      />
    </div>
  );
}
