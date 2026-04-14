'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { Save, Add, Edit as EditIcon, TrashCan } from '@carbon/icons-react';
import { STREAM_API_URL, getApiHeaders } from '@/lib/api';

interface ColumnLabel {
  column_name: string;
  label: string;
}

export default function SettingsPage() {
  const { settings, updateSettings, user } = useStore();
  const [localSettings, setLocalSettings] = useState(settings);
  const [saved, setSaved] = useState(false);

  // Column label management state
  const [labels, setLabels] = useState<ColumnLabel[]>([]);
  const [newCol, setNewCol] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [editingCol, setEditingCol] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState('');
  const [labelsLoading, setLabelsLoading] = useState(false);

  const fetchLabels = useCallback(async () => {
    setLabelsLoading(true);
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/column-labels`, { headers: getApiHeaders() });
      if (res.ok) {
        const data = await res.json();
        setLabels(data);
      }
    } catch { /* ignore */ }
    setLabelsLoading(false);
  }, []);

  useEffect(() => {
    if (user?.role === 'admin') fetchLabels();
  }, [user?.role, fetchLabels]);

  const addLabel = async () => {
    if (!newCol.trim() || !newLabel.trim()) return;
    try {
      await fetch(`${STREAM_API_URL}/api/admin/column-labels`, {
        method: 'POST',
        headers: { ...getApiHeaders() as Record<string, string>, 'Content-Type': 'application/json' },
        body: JSON.stringify({ column_name: newCol.trim(), label: newLabel.trim() }),
      });
      setLabels(prev => [...prev.filter(l => l.column_name !== newCol.trim()), { column_name: newCol.trim(), label: newLabel.trim() }]);
      setNewCol('');
      setNewLabel('');
    } catch { /* ignore */ }
  };

  const updateLabel = async (columnName: string, label: string) => {
    if (!label.trim()) return;
    try {
      await fetch(`${STREAM_API_URL}/api/admin/column-labels`, {
        method: 'POST',
        headers: { ...getApiHeaders() as Record<string, string>, 'Content-Type': 'application/json' },
        body: JSON.stringify({ column_name: columnName, label: label.trim() }),
      });
      setLabels(prev => prev.map(l => l.column_name === columnName ? { ...l, label: label.trim() } : l));
    } catch { /* ignore */ }
    setEditingCol(null);
  };

  const deleteLabel = async (name: string) => {
    if (!confirm(`確定要刪除「${name}」的欄位映射嗎？`)) return;
    try {
      await fetch(`${STREAM_API_URL}/api/admin/column-labels/${name}`, {
        method: 'DELETE',
        headers: getApiHeaders(),
      });
      setLabels(prev => prev.filter(l => l.column_name !== name));
    } catch { /* ignore */ }
  };

  const handleSave = () => {
    updateSettings(localSettings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: 720 }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>系統設定</h1>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: '0.25rem 0 1.5rem' }}>管理系統參數、AI 模型與使用者設定</p>

      {/* General Settings */}
      <div style={{ marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '1.5rem 0 0.75rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>一般設定</h2>

        <div className="form-group">
          <label className="form-label">系統名稱</label>
          <input
            type="text"
            className="form-input"
            value={localSettings.siteName}
            onChange={(e) => setLocalSettings({ ...localSettings, siteName: e.target.value })}
            style={{ width: '100%' }}
          />
        </div>

        <div className="form-group">
          <label className="form-label">主題色</label>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="color"
              value={localSettings.primaryColor}
              onChange={(e) => setLocalSettings({ ...localSettings, primaryColor: e.target.value })}
              style={{
                width: 48,
                height: 48,
                border: '1px solid var(--border)',
                borderRadius: 8,
                cursor: 'pointer',
                flexShrink: 0,
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
      <div style={{ marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '1.5rem 0 0.75rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>AI 設定</h2>

        <div className="form-group">
          <label className="form-label">AI 模型</label>
          <select
            className="form-input"
            value={localSettings.aiModel}
            onChange={(e) => setLocalSettings({ ...localSettings, aiModel: e.target.value })}
            style={{ width: '100%' }}
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
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* User Settings (Admin only) */}
      {user?.role === 'admin' && (
        <div style={{ marginBottom: '1rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '1.5rem 0 0.75rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>使用者設定</h2>

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
              style={{ width: '100%' }}
            >
              <option value="user">一般使用者</option>
              <option value="guest">訪客</option>
            </select>
          </div>
        </div>
      )}

      {/* Column Label Management (Admin only) */}
      {user?.role === 'admin' && (
        <div style={{ marginBottom: '1rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '1.5rem 0 0.75rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>欄位名稱映射</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
            管理 SQL 查詢結果的欄位中文顯示名稱
          </p>

          {/* Add new label */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="text"
              className="form-input"
              placeholder="欄位名 (如 wonum)"
              value={newCol}
              onChange={e => setNewCol(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addLabel()}
              style={{ width: 180 }}
            />
            <input
              type="text"
              className="form-input"
              placeholder="中文名稱 (如 工單號)"
              value={newLabel}
              onChange={e => setNewLabel(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addLabel()}
              style={{ width: 180 }}
            />
            <button
              className="btn btn-primary"
              onClick={addLabel}
              disabled={!newCol.trim() || !newLabel.trim()}
              style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.5rem 0.75rem' }}
            >
              <Add size={16} />
              新增
            </button>
          </div>

          {/* Labels table */}
          {labelsLoading ? (
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>載入中...</p>
          ) : labels.length === 0 ? (
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>尚無欄位映射</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ background: 'var(--bg-tertiary, #f4f4f4)' }}>
                  <th style={{ textAlign: 'left', padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--border)' }}>欄位名稱</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--border)' }}>中文顯示</th>
                  <th style={{ textAlign: 'right', padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--border)', width: 100 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {labels.map(l => (
                  <tr key={l.column_name} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '0.5rem 0.75rem', fontFamily: 'monospace' }}>{l.column_name}</td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      {editingCol === l.column_name ? (
                        <input
                          type="text"
                          className="form-input"
                          value={editingLabel}
                          onChange={e => setEditingLabel(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') updateLabel(l.column_name, editingLabel);
                            if (e.key === 'Escape') setEditingCol(null);
                          }}
                          onBlur={() => updateLabel(l.column_name, editingLabel)}
                          autoFocus
                          style={{ width: '100%', padding: '0.25rem 0.5rem' }}
                        />
                      ) : (
                        l.label
                      )}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>
                      <button
                        onClick={() => { setEditingCol(l.column_name); setEditingLabel(l.label); }}
                        title="編輯"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', color: 'var(--text-secondary)' }}
                      >
                        <EditIcon size={16} />
                      </button>
                      <button
                        onClick={() => deleteLabel(l.column_name)}
                        title="刪除"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', color: '#da1e28', marginLeft: '0.25rem' }}
                      >
                        <TrashCan size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Save Button */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
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
