'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from './upload.module.css';

interface WholesaleSite {
  id: string;
  name: string;
  homepage_url: string | null;
  column_mapping: Record<string, string> | null;
}

interface UploadResponse {
  file_id: string;
  filename: string;
  columns: string[];
  preview: any[];
}

const SYSTEM_FIELD_GROUPS = [
  {
    title: '필수 상품 필드',
    fields: [
      { key: 'wholesale_status', label: '판매 상태 (필수)', required: true, standardKey: 'wholesale_status', defaultFallbacks: ['상태', '품절상태', '품절여부', '판매상태'] },
      { key: 'wholesale_product_id', label: '도매처 상품 번호 (필수)', required: true, standardKey: 'wholesale_product_id', defaultFallbacks: ['제품번호', '제품id', '상품id'] },
      { key: 'product_code', label: '도매처 상품 코드 (필수)', required: true, standardKey: 'product_code', defaultFallbacks: ['상품코드', '도매코드', '자체상품코드', '코드'] },
      { key: 'original_name', label: '원본 상품명 (필수)', required: true, standardKey: 'original_name', defaultFallbacks: ['상품명', '원본상품명', '제품명'] },
      { key: 'origin', label: '원산지 (필수)', required: true, standardKey: 'origin', defaultFallbacks: ['원산지', '제조국', '제조국가'] },
      { key: 'price_wholesale_raw', label: '기본 공급가 (필수)', required: true, standardKey: 'price_wholesale_raw', defaultFallbacks: ['공급가', '도매가', '공급가격', '도매가격', '가격'] },
      { key: 'image_list_1', label: '대표 이미지 (필수)', required: true, standardKey: 'image_list_1', defaultFallbacks: ['목록이미지1', '대표이미지', '상품이미지', '이미지'] },
      { key: 'image_detail', label: '상세 설명 이미지 (필수)', required: true, standardKey: 'image_detail', defaultFallbacks: ['상세이미지', '상세설명이미지'] }
    ]
  },
  {
    title: '선택 상품 필드',
    fields: [
      { key: 'price_retail', label: '권장 소비자가', required: false, standardKey: 'price_retail', defaultFallbacks: ['소비자가', '소매가', '소매가격'] },
      { key: 'price_min_selling', label: '최소 판매가', required: false, standardKey: 'price_min_selling', defaultFallbacks: ['판매준수가', '최소판매가', '최저가'] },
      { key: 'image_list_2', label: '추가 이미지 2', required: false, standardKey: 'image_list_2', defaultFallbacks: ['목록이미지2'] },
      { key: 'image_list_3', label: '추가 이미지 3', required: false, standardKey: 'image_list_3', defaultFallbacks: ['목록이미지3'] },
      { key: 'image_list_4', label: '추가 이미지 4', required: false, standardKey: 'image_list_4', defaultFallbacks: ['목록이미지4'] },
      { key: 'image_list_5', label: '추가 이미지 5', required: false, standardKey: 'image_list_5', defaultFallbacks: ['목록이미지5'] },
      { key: 'wholesale_registered_at', label: '도매처 등록일', required: false, standardKey: 'wholesale_registered_at', defaultFallbacks: ['등록일', '상품등록일'] }
    ]
  },
  {
    title: '옵션 필드',
    fields: [
      { key: 'option_values_raw', label: '옵션 값 목록', required: false, standardKey: 'option_values_raw', defaultFallbacks: ['옵션값', '옵션', '선택사항', '옵션명'] },
      { key: 'option_image_urls_raw', label: '옵션별 이미지 URL', required: false, standardKey: 'option_image_urls_raw', defaultFallbacks: ['옵션이미지', '옵션 이미지', '옵션이미지url', '옵션이미지주소'] }
    ]
  }
] as const;

const SYSTEM_FIELDS = SYSTEM_FIELD_GROUPS.flatMap(group => group.fields);

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

