'use client';

import { useState, useEffect } from 'react';
import { Close } from '@carbon/icons-react';
import { User, UserRole } from '@/types';

interface UserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (user: Partial<User> & { password?: string }) => void;
  user?: User | null;
}

export default function UserModal({ isOpen, onClose, onSave, user }: UserModalProps) {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'user' as UserRole,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (user) {
      setFormData({
        name: user.name,
        email: user.email,
        password: '',
        confirmPassword: '',
        role: user.role,
      });
    } else {
      setFormData({
        name: '',
        email: '',
        password: '',
        confirmPassword: '',
        role: 'user',
      });
    }
    setErrors({});
  }, [user, isOpen]);

  const validate = () => {
    const newErrors: Record<string, string> = {};
    
    if (!formData.name.trim()) {
      newErrors.name = '請輸入名稱';
    }
    
    if (!formData.email.trim()) {
      newErrors.email = '請輸入電子郵件';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = '請輸入有效的電子郵件';
    }
    
    if (!user) {
      // New user requires password
      if (!formData.password) {
        newErrors.password = '請輸入密碼';
      } else if (formData.password.length < 6) {
        newErrors.password = '密碼至少需要 6 個字元';
      }
      
      if (formData.password !== formData.confirmPassword) {
        newErrors.confirmPassword = '密碼不一致';
      }
    } else if (formData.password) {
      // Editing user with new password
      if (formData.password.length < 6) {
        newErrors.password = '密碼至少需要 6 個字元';
      }
      if (formData.password !== formData.confirmPassword) {
        newErrors.confirmPassword = '密碼不一致';
      }
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validate()) return;
    
    onSave({
      id: user?.id,
      name: formData.name,
      email: formData.email,
      role: formData.role,
      password: formData.password || undefined,
    });
    
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.3)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          width: '100%',
          maxWidth: 480,
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: 'var(--shadow-md)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '1.25rem 1.5rem',
          borderBottom: '1px solid var(--border)',
        }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0 }}>
            {user ? '編輯使用者' : '新增使用者'}
          </h2>
          <button 
            className="input-btn" 
            onClick={onClose}
            style={{ marginRight: -8 }}
          >
            <Close size={20} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ padding: '1.5rem' }}>
          <div className="form-group">
            <label className="form-label">名稱 *</label>
            <input
              type="text"
              className="form-input"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="輸入使用者名稱"
              style={errors.name ? { borderColor: '#da1e28' } : {}}
            />
            {errors.name && (
              <div style={{ color: '#da1e28', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                {errors.name}
              </div>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">電子郵件 *</label>
            <input
              type="email"
              className="form-input"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="user@example.com"
              style={errors.email ? { borderColor: '#da1e28' } : {}}
            />
            {errors.email && (
              <div style={{ color: '#da1e28', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                {errors.email}
              </div>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">角色 *</label>
            <select
              className="form-input"
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
            >
              <option value="admin">管理員</option>
              <option value="user">使用者</option>
              <option value="guest">訪客</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">
              密碼 {user ? '（留空則不變更）' : '*'}
            </label>
            <input
              type="password"
              className="form-input"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder={user ? '輸入新密碼（選填）' : '輸入密碼'}
              style={errors.password ? { borderColor: '#da1e28' } : {}}
            />
            {errors.password && (
              <div style={{ color: '#da1e28', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                {errors.password}
              </div>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">確認密碼</label>
            <input
              type="password"
              className="form-input"
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              placeholder="再次輸入密碼"
              style={errors.confirmPassword ? { borderColor: '#da1e28' } : {}}
            />
            {errors.confirmPassword && (
              <div style={{ color: '#da1e28', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                {errors.confirmPassword}
              </div>
            )}
          </div>

          {/* Actions */}
          <div style={{ 
            display: 'flex', 
            gap: '0.75rem', 
            justifyContent: 'flex-end',
            marginTop: '1.5rem',
            paddingTop: '1rem',
            borderTop: '1px solid var(--border)'
          }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="btn btn-primary">
              {user ? '儲存變更' : '新增使用者'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
