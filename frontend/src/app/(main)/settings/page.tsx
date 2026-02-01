'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { Save } from '@carbon/icons-react';

export default function SettingsPage() {
  const { settings, updateSettings, user } = useStore();
  const [localSettings, setLocalSettings] = useState(settings);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    updateSettings(localSettings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="settings-container">
      <h1 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1.5rem' }}>
        系統設定
      </h1>

      {/* General Settings */}
      <div className="settings-section">
        <h2 className="settings-title">一般設定</h2>
        
        <div className="form-group">
          <label className="form-label">系統名稱</label>
          <input
            type="text"
            className="form-input"
            value={localSettings.siteName}
            onChange={(e) => setLocalSettings({ ...localSettings, siteName: e.target.value })}
          />
        </div>

        <div className="form-group">
          <label className="form-label">主題色</label>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <input
              type="color"
              value={localSettings.primaryColor}
              onChange={(e) => setLocalSettings({ ...localSettings, primaryColor: e.target.value })}
              style={{ 
                width: 48, 
                height: 48, 
                border: '1px solid var(--border)',
                borderRadius: 8,
                cursor: 'pointer'
              }}
            />
            <input
              type="text"
              className="form-input"
              value={localSettings.primaryColor}
              onChange={(e) => setLocalSettings({ ...localSettings, primaryColor: e.target.value })}
              style={{ width: 120 }}
            />
          </div>
        </div>
      </div>

      {/* AI Settings */}
      <div className="settings-section">
        <h2 className="settings-title">AI 設定</h2>
        
        <div className="form-group">
          <label className="form-label">AI 模型</label>
          <select
            className="form-input"
            value={localSettings.aiModel}
            onChange={(e) => setLocalSettings({ ...localSettings, aiModel: e.target.value })}
          >
            <option value="gpt-4">GPT-4</option>
            <option value="gpt-4o">GPT-4o</option>
            <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
            <option value="claude-3">Claude 3</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">最大 Token 數</label>
          <input
            type="number"
            className="form-input"
            value={localSettings.maxTokens}
            onChange={(e) => setLocalSettings({ ...localSettings, maxTokens: parseInt(e.target.value) })}
            min={256}
            max={32000}
            step={256}
          />
        </div>
      </div>

      {/* User Settings (Admin only) */}
      {user?.role === 'admin' && (
        <div className="settings-section">
          <h2 className="settings-title">使用者設定</h2>
          
          <div className="form-group">
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={localSettings.allowRegistration}
                onChange={(e) => setLocalSettings({ ...localSettings, allowRegistration: e.target.checked })}
                style={{ width: 18, height: 18 }}
              />
              <span>允許新使用者註冊</span>
            </label>
          </div>

          <div className="form-group">
            <label className="form-label">預設使用者角色</label>
            <select
              className="form-input"
              value={localSettings.defaultRole}
              onChange={(e) => setLocalSettings({ ...localSettings, defaultRole: e.target.value as any })}
            >
              <option value="user">一般使用者</option>
              <option value="guest">訪客</option>
            </select>
          </div>
        </div>
      )}

      {/* Save Button */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
        <button className="btn btn-primary" onClick={handleSave}>
          <Save size={16} />
          儲存設定
        </button>
        {saved && (
          <span style={{ color: '#198038', fontSize: '0.875rem' }}>
            ✓ 設定已儲存
          </span>
        )}
      </div>
    </div>
  );
}
