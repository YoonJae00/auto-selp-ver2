'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from '../auth.module.css';

export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminSecretKey, setAdminSecretKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await api.post('/api/auth/register', {
        username: email,
        password,
        nickname,
        is_admin: isAdmin,
        admin_secret_key: isAdmin ? adminSecretKey : undefined,
      });
      router.push('/login');
    } catch (err: any) {
      setError(err.message || '회원가입에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthLogin = async (provider: 'google' | 'naver') => {
    try {
      const res = await api.get<{ url: string }>(`/api/auth/${provider}/login`);
      if (res.url) {
        window.location.href = res.url;
      }
    } catch (err: any) {
      setError(`${provider} 로그인에 실패했습니다.`);
    }
  };

  return (
    <>
      <h1 className={styles.title}>회원가입</h1>
      <p className={styles.subtitle}>Auto-Selp의 새로운 가족이 되어주세요.</p>
      
      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.oauthWrapper}>
        <button 
          className={`${styles.oauthButton} ${styles.google}`}
          onClick={() => handleOAuthLogin('google')}
        >
          <img src="/google-icon.svg" alt="Google" className={styles.oauthIcon} />
          Google로 시작하기
        </button>
        <button 
          className={`${styles.oauthButton} ${styles.naver}`}
          onClick={() => handleOAuthLogin('naver')}
        >
          <img src="/naver-icon.svg" alt="Naver" className={styles.oauthIcon} />
          Naver로 시작하기
        </button>
      </div>

      <div className={styles.divider}>
        <span>또는</span>
      </div>
      
      <form onSubmit={handleSubmit}>
        <div className={styles.formGroup}>
          <label className={styles.label}>이름 (닉네임)</label>
          <input
            type="text"
            className={styles.input}
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            required
            placeholder="홍길동"
          />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.label}>이메일 (아이디)</label>
          <input
            type="email"
            className={styles.input}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="example@email.com"
          />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.label}>비밀번호</label>
          <input
            type="password"
            className={styles.input}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="••••••••"
          />
        </div>
        
        <div className={styles.checkboxGroup}>
          <input
            type="checkbox"
            id="isAdmin"
            checked={isAdmin}
            onChange={(e) => setIsAdmin(e.target.checked)}
          />
          <label htmlFor="isAdmin" className={styles.label} style={{ margin: 0 }}>
            관리자 계정으로 가입
          </label>
        </div>

        {isAdmin && (
          <div className={styles.formGroup} style={{ marginTop: '20px' }}>
            <label className={styles.label}>관리자 인증 코드</label>
            <input
              type="password"
              className={styles.input}
              value={adminSecretKey}
              onChange={(e) => setAdminSecretKey(e.target.value)}
              required
              placeholder="관리자 전용 코드"
            />
          </div>
        )}
        
        <div className={styles.buttonWrapper}>
          <PillButton variant="primary" type="submit" className={styles.submitButton}>
            {loading ? '처리 중...' : '회원가입'}
          </PillButton>
          <Link href="/login" className={styles.link}>
            이미 계정이 있으신가요? 로그인
          </Link>
        </div>
      </form>
    </>
  );
}
