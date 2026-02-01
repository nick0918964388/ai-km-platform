'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useStore } from '@/store/useStore';

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // Demo login - will be replaced with actual auth
    setTimeout(() => {
      if (email === 'admin@example.com' && password === 'admin') {
        setUser({
          id: '1',
          name: '管理員',
          email: 'admin@example.com',
          role: 'admin',
          createdAt: new Date(),
        });
        router.push('/chat');
      } else if (email && password) {
        setUser({
          id: '2',
          name: email.split('@')[0],
          email: email,
          role: 'user',
          createdAt: new Date(),
        });
        router.push('/chat');
      } else {
        setError('請輸入帳號密碼');
      }
      setLoading(false);
    }, 500);
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div style={{ 
          textAlign: 'center', 
          marginBottom: '2rem' 
        }}>
          <div style={{
            width: 64,
            height: 64,
            background: 'var(--primary)',
            borderRadius: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontSize: '1.5rem',
            fontWeight: 700,
            margin: '0 auto 1rem'
          }}>
            KM
          </div>
          <h1 className="login-title">車輛維修知識庫</h1>
          <p className="login-subtitle">AI 智慧助理平台</p>
        </div>

        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{
              padding: '0.75rem 1rem',
              background: '#ffd7d9',
              color: '#a2191f',
              borderRadius: 8,
              marginBottom: '1rem',
              fontSize: '0.875rem'
            }}>
              {error}
            </div>
          )}

          <div className="form-group">
            <label className="form-label">電子郵件</label>
            <input
              type="email"
              className="form-input"
              placeholder="your@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">密碼</label>
            <input
              type="password"
              className="form-input"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center', marginTop: '0.5rem', gap: '0.5rem' }}
            disabled={loading}
          >
            {loading && <span className="spinner" style={{ width: 16, height: 16, borderWidth: '2px' }} />}
            {loading ? '登入中...' : '登入'}
          </button>
        </form>

        <div style={{
          marginTop: '1.5rem',
          padding: '1rem',
          background: 'var(--bg-secondary)',
          borderRadius: 8,
          fontSize: '0.75rem',
          color: 'var(--text-secondary)',
          lineHeight: 1.6
        }}>
          <strong>Demo 帳號：</strong>
          <div style={{ marginTop: '0.25rem' }}>管理員：admin@example.com / admin</div>
          <div>一般使用者：任意 email / 任意密碼</div>
        </div>
      </div>
    </div>
  );
}
