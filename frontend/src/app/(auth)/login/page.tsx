'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import PillButton from '@/components/UI/PillButton/PillButton';
import styles from '../auth.module.css';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const checkAuth = useAuthStore((state) => state.checkAuth);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // 1. Get Token (sets HttpOnly cookie)
      await api.postForm<{ access_token: string }>('/api/auth/token', {
        username: email,
        password,
      });

      // 2. Fetch user info using the cookie and update store
      await checkAuth();
      
      router.push('/home');
    } catch (err: any) {
      setError(err.message || '로그인에 실패했습니다.');
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
      <h1 className={styles.title}>로그인</h1>
      <p className={styles.subtitle}>계정에 접속하여 서비스를 이용하세요.</p>
      
      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.oauthWrapper}>
        <button 
          className={`${styles.oauthButton} ${styles.google}`}
          onClick={() => handleOAuthLogin('google')}
        >
          <img src="/google-icon.svg" alt="Google" className={styles.oauthIcon} />
          Google로 로그인
        </button>
        <button 
          className={`${styles.oauthButton} ${styles.naver}`}
          onClick={() => handleOAuthLogin('naver')}
        >
          <img src="/naver-icon.svg" alt="Naver" className={styles.oauthIcon} />
          Naver로 로그인
        </button>
      </div>

      <div className={styles.divider}>
        <span>또는</span>
      </div>
      
      <form onSubmit={handleSubmit}>
        <div className={styles.formGroup}>
          <label className={styles.label}>이메일</label>
          <input
            type="email"
            className={styles.input}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="example@email.com"
            autoFocus
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
        
        <div className={styles.buttonWrapper}>
          <PillButton variant="primary" type="submit" className={styles.submitButton}>
            {loading ? '로그인 중...' : '로그인'}
          </PillButton>
          <Link href="/register" className={styles.link}>
            계정이 없으신가요? 회원가입
          </Link>
        </div>
      </form>
    </>
  );
}
