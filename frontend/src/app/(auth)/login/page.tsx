'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useStore } from '@/store/useStore';
import {
  Bot,
  Document,
  Search,
  Analytics,
} from '@carbon/icons-react';

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

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
      {/* Left Panel - Train Image with Branding */}
      <div className="login-image-panel" style={{
        backgroundImage: 'url(https://images.unsplash.com/photo-1474487548417-781cb71495f3?w=1200)',
        flex: 1,
        minWidth: 0,
      }}>
        <div className="login-image-overlay" />
        <div className="login-image-content" style={{ gap: '1rem', display: 'flex', flexDirection: 'column' }}>
          <h1 className="login-branding-text">AIKM 台鐵問答 AI</h1>
          <p className="login-branding-desc">
            AI 驅動的車輛維修知識管理平台，快速查詢維修知識與技術文件
          </p>

          {/* Feature Cards */}
          <div style={{
            display: 'flex',
            gap: '1.5rem',
            marginTop: '1.5rem',
            flexWrap: 'wrap',
          }}>
            <div className="feature-card" style={{ flex: 1, minWidth: 180 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Bot size={20} style={{ color: 'var(--accent)' }} />
                <span className="feature-card-title">智慧問答</span>
              </div>
              <p className="feature-card-desc">AI 驅動的維修知識查詢</p>
            </div>
            <div className="feature-card" style={{ flex: 1, minWidth: 180 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Document size={20} style={{ color: 'var(--accent)' }} />
                <span className="feature-card-title">技術文件</span>
              </div>
              <p className="feature-card-desc">完整維修手冊與規範</p>
            </div>
            <div className="feature-card" style={{ flex: 1, minWidth: 180 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Search size={20} style={{ color: 'var(--accent)' }} />
                <span className="feature-card-title">知識搜尋</span>
              </div>
              <p className="feature-card-desc">快速精準定位資訊</p>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel - Login Form */}
      <div className="login-panel">
        <div className="login-card">
          {/* Logo Section */}
          <div className="login-logo-section">
            <div className="login-logo-icon">
              <Bot size={32} />
            </div>
            <h1 className="login-title">AIKM</h1>
            <p className="login-subtitle">台鐵問答 AI 系統</p>
          </div>

          {/* Welcome Section */}
          <div className="login-welcome">
            <h2 className="login-welcome-title">歡迎登入</h2>
            <p className="login-welcome-subtitle">請輸入您的帳號密碼以存取系統</p>
          </div>

          <form onSubmit={handleSubmit} className="login-form">
            {error && (
              <div style={{
                padding: '0.75rem 1rem',
                background: 'var(--error-light)',
                border: '1px solid var(--error)',
                color: 'var(--error)',
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
                placeholder="請輸入您的電子郵件"
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
                placeholder="請輸入密碼"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <div className="login-options">
              <label className="login-remember">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  style={{
                    width: 16,
                    height: 16,
                    accentColor: 'var(--accent)',
                  }}
                />
                記住我
              </label>
              <a href="#" className="login-forgot">忘記密碼？</a>
            </div>

            <button
              type="submit"
              className="btn btn-primary login-btn"
              disabled={loading}
            >
              {loading && <span className="spinner" style={{ width: 16, height: 16, borderWidth: '2px' }} />}
              {loading ? '登入中...' : '登入'}
            </button>
          </form>

          <div className="login-signup">
            還沒有帳號？ <a href="#" className="login-signup-link">立即註冊</a>
          </div>
        </div>
      </div>
    </div>
  );
}
