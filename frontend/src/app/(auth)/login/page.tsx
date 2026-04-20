'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useStore } from '@/store/useStore';
import { UserRole } from '@/types';
import {
  Bot,
  Document,
  Search,
  Analytics,
  ViewFilled,
  ViewOffFilled,
} from '@carbon/icons-react';

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Load remembered email on mount
  useEffect(() => {
    const remembered = localStorage.getItem('remembered_email');
    if (remembered) {
      setEmail(remembered);
      setRememberMe(true);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || '登入失敗');
        setLoading(false);
        return;
      }

      const data = await res.json();

      // Remember email preference
      if (rememberMe) {
        localStorage.setItem('remembered_email', email);
      } else {
        localStorage.removeItem('remembered_email');
      }

      // Store JWT token
      localStorage.setItem('auth_token', data.token);

      // Store user in Zustand
      setUser({
        id: data.user.id,
        name: data.user.name,
        email: data.user.email,
        role: data.user.role as UserRole,
        createdAt: new Date(),
      });

      router.push('/chat');
    } catch (err) {
      setError('無法連線到伺服器');
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      {/* Left Panel - Train Image with Branding */}
      <div
        className="login-image-panel"
        style={{
          backgroundImage: 'url(https://images.unsplash.com/photo-1474487548417-781cb71495f3?w=1200)',
          flex: 1,
          minWidth: 0,
        }}
      >
        <div className="login-image-overlay" />
        <div className="login-image-content" style={{ gap: '1rem', display: 'flex', flexDirection: 'column' }}>
          <h1 className="login-branding-text">AIKM 台鐵問答 AI</h1>
          <p className="login-branding-desc">
            AI 驅動的車輛維修知識管理平台，快速查詢維修知識與技術文件
          </p>

          {/* Feature Cards - hidden on mobile to save space */}
          <div
            className="hidden sm:flex"
            style={{
              gap: '1.5rem',
              marginTop: '1.5rem',
              flexWrap: 'wrap',
            }}
          >
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
        <div className="login-card" style={{ width: '100%', maxWidth: 400 }}>
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
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="form-input"
                  placeholder="請輸入密碼"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  style={{ paddingRight: '2.5rem' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: 8,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--text-muted)',
                    padding: 4,
                    display: 'flex',
                    alignItems: 'center',
                  }}
                  aria-label={showPassword ? '隱藏密碼' : '顯示密碼'}
                >
                  {showPassword ? <ViewOffFilled size={18} /> : <ViewFilled size={18} />}
                </button>
              </div>
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
