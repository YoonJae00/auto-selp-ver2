'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import styles from './accounts.module.css';

type MarketCode = 'smartstore' | 'coupang';

interface MarketplaceAccount {
  id: string;
  market_code: MarketCode;
  display_name: string;
  connection_status?: string;
  is_primary?: boolean;
}

interface MarketplaceSettings {
  settings_schema_version?: string;
  connection_config?: Record<string, unknown> | null;
  fulfillment_config?: Record<string, unknown> | null;
  claim_config?: Record<string, unknown> | null;
  listing_defaults?: Record<string, unknown> | null;
  generation_rules?: Record<string, unknown> | null;
}

const MARKET_TABS: MarketCode[] = ['smartstore', 'coupang'];

const marketLabel = (value: MarketCode) => (value === 'smartstore' ? 'Smart Store' : 'Coupang');

export default function MarketplaceAccountsPage() {
  const [accounts, setAccounts] = useState<MarketplaceAccount[]>([]);
  const [activeTab, setActiveTab] = useState<MarketCode>('smartstore');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newDisplayName, setNewDisplayName] = useState('');
  const [credentialsText, setCredentialsText] = useState('{\n  "client_id": "",\n  "client_secret": ""\n}');
  const [settingsText, setSettingsText] = useState('{}');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAccounts = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.get<MarketplaceAccount[]>('/api/marketplace/accounts');
      setAccounts(data);
    } catch (err: any) {
      setError(err.message || '계정 목록을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  const tabAccounts = useMemo(
    () => accounts.filter((account) => account.market_code === activeTab),
    [accounts, activeTab],
  );

  useEffect(() => {
    if (tabAccounts.length > 0) {
      const next = tabAccounts[0];
      setSelectedId(next.id);
    } else {
      setSelectedId(null);
      setSettingsText('{}');
    }
  }, [activeTab, tabAccounts]);

  const selectedAccount = tabAccounts.find((account) => account.id === selectedId) || null;

  useEffect(() => {
    if (!selectedAccount) return;

    let cancelled = false;
    const loadSettings = async () => {
      try {
        const data = await api.get<MarketplaceSettings>(`/api/marketplace/accounts/${selectedAccount.id}/settings`);
        if (!cancelled) setSettingsText(JSON.stringify(data, null, 2));
      } catch {
        if (!cancelled) {
          setSettingsText(JSON.stringify({
            settings_schema_version: 'v1',
            connection_config: {},
            fulfillment_config: {},
            claim_config: {},
            listing_defaults: {},
            generation_rules: {
              pricingPolicy: {
                version: `${activeTab}-pricing:v1`,
                shippingCost: { type: 'fixed', amount: 0 },
                marketplaceFee: { type: 'percent_of_sale_price', rate: 0 },
                targetMargin: { type: 'percent_of_sale_price', rate: 20 },
                rounding: { mode: 'ceil', unit: 100 },
              },
            },
          }, null, 2));
        }
      }
    };

    loadSettings();
    return () => {
      cancelled = true;
    };
  }, [selectedAccount, activeTab]);

  const handleCreateAccount = async (e: FormEvent) => {
    e.preventDefault();
    if (!newDisplayName.trim()) return;
    setIsSaving(true);
    setError(null);
    try {
      const credentials = JSON.parse(credentialsText || '{}');
      await api.post('/api/marketplace/accounts', {
        market_code: activeTab,
        display_name: newDisplayName.trim(),
        credentials,
      });
      setNewDisplayName('');
      await loadAccounts();
    } catch (err: any) {
      setError(err.message || '계정 생성에 실패했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveSettings = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedAccount) return;
    setIsSaving(true);
    setError(null);
    try {
      const parsed = JSON.parse(settingsText || '{}');
      await api.put(`/api/marketplace/accounts/${selectedAccount.id}/settings`, parsed);
      await loadAccounts();
    } catch (err: any) {
      setError(err.message || '설정 저장에 실패했습니다.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>마켓 계정 설정</h1>
        <p>Smart Store/Coupang 계정별 연결 및 정책 설정</p>
      </header>

      <div className={styles.tabRow}>
        {MARKET_TABS.map((tab) => (
          <button key={tab} type="button" onClick={() => setActiveTab(tab)} className={activeTab === tab ? styles.activeTab : styles.tab}>
            {marketLabel(tab)}
          </button>
        ))}
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.layout}>
        <section className={styles.card}>
          <h2>{marketLabel(activeTab)} 계정 목록</h2>
          {isLoading ? <p>불러오는 중...</p> : (
            <ul className={styles.accountList}>
              {tabAccounts.map((account) => (
                <li key={account.id}>
                  <button type="button" className={selectedId === account.id ? styles.accountActive : styles.accountItem} onClick={() => {
                    setSelectedId(account.id);
                  }}>
                    <strong>{account.display_name}</strong>
                    <span>{account.connection_status || 'unknown'}</span>
                  </button>
                </li>
              ))}
              {tabAccounts.length === 0 && <li className={styles.empty}>연결된 계정이 없습니다.</li>}
            </ul>
          )}

          <form className={styles.form} onSubmit={handleCreateAccount}>
            <label>
              새 계정 이름
              <input value={newDisplayName} onChange={(e) => setNewDisplayName(e.target.value)} placeholder={`${marketLabel(activeTab)} 계정`} />
            </label>
            <label>
              연결 인증 JSON
              <textarea className={styles.credentialsInput} value={credentialsText} onChange={(e) => setCredentialsText(e.target.value)} />
            </label>
            <button type="submit" disabled={isSaving}>{isSaving ? '저장 중...' : '계정 생성'}</button>
          </form>
        </section>

        <section className={styles.card}>
          <h2>{selectedAccount ? `${selectedAccount.display_name} 설정` : '계정을 선택하세요'}</h2>
          <form className={styles.form} onSubmit={handleSaveSettings}>
            <label>
              설정 JSON
              <textarea value={settingsText} onChange={(e) => setSettingsText(e.target.value)} />
            </label>
            <button type="submit" disabled={!selectedAccount || isSaving}>{isSaving ? '저장 중...' : '설정 저장'}</button>
          </form>
        </section>
      </div>
    </div>
  );
}
