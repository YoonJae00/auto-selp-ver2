'use client';

import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import { useSettingsStore } from '@/store/settingsStore';
import { useTaskStore } from '@/store/taskStore';
import PillButton from '@/components/UI/PillButton/PillButton';
import TrademarkModal from './TrademarkModal';
import styles from './process.module.css';

type Step = 'UPLOAD' | 'MAPPING' | 'PROCESSING' | 'COMPLETED';

interface UploadResponse {
  file_id: string;
  filename: string;
  columns: string[];
  preview: any[];
}

export default function ProcessPage() {
  const [step, setStep] = useState<Step>('UPLOAD');
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);
  
  // Use Global Settings
  const { llmProvider, columnMapping, setColumnMapping, kiprisEnabled } = useSettingsStore();
  
  // Use Global Task Store
  const { tasks, addTask } = useTaskStore();
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const activeTask = tasks.find(t => t.id === activeTaskId);

  const [error, setError] = useState<string | null>(null);
  const [showWarnings, setShowWarnings] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Recovery logic on mount: if there's a running task, jump to processing step
  useEffect(() => {
    if (step === 'UPLOAD') {
      const runningTask = tasks.find(t => t.status === 'PENDING' || t.status === 'PROGRESS');
      if (runningTask) {
        setActiveTaskId(runningTask.id);
        setStep('PROCESSING');
      }
    }
  }, [tasks, step]);

  // Sync local step with task status
  useEffect(() => {
    if (activeTask?.status === 'SUCCESS') {
      setStep('COMPLETED');
    } else if (activeTask?.status === 'FAILURE') {
      setError('Processing failed.');
      setStep('MAPPING');
      setActiveTaskId(null);
    }
  }, [activeTask?.status]);

  // 1. Upload
  const [isDragging, setIsDragging] = useState(false);

  const handleFileUpload = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    setError(null);
    try {
      const data = await api.post<UploadResponse>('/api/processor/upload', formData);
      
      setUploadData(data);
      
      // 기존에 저장된 매핑값이 업로드된 파일의 컬럼에 존재하는지 확인하고, 
      // 없으면 자동 선택 로직 수행 (원본 상품명 한정)
      if (!data.columns.includes(columnMapping.original_name)) {
        const autoPick = data.columns.find((c: string) => c.includes('상품명')) || data.columns[0];
        setColumnMapping({ original_name: autoPick });
      }
      
      setStep('MAPPING');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  };

  // 2. Start Process
  const handleStartProcess = async () => {
    if (!uploadData) return;
    setError(null);
    try {
      const res = await api.post<{ task_id: string }>('/api/processor/process', {
        file_id: uploadData.file_id,
        column_mapping: columnMapping,
        llm_provider: llmProvider,
        kipris_enabled: kiprisEnabled
      });
      
      addTask({
        id: res.task_id,
        filename: uploadData.filename,
        progress: 0,
        status: 'PENDING',
        startTime: Date.now()
      });
      
      setActiveTaskId(res.task_id);
      setStep('PROCESSING');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDownload = () => {
    if (!activeTaskId) return;
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost'}/api/processor/download/${activeTaskId}`;
  };

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>상품 가공</h1>

      {error && <div className={styles.error}>{error}</div>}

      {step === 'UPLOAD' && (
        <section className={styles.section}>
          <div 
            className={isDragging ? `${styles.uploadArea} ${styles.dragging}` : styles.uploadArea} 
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
          >
            <span className={styles.uploadIcon}>📄</span>
            <h3>엑셀 파일을 업로드하세요</h3>
            <p>클릭하여 파일을 선택하거나 여기로 드래그하세요.</p>
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              accept=".xlsx,.xls"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
              }}
            />
          </div>
        </section>
      )}

      {step === 'MAPPING' && uploadData && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>컬럼 매핑 및 설정</h3>
          <p className={styles.sectionDesc}>가공 결과가 저장될 열을 선택해 주세요.</p>
          
          <div className={styles.mappingGrid}>
            <div className={styles.formGroup}>
              <label className={styles.label}>원본 상품명 열</label>
              <select 
                className={styles.select}
                value={columnMapping.original_name}
                onChange={(e) => setColumnMapping({ original_name: e.target.value })}
              >
                {uploadData.columns.map(col => <option key={col} value={col}>{col}</option>)}
              </select>
            </div>
            
            <div className={styles.formGroup}>
              <label className={styles.label}>정제 상품명 저장 열</label>
              <select 
                className={styles.select}
                value={columnMapping.refined_name}
                onChange={(e) => setColumnMapping({ refined_name: e.target.value })}
              >
                <option value="">-- 선택 안함 --</option>
                {uploadData.columns.map(col => <option key={col} value={col}>{col}</option>)}
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>키워드 저장 열</label>
              <select 
                className={styles.select}
                value={columnMapping.keywords}
                onChange={(e) => setColumnMapping({ keywords: e.target.value })}
              >
                <option value="">-- 선택 안함 --</option>
                {uploadData.columns.map(col => <option key={col} value={col}>{col}</option>)}
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>네이버 카테고리 저장 열</label>
              <select 
                className={styles.select}
                value={columnMapping.naver_category}
                onChange={(e) => setColumnMapping({ naver_category: e.target.value })}
              >
                <option value="">-- 선택 안함 --</option>
                {uploadData.columns.map(col => <option key={col} value={col}>{col}</option>)}
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>쿠팡 카테고리 저장 열</label>
              <select 
                className={styles.select}
                value={columnMapping.coupang_category}
                onChange={(e) => setColumnMapping({ coupang_category: e.target.value })}
              >
                <option value="">-- 선택 안함 --</option>
                {uploadData.columns.map(col => <option key={col} value={col}>{col}</option>)}
              </select>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>현재 엔진</label>
              <div className={styles.engineBadge}>
                {llmProvider === 'gemini' ? 'Gemini 3.1 Flash-Lite' : 'gpt-5.4-nano'}
              </div>
            </div>
          </div>

          <h4 className={styles.previewTitle}>데이터 미리보기 (상위 5개)</h4>
          <div className={styles.tableWrapper}>
            <table className={styles.previewTable}>
              <thead>
                <tr>
                  {uploadData.columns.map(col => <th key={col}>{col}</th>)}
                </tr>
              </thead>
              <tbody>
                {uploadData.preview.map((row, i) => (
                  <tr key={i}>
                    {uploadData.columns.map(col => <td key={col}>{row[col]}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: '32px', textAlign: 'right' }}>
            <PillButton onClick={handleStartProcess}>가공 시작하기</PillButton>
          </div>
        </section>
      )}

      {(step === 'PROCESSING' || step === 'COMPLETED') && (
        <section className={styles.section}>
          <div className={styles.progressContainer}>
            <div className={styles.statusText}>
              {step === 'PROCESSING' ? `상품을 가공하고 있습니다... (${activeTask?.progress || 0}%)` : '가공이 완료되었습니다!'}
            </div>

            {step === 'COMPLETED' && activeTask?.warnings && Object.keys(activeTask.warnings).length > 0 && (
              <div className={styles.warningSummary}>
                <div className={styles.warningText}>
                  <span className={styles.warningIcon}>⚠️</span>
                  <span>상표권 침해 의심 키워드가 {Object.values(activeTask.warnings).flat().length}개 발견되었습니다.</span>
                </div>
                <PillButton variant="secondary" onClick={() => setShowWarnings(true)}>상세보기</PillButton>
              </div>
            )}

            <div className={styles.progressBar}>
              <div className={styles.progressFill} style={{ width: `${activeTask?.progress || 0}%` }}></div>
            </div>
            {step === 'COMPLETED' && (
              <PillButton variant="primary" onClick={handleDownload}>결과 파일 다운로드</PillButton>
            )}
          </div>
        </section>
      )}

      {showWarnings && activeTask?.warnings && (
        <TrademarkModal 
          warnings={activeTask.warnings} 
          onClose={() => setShowWarnings(false)} 
        />
      )}
    </div>
  );
}
