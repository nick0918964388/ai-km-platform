'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { Save, Add, Edit as EditIcon, TrashCan, ChevronUp, ChevronDown, Close } from '@carbon/icons-react';
import { STREAM_API_URL, getApiHeaders } from '@/lib/api';

interface ColumnLabel {
  column_name: string;
  label: string;
}

export default function SettingsPage() {
  const { settings, updateSettings, user } = useStore();
  const [localSettings, setLocalSettings] = useState(settings);
  const [saved, setSaved] = useState(false);

  // LLM settings state
  const [llmSettings, setLlmSettings] = useState({
    ollama_chat_url: '',
    ollama_chat_api_key: '',
    ollama_chat_model: '',
    ollama_light_model: '',
    intent_llm_url: '',
    intent_llm_model: '',
  });

  // Column label management state
  const [labels, setLabels] = useState<ColumnLabel[]>([]);
  const [newCol, setNewCol] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [editingCol, setEditingCol] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState('');
  const [labelsLoading, setLabelsLoading] = useState(false);

  // Table column configuration state
  const [selectedTable, setSelectedTable] = useState('');
  const [availableCols, setAvailableCols] = useState<{column_name: string; data_type: string}[]>([]);
  const [selectedCols, setSelectedCols] = useState<{column_name: string; display_order: number}[]>([]);
  const [tableConfigs, setTableConfigs] = useState<Record<string, {column_name: string; display_order: number}[]>>({});
  const [tables] = useState(['maximo_mxwo', 'maximo_mxsr', 'maximo_mxasset', 'maximo_fault_reports', 'maximo_cm_workorders', 'maximo_pm_workorders']);
  const [colConfigSaving, setColConfigSaving] = useState(false);
  const [colConfigSaved, setColConfigSaved] = useState(false);

  const fetchTableConfigs = useCallback(async () => {
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/table-columns`, { headers: getApiHeaders() });
      if (res.ok) {
        const data = await res.json();
        const configs: Record<string, {column_name: string; display_order: number}[]> = {};
        for (const item of data) {
          if (!configs[item.table_name]) configs[item.table_name] = [];
          configs[item.table_name].push({ column_name: item.column_name, display_order: item.display_order });
        }
        for (const key of Object.keys(configs)) {
          configs[key].sort((a, b) => a.display_order - b.display_order);
        }
        setTableConfigs(configs);
      }
    } catch { /* ignore */ }
  }, []);

  const fetchAvailableCols = useCallback(async (table: string) => {
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/table-columns/${table}/available`, { headers: getApiHeaders() });
      if (res.ok) {
        const data = await res.json();
        setAvailableCols(data);
      }
    } catch { /* ignore */ }
  }, []);

  // Fetch settings from backend on mount
  useEffect(() => {
    if (user?.role === 'admin') {
      fetch(`${STREAM_API_URL}/api/admin/settings`, { headers: getApiHeaders() })
        .then(r => r.json())
        .then(data => {
          setLocalSettings(prev => ({
            ...prev,
            siteName: data.site_name || prev.siteName,
            primaryColor: data.primary_color || prev.primaryColor,
            aiModel: data.ollama_chat_model || prev.aiModel,
            maxTokens: parseInt(data.max_tokens) || prev.maxTokens,
          }));
          setLlmSettings({
            ollama_chat_url: data.ollama_chat_url || '',
            ollama_chat_api_key: data.ollama_chat_api_key || '',
            ollama_chat_model: data.ollama_chat_model || '',
            ollama_light_model: data.ollama_light_model || '',
            intent_llm_url: data.intent_llm_url || '',
            intent_llm_model: data.intent_llm_model || '',
          });
        })
        .catch(() => {});
    }
  }, [user?.role]);

  useEffect(() => {
    if (user?.role === 'admin') fetchTableConfigs();
  }, [user?.role, fetchTableConfigs]);

  useEffect(() => {
    if (selectedTable) {
      fetchAvailableCols(selectedTable);
      setSelectedCols(tableConfigs[selectedTable] || []);
    }
  }, [selectedTable, tableConfigs, fetchAvailableCols]);

  const addColToSelected = (colName: string) => {
    if (selectedCols.some(c => c.column_name === colName)) return;
    setSelectedCols(prev => [...prev, { column_name: colName, display_order: prev.length + 1 }]);
  };

  const removeColFromSelected = (colName: string) => {
    setSelectedCols(prev => prev.filter(c => c.column_name !== colName).map((c, i) => ({ ...c, display_order: i + 1 })));
  };

  const moveCol = (index: number, direction: 'up' | 'down') => {
    setSelectedCols(prev => {
      const arr = [...prev];
      const swapIdx = direction === 'up' ? index - 1 : index + 1;
      if (swapIdx < 0 || swapIdx >= arr.length) return prev;
      [arr[index], arr[swapIdx]] = [arr[swapIdx], arr[index]];
      return arr.map((c, i) => ({ ...c, display_order: i + 1 }));
    });
  };

  const saveTableColumns = async () => {
    if (!selectedTable) return;
    setColConfigSaving(true);
    try {
      await fetch(`${STREAM_API_URL}/api/admin/table-columns`, {
        method: 'POST',
        headers: { ...getApiHeaders() as Record<string, string>, 'Content-Type': 'application/json' },
        body: JSON.stringify({ table_name: selectedTable, columns: selectedCols }),
      });
      setTableConfigs(prev => ({ ...prev, [selectedTable]: [...selectedCols] }));
      setColConfigSaved(true);
      setTimeout(() => setColConfigSaved(false), 2000);
    } catch { /* ignore */ }
    setColConfigSaving(false);
  };

  const getColLabel = (colName: string) => {
    const found = labels.find(l => l.column_name === colName);
    return found ? found.label : '';
  };

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

  const handleSave = async () => {
    // Save to backend
    try {
      await fetch(`${STREAM_API_URL}/api/admin/settings`, {
        method: 'POST',
        headers: { ...getApiHeaders() as Record<string, string>, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_name: localSettings.siteName,
          primary_color: localSettings.primaryColor,
          max_tokens: String(localSettings.maxTokens),
          ...llmSettings,
        }),
      });
    } catch { /* ignore */ }
    // Also save to local store
    updateSettings(localSettings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  // Fetch available models from Ollama
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  useEffect(() => {
    if (llmSettings.ollama_chat_url) {
      const baseUrl = llmSettings.ollama_chat_url.replace('/v1', '');
      fetch(`${baseUrl}/api/tags`).then(r => r.json()).then(data => {
        setAvailableModels((data.models || []).map((m: any) => m.name));
      }).catch(() => {});
    }
  }, [llmSettings.ollama_chat_url]);

  // Also fetch from intent endpoint
  const [intentModels, setIntentModels] = useState<string[]>([]);
  useEffect(() => {
    if (llmSettings.intent_llm_url) {
      const baseUrl = llmSettings.intent_llm_url.replace('/v1', '');
      fetch(`${baseUrl}/api/tags`).then(r => r.json()).then(data => {
        setIntentModels((data.models || []).map((m: any) => m.name));
      }).catch(() => {});
    }
  }, [llmSettings.intent_llm_url]);

  const cardStyle: React.CSSProperties = {
    background: 'var(--bg-secondary, #fff)',
    borderRadius: 'var(--radius-lg, 12px)',
    border: '1px solid var(--border)',
    padding: '1.25rem',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  };
  const cardTitle: React.CSSProperties = {
    fontSize: '1rem', fontWeight: 600, margin: '0 0 1rem', color: 'var(--text-primary)',
  };

  return (
    <div style={{ padding: '1.5rem 2rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>系統設定</h1>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: '0.25rem 0 1.5rem' }}>管理系統參數、AI 模型與使用者設定</p>

      {/* 2-column grid for small settings cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>

      {/* AI Settings Card */}
      <div style={cardStyle}>
        <h2 style={cardTitle}>AI 模型設定</h2>
        <div className="form-group" style={{ marginBottom: '0.75rem' }}>
          <label className="form-label">LLM 端點 URL</label>
          <input type="text" className="form-input" style={{ width: '100%' }}
            value={llmSettings.ollama_chat_url}
            onChange={e => setLlmSettings(s => ({ ...s, ollama_chat_url: e.target.value }))}
          />
        </div>
        <div className="form-group" style={{ marginBottom: '0.75rem' }}>
          <label className="form-label">Chat 模型</label>
          <select className="form-input" style={{ width: '100%' }}
            value={llmSettings.ollama_chat_model}
            onChange={e => setLlmSettings(s => ({ ...s, ollama_chat_model: e.target.value }))}>
            {llmSettings.ollama_chat_model && !availableModels.includes(llmSettings.ollama_chat_model) && (
              <option value={llmSettings.ollama_chat_model}>{llmSettings.ollama_chat_model}</option>
            )}
            {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="form-group" style={{ marginBottom: '0.75rem' }}>
          <label className="form-label">Light 模型（SQL/Rewrite）</label>
          <select className="form-input" style={{ width: '100%' }}
            value={llmSettings.ollama_light_model}
            onChange={e => setLlmSettings(s => ({ ...s, ollama_light_model: e.target.value }))}>
            {llmSettings.ollama_light_model && !availableModels.includes(llmSettings.ollama_light_model) && (
              <option value={llmSettings.ollama_light_model}>{llmSettings.ollama_light_model}</option>
            )}
            {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">API Key</label>
          <input type="password" className="form-input" style={{ width: '100%' }}
            value={llmSettings.ollama_chat_api_key}
            onChange={e => setLlmSettings(s => ({ ...s, ollama_chat_api_key: e.target.value }))}
            placeholder="ollama"
          />
        </div>
      </div>

      {/* Intent Model Card */}
      <div style={cardStyle}>
        <h2 style={cardTitle}>Intent 分類模型</h2>
        <div className="form-group" style={{ marginBottom: '0.75rem' }}>
          <label className="form-label">端點 URL</label>
          <input type="text" className="form-input" style={{ width: '100%' }}
            value={llmSettings.intent_llm_url}
            onChange={e => setLlmSettings(s => ({ ...s, intent_llm_url: e.target.value }))}
          />
        </div>
        <div className="form-group">
          <label className="form-label">模型名稱</label>
          <select className="form-input" style={{ width: '100%' }}
            value={llmSettings.intent_llm_model}
            onChange={e => setLlmSettings(s => ({ ...s, intent_llm_model: e.target.value }))}>
            {llmSettings.intent_llm_model && !intentModels.includes(llmSettings.intent_llm_model) && (
              <option value={llmSettings.intent_llm_model}>{llmSettings.intent_llm_model}</option>
            )}
            {intentModels.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>

      {/* User Settings Card (Admin only) */}
      {user?.role === 'admin' && (
        <div style={cardStyle}>
          <h2 style={cardTitle}>使用者設定</h2>

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

      </div>{/* end grid */}

      {/* Save button moved to bottom */}

      {/* Column Label Management (Admin only) - Full width card */}
      {user?.role === 'admin' && (
        <div style={{ ...cardStyle, marginBottom: '1rem' }}>
          <h2 style={cardTitle}>欄位名稱映射</h2>
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

      {/* Table Column Configuration (Admin only) - Full width card */}
      {user?.role === 'admin' && (
        <div style={{ ...cardStyle, marginBottom: '1rem' }}>
          <h2 style={cardTitle}>表格欄位設定</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
            設定每張資料表的預設顯示欄位與順序
          </p>

          {/* Table selector */}
          <div className="form-group">
            <select
              className="form-input"
              value={selectedTable}
              onChange={e => setSelectedTable(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="">選擇資料表...</option>
              {tables.map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          {selectedTable && (
            <div style={{ display: 'flex', gap: '1.5rem', marginTop: '1rem', flexWrap: 'wrap' }}>
              {/* Available columns */}
              <div style={{ flex: 1, minWidth: 240 }}>
                <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>可用欄位</h3>
                <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.5rem', maxHeight: 320, overflowY: 'auto' }}>
                  {availableCols.length === 0 ? (
                    <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', padding: '0.25rem' }}>載入中...</p>
                  ) : (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                      {availableCols.map(col => {
                        const isSelected = selectedCols.some(c => c.column_name === col.column_name);
                        const label = getColLabel(col.column_name);
                        return (
                          <button
                            key={col.column_name}
                            onClick={() => !isSelected && addColToSelected(col.column_name)}
                            disabled={isSelected}
                            style={{
                              padding: '0.25rem 0.5rem',
                              fontSize: '0.8125rem',
                              fontFamily: 'monospace',
                              border: '1px solid var(--border)',
                              borderRadius: 4,
                              background: isSelected ? 'var(--bg-tertiary, #f4f4f4)' : 'var(--bg-secondary, #fff)',
                              color: isSelected ? 'var(--text-muted)' : 'var(--text-primary)',
                              cursor: isSelected ? 'default' : 'pointer',
                              opacity: isSelected ? 0.5 : 1,
                              textDecoration: 'none',
                            }}
                            title={label ? `${col.column_name} (${label})` : col.column_name}
                          >
                            {col.column_name}
                            {label && <span style={{ fontFamily: 'sans-serif', fontSize: '0.75rem', color: 'var(--text-secondary)', marginLeft: '0.25rem' }}>({label})</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Selected columns */}
              <div style={{ flex: 1, minWidth: 240 }}>
                <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>已選欄位（排序）</h3>
                <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.5rem', maxHeight: 320, overflowY: 'auto' }}>
                  {selectedCols.length === 0 ? (
                    <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', padding: '0.25rem' }}>點擊左側欄位加入</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      {selectedCols.map((col, idx) => {
                        const label = getColLabel(col.column_name);
                        return (
                          <div
                            key={col.column_name}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.375rem',
                              padding: '0.25rem 0.5rem',
                              background: 'var(--bg-secondary, #fff)',
                              border: '1px solid var(--border)',
                              borderRadius: 4,
                              fontSize: '0.8125rem',
                            }}
                          >
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', minWidth: 20 }}>{idx + 1}.</span>
                            <span style={{ flex: 1, fontFamily: 'monospace' }}>
                              {col.column_name}
                              {label && <span style={{ fontFamily: 'sans-serif', fontSize: '0.75rem', color: 'var(--text-secondary)', marginLeft: '0.25rem' }}>({label})</span>}
                            </span>
                            <button
                              onClick={() => moveCol(idx, 'up')}
                              disabled={idx === 0}
                              style={{ background: 'none', border: 'none', cursor: idx === 0 ? 'default' : 'pointer', padding: '0.125rem', color: idx === 0 ? 'var(--text-muted)' : 'var(--text-secondary)', opacity: idx === 0 ? 0.3 : 1 }}
                              title="上移"
                            >
                              <ChevronUp size={14} />
                            </button>
                            <button
                              onClick={() => moveCol(idx, 'down')}
                              disabled={idx === selectedCols.length - 1}
                              style={{ background: 'none', border: 'none', cursor: idx === selectedCols.length - 1 ? 'default' : 'pointer', padding: '0.125rem', color: idx === selectedCols.length - 1 ? 'var(--text-muted)' : 'var(--text-secondary)', opacity: idx === selectedCols.length - 1 ? 0.3 : 1 }}
                              title="下移"
                            >
                              <ChevronDown size={14} />
                            </button>
                            <button
                              onClick={() => removeColFromSelected(col.column_name)}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.125rem', color: '#da1e28' }}
                              title="移除"
                            >
                              <Close size={14} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
                <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <button
                    className="btn btn-primary"
                    onClick={saveTableColumns}
                    disabled={colConfigSaving || selectedCols.length === 0}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.5rem 0.75rem' }}
                  >
                    <Save size={16} />
                    {colConfigSaving ? '儲存中...' : '儲存此表設定'}
                  </button>
                  {colConfigSaved && (
                    <span style={{ color: '#198038', fontSize: '0.875rem' }}>
                      ✓ 已儲存
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Save Button at bottom */}
      <div style={{ margin: '1.5rem 0', paddingTop: '1rem', borderTop: '1px solid var(--border)' }}>
        <button onClick={handleSave} style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          padding: '0.75rem 1.5rem', background: 'var(--primary)', color: 'white',
          border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontWeight: 600, fontSize: '0.9375rem',
        }}>
          <Save size={18} /> {saved ? '已儲存 ✓' : '儲存所有設定'}
        </button>
      </div>
    </div>
  );
}
