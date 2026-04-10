'use client';

import { useState, useEffect } from 'react';
import { Add, TrashCan, Renew, DataBase, Education } from '@carbon/icons-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Rule { id: number; content: string; }
interface Example { id: number; question: string; sql_query: string; verified: boolean; }

export default function MaximoKnowledgePage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [examples, setExamples] = useState<Example[]>([]);
  const [loading, setLoading] = useState(true);
  const [newRule, setNewRule] = useState('');
  const [newQ, setNewQ] = useState('');
  const [newSQL, setNewSQL] = useState('');
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'rules' | 'examples'>('rules');

  const fetchKnowledge = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/maximo/knowledge`);
      const data = await res.json();
      setRules(data.rules || []);
      setExamples(data.examples || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchKnowledge(); }, []);

  const addRule = async () => {
    if (!newRule.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/maximo/knowledge/rule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newRule }),
      });
      if (res.ok) {
        setNewRule('');
        await fetchKnowledge();
      }
    } finally { setSaving(false); }
  };

  const deleteRule = async (id: number) => {
    await fetch(`${API}/api/maximo/knowledge/rule/${id}`, { method: 'DELETE' });
    setRules(r => r.filter(x => x.id !== id));
  };

  const addExample = async () => {
    if (!newQ.trim() || !newSQL.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/maximo/knowledge/example`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: newQ, sql_query: newSQL }),
      });
      if (res.ok) {
        setNewQ(''); setNewSQL('');
        await fetchKnowledge();
      }
    } finally { setSaving(false); }
  };

  const deleteExample = async (id: number) => {
    await fetch(`${API}/api/maximo/knowledge/example/${id}`, { method: 'DELETE' });
    setExamples(e => e.filter(x => x.id !== id));
  };

  const tabStyle = (active: boolean) => ({
    padding: '0.5rem 1.25rem',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    cursor: 'pointer',
    fontSize: '0.875rem',
    fontWeight: active ? 600 : 400,
    background: active ? 'var(--primary)' : 'transparent',
    color: active ? 'white' : 'var(--text-muted)',
    transition: 'all 0.15s',
  });

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: 900, overflowY: 'auto', height: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
          Maximo 查詢知識庫
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: '0.25rem 0 0' }}>
          管理 NL→SQL 的領域規則與查詢範例，自動注入 AI 提示
        </p>
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
        {[
          { icon: Education, label: '領域規則', count: rules.length, color: '#0f62fe' },
          { icon: DataBase, label: '查詢範例', count: examples.length, color: '#42be65' },
        ].map(({ icon: Icon, label, count, color }) => (
          <div key={label} style={{
            flex: 1, padding: '1rem 1.25rem',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            display: 'flex', alignItems: 'center', gap: '0.75rem',
          }}>
            <div style={{ color, background: `${color}18`, borderRadius: 8, padding: 8, display: 'flex' }}>
              <Icon size={20} />
            </div>
            <div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{count}</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{label}</div>
            </div>
          </div>
        ))}
        <button
          onClick={fetchKnowledge}
          style={{ padding: '0 1rem', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <Renew size={16} />
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.25rem', background: 'var(--bg-secondary)', padding: 4, borderRadius: 'var(--radius-sm)', width: 'fit-content' }}>
        <button style={tabStyle(activeTab === 'rules')} onClick={() => setActiveTab('rules')}>
          領域規則 ({rules.length})
        </button>
        <button style={tabStyle(activeTab === 'examples')} onClick={() => setActiveTab('examples')}>
          查詢範例 ({examples.length})
        </button>
      </div>

      {/* Rules Tab */}
      {activeTab === 'rules' && (
        <div>
          {/* Add Rule */}
          <div style={{
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', padding: '1rem', marginBottom: '1rem',
          }}>
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>新增領域規則</div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input
                value={newRule}
                onChange={e => setNewRule(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addRule()}
                placeholder='例：工單通常掛在車組的 assetnum 上，不是子車廂'
                style={{
                  flex: 1, padding: '0.5rem 0.75rem', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
                  color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none',
                }}
              />
              <button
                onClick={addRule}
                disabled={!newRule.trim() || saving}
                style={{
                  padding: '0.5rem 1rem', background: 'var(--primary)', color: 'white',
                  border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                  opacity: !newRule.trim() ? 0.45 : 1,
                }}
              >
                <Add size={16} /> 新增
              </button>
            </div>
          </div>

          {/* Rules List */}
          {loading ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>載入中...</div>
          ) : rules.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>尚無規則</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', paddingRight: 4 }}>
              {rules.map(r => (
                <div key={r.id} style={{
                  display: 'flex', alignItems: 'flex-start', gap: '0.75rem',
                  padding: '0.75rem 1rem', background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                }}>
                  <span style={{ color: 'var(--accent)', fontSize: '1rem', lineHeight: 1.5 }}>•</span>
                  <span style={{ flex: 1, fontSize: '0.875rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                    {r.content}
                  </span>
                  <button
                    onClick={() => deleteRule(r.id)}
                    style={{ color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4, flexShrink: 0 }}
                    onMouseEnter={e => (e.currentTarget.style.color = '#da1e28')}
                    onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
                  >
                    <TrashCan size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Examples Tab */}
      {activeTab === 'examples' && (
        <div>
          {/* Add Example */}
          <div style={{
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', padding: '1rem', marginBottom: '1rem',
          }}>
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>新增查詢範例</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <input
                value={newQ}
                onChange={e => setNewQ(e.target.value)}
                placeholder='問：EMU900 有幾組車組？'
                style={{
                  padding: '0.5rem 0.75rem', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
                  color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none',
                }}
              />
              <textarea
                value={newSQL}
                onChange={e => setNewSQL(e.target.value)}
                placeholder={'SQL：SELECT COUNT(*) FROM maximo_assets WHERE ...'}
                rows={3}
                style={{
                  padding: '0.5rem 0.75rem', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
                  color: 'var(--text-primary)', fontSize: '0.8125rem', outline: 'none',
                  resize: 'vertical', fontFamily: 'monospace',
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  onClick={addExample}
                  disabled={!newQ.trim() || !newSQL.trim() || saving}
                  style={{
                    padding: '0.5rem 1rem', background: 'var(--primary)', color: 'white',
                    border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 6,
                    opacity: (!newQ.trim() || !newSQL.trim()) ? 0.45 : 1,
                  }}
                >
                  <Add size={16} /> 新增
                </button>
              </div>
            </div>
          </div>

          {/* Examples List */}
          {loading ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>載入中...</div>
          ) : examples.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>尚無範例</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', paddingRight: 4 }}>
              {examples.map(ex => (
                <div key={ex.id} style={{
                  background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)', overflow: 'hidden',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.625rem 1rem', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ fontSize: '0.875rem', color: 'var(--text-primary)', fontWeight: 500 }}>
                      {ex.question}
                    </span>
                    <button
                      onClick={() => deleteExample(ex.id)}
                      style={{ color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 4, borderRadius: 4 }}
                      onMouseEnter={e => (e.currentTarget.style.color = '#da1e28')}
                      onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
                    >
                      <TrashCan size={14} />
                    </button>
                  </div>
                  <pre style={{
                    margin: 0, padding: '0.625rem 1rem',
                    fontSize: '0.75rem', color: 'var(--text-secondary)',
                    fontFamily: 'monospace', whiteSpace: 'pre-wrap', lineHeight: 1.6,
                    background: 'var(--bg-primary)',
                  }}>{ex.sql_query}</pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