export default function UploadPage() {
  const [wholesaleSites, setWholesaleSites] = useState<WholesaleSite[]>([]);
  const [activeSite, setActiveSite] = useState<WholesaleSite | null>(null);
  
  // Modals & Forms
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newUrl, setNewUrl] = useState('');
  
  // File Uploading & Mapping States
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(true); // Added for accordion toggle
  
  // Feedback
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch Wholesale Sites
  const fetchSites = useCallback(async () => {
    try {
      const data = await api.get<WholesaleSite[]>('/api/processor/wholesale-sites');
      setWholesaleSites(data);
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

  // Update activeSite's column mapping when it changes
  useEffect(() => {
    if (activeSite) {
      setColumnMapping(activeSite.column_mapping || {});
    } else {
      setColumnMapping({});
    }
  }, [activeSite]);

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
    
    try {
      const data = await api.post<UploadResponse>('/api/processor/upload', formData);
      setUploadData(data);
      
      // Perform smart fallback auto-matching on uploaded columns
      const nextMapping = { ...columnMapping };
      SYSTEM_FIELDS.forEach(field => {
        // If not already mapped to an existing column in the excel
        if (!nextMapping[field.key] || !data.columns.includes(nextMapping[field.key])) {
          const matched = findBestColumnMatch(field, data.columns);
          if (matched) {
            nextMapping[field.key] = matched;
          } else if (field.required) {
            nextMapping[field.key] = data.columns[0];
          }
        }
      });
      setColumnMapping(nextMapping);
      
    } catch (err: any) {
      setError(err.message || '엑셀 파일 해석에 실패했습니다.');
    } finally {
      setIsUploading(false);
    }
  };

  // Save Column Template mapping to WholesaleSite
  const handleSaveTemplate = async () => {
    if (!activeSite) return;
    setError(null);
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

  // Store uploaded supplier products in DB without product processing.
  const handleSaveProductsToDb = async () => {
    if (!activeSite || !uploadData) return;
    
    // Validate required fields
    const missing = SYSTEM_FIELDS.filter(f => f.required && !columnMapping[f.key]);
    if (missing.length > 0) {
      setError(`필수 매핑 컬럼이 설정되지 않았습니다: ${missing.map(m => m.label).join(', ')}`);
      return;
    }
    
    setError(null);
    setIsProcessing(true);
    try {
      const res = await api.post<{ task_id: string | null; import_id: string; total: number }>('/api/processor/process-db', {
        file_id: uploadData.file_id,
        column_mapping: columnMapping,
        wholesale_site_id: activeSite.id,
        llm_provider: 'gemini',
        kipris_enabled: true,
        start_processing: false
      });
      
      setSuccess(`${res.total}개의 상품을 DB에 저장했습니다. 상품 가공 화면에서 도매처와 상품을 선택해 가공할 수 있습니다.`);
      // Clear file upload state
      setUploadData(null);
    } catch (err: any) {
      setError(err.message || '상품 DB 저장 중 오류가 발생했습니다.');
    } finally {
      setIsProcessing(false);
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

      {error && <div className={styles.error}>{error}</div>}
      {success && <div className={styles.success}>{success}</div>}

      {/* Grid of wholesale sites */}
      <div className={styles.sitesGrid}>
        {wholesaleSites.map((site) => {
          const isSelected = activeSite?.id === site.id;
          const mappedCount = Object.keys(site.column_mapping || {}).length;
          
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
                <span className={`${styles.mappingBadge} ${mappedCount === 0 ? styles.mappingBadgeEmpty : ''}`}>
                  {mappedCount > 0 ? `🔗 ${mappedCount}개 항목 매핑됨` : '⚠️ 템플릿 미설정'}
                </span>
              </div>
              <div className={styles.cardActions}>
                <button 
                  type="button" 
                  className={styles.deleteBtn}
                  onClick={(e) => handleDeleteSite(site.id, e)}
                >
                  삭제
                </button>
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
            <h3>{isUploading ? '업로드 해석 중...' : '엑셀 파일을 업로드해 주세요'}</h3>
            <p>클릭하거나 여기로 파일을 드래그합니다 (.xlsx, .xls)</p>
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }}
              accept=".xlsx,.xls"
              onChange={handleFileSelect}
              disabled={isUploading}
            />
          </div>

          {/* Visual Column Mapper */}
          {uploadData && (
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

              <div className={styles.sectionHeader}>
                <h2>Visual Column Mapper (컬럼 매핑 대입)</h2>
                <p>도매처 엑셀 열 항목과 시스템의 표준 저장 필드를 시각적으로 연결합니다. 처음 한번만 설정하면 저장되어 계속 재사용 가능합니다.</p>
              </div>

              {SYSTEM_FIELD_GROUPS.map((group) => (
                <div key={group.title} className={styles.mapperGroup}>
                  <h3 className={styles.mapperGroupTitle}>{group.title}</h3>
                  <div className={styles.mapperGrid}>
                    {group.fields.map((field) => {
                      return (
                        <div key={field.key} className={styles.mappingField}>
                          <span className={styles.fieldLabel}>{field.label}</span>
                          <select
                            className={styles.select}
                            value={columnMapping[field.key] || ''}
                            onChange={(e) => setColumnMapping({
                              ...columnMapping,
                              [field.key]: e.target.value
                            })}
                          >
                            <option value="">-- 선택 안함 --</option>
                            {uploadData.columns.map(col => (
                              <option key={col} value={col}>{col}</option>
                            ))}
                          </select>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              <div className={styles.mapperActions}>
                <PillButton 
                  variant="secondary"
                  onClick={handleSaveTemplate}
                  type="button"
                >
                  💾 도매처 템플릿 저장
                </PillButton>
                <PillButton 
                  variant="primary"
                  onClick={handleSaveProductsToDb}
                  disabled={isProcessing}
                  type="button"
                >
                  {isProcessing ? 'DB 저장 중...' : 'DB에 상품 저장'}
                </PillButton>
              </div>
            </div>
          )}
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
