'use client';

import { useState, useEffect, useRef } from 'react';
import { Add, TrashCan, Renew, DataBase, Education, Tag, Edit, Checkmark, Close } from '@carbon/icons-react';

const API = '';

const TAGS = [
  { value: 'general',      label: '通用',     color: '#6f6f6f' },
  { value: 'asset',        label: '資產',     color: '#0f62fe' },
  { value: 'workorder',    label: '工單',     color: '#42be65' },
  { value: 'fault_report', label: '故障報告', color: '#ff832b' },
];

const tagMeta = (value: string) => TAGS.find(t => t.value === value) ?? TAGS[0];

interface Rule    { id: number; content: string; tag: string; }
interface Example { id: number; question: string; sql_query: string; verified: boolean; tag: string; }
interface EditState { id: number; type: 'rule' | 'example'; }

function TagBadge({ tag }: { tag: string }) {
  const m = tagMeta(tag);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '1px 8px', borderRadius: 99,
      fontSize: '0.6875rem', fontWeight: 600,
      background: `${m.color}18`, color: m.color,
      flexShrink: 0,
    }}>
      {m.label}
    </span>
  );
}

function TagSelect({ value, onChange, small }: { value: string; onChange: (v: string) => void; small?: boolean }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        padding: small ? '0.25rem 0.5rem' : '0.5rem 0.625rem',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
        color: 'var(--text-primary)', fontSize: small ? '0.8125rem' : '0.875rem',
        outline: 'none', cursor: 'pointer',
      }}
    >
      {TAGS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
    </select>
  );
}

export default function MaximoKnowledgePage() {
  const [rules, setRules]       = useState<Rule[]>([]);
  const [examples, setExamples] = useState<Example[]>([]);
  const [loading, setLoading]   = useState(true);
  const [newRule, setNewRule]   = useState('');
  const [newRuleTag, setNewRuleTag] = useState('general');
  const [newQ, setNewQ]         = useState('');
  const [newSQL, setNewSQL]     = useState('');
  const [newExTag, setNewExTag] = useState('general');
  const [saving, setSaving]     = useState(false);
  const [activeTab, setActiveTab] = useState<'rules' | 'examples'>('rules');
  const [filterTag, setFilterTag] = useState<string>('all');

  // Inline edit state
  const [editing, setEditing] = useState<EditState | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editQ, setEditQ]     = useState('');
  const [editSQL, setEditSQL] = useState('');
  const [editTag, setEditTag] = useState('general');

  const fetchKnowledge = async () => {
    setLoading(true);
    try {
      const res  = await fetch(`${API}/api/maximo/knowledge`);
      const data = await res.json();
      setRules(data.rules || []);
      setExamples(data.examples || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchKnowledge(); }, []);

  const startEditRule = (r: Rule) => {
    setEditing({ id: r.id, type: 'rule' });
    setEditContent(r.content);
    setEditTag(r.tag);
  };

  const startEditExample = (ex: Example) => {
    setEditing({ id: ex.id, type: 'example' });
    setEditQ(ex.question);
    setEditSQL(ex.sql_query);
    setEditTag(ex.tag);
  };

  const cancelEdit = () => setEditing(null);

  const saveEditRule = async (id: number) => {
    if (!editContent.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/maximo/knowledge/rule/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent, tag: editTag }),
      });
      if (res.ok) {
        setRules(rs => rs.map(r => r.id === id ? { ...r, content: editContent, tag: editTag } : r));
        setEditing(null);
      }
    } finally { setSaving(false); }
  };

  const saveEditExample = async (id: number) => {
    if (!editQ.trim() || !editSQL.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/maximo/knowledge/example/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: editQ, sql_query: editSQL, tag: editTag }),
      });
      if (res.ok) {
        setExamples(es => es.map(e => e.id === id ? { ...e, question: editQ, sql_query: editSQL, tag: editTag } : e));
        setEditing(null);
      }
    } finally { setSaving(false); }
  };

  const addRule = async () => {
    if (!newRule.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/maximo/knowledge/rule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newRule, tag: newRuleTag }),
      });
      if (res.ok) { setNewRule(''); await fetchKnowledge(); }
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
        body: JSON.stringify({ question: newQ, sql_query: newSQL, tag: newExTag }),
      });
      if (res.ok) { setNewQ(''); setNewSQL(''); await fetchKnowledge(); }
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

  const chipStyle = (active: boolean, color?: string) => ({
    padding: '0.25rem 0.875rem',
    borderRadius: 99,
    border: `1px solid ${active ? (color ?? 'var(--primary)') : 'var(--border)'}`,
    cursor: 'pointer',
    fontSize: '0.8125rem',
    fontWeight: active ? 600 : 400,
    background: active ? `${color ?? 'var(--primary)'}18` : 'transparent',
    color: active ? (color ?? 'var(--primary)') : 'var(--text-muted)',
    transition: 'all 0.15s',
  });

  const iconBtnStyle = (color?: string) => ({
    color: color ?? 'var(--text-muted)', background: 'none', border: 'none',
    cursor: 'pointer', padding: 4, borderRadius: 4, flexShrink: 0 as const,
    display: 'flex', alignItems: 'center',
  });

  const filteredRules    = filterTag === 'all' ? rules    : rules.filter(r => r.tag === filterTag);
  const filteredExamples = filterTag === 'all' ? examples : examples.filter(e => e.tag === filterTag);

  const tagCounts = (items: { tag: string }[]) =>
    TAGS.reduce((acc, t) => ({ ...acc, [t.value]: items.filter(i => i.tag === t.value).length }), {} as Record<string, number>);

  const currentItems  = activeTab === 'rules' ? rules : examples;
  const counts        = tagCounts(currentItems);

  return (
    <div style={{ padding: '1.5rem 2rem', overflowY: 'auto', height: '100%' }}>
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
          { icon: Education, label: '領域規則', count: rules.length,    color: '#0f62fe' },
          { icon: DataBase,  label: '查詢範例', count: examples.length, color: '#42be65' },
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
      <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1rem', background: 'var(--bg-secondary)', padding: 4, borderRadius: 'var(--radius-sm)', width: 'fit-content' }}>
        <button style={tabStyle(activeTab === 'rules')}    onClick={() => { setActiveTab('rules');    setFilterTag('all'); setEditing(null); }}>
          領域規則 ({rules.length})
        </button>
        <button style={tabStyle(activeTab === 'examples')} onClick={() => { setActiveTab('examples'); setFilterTag('all'); setEditing(null); }}>
          查詢範例 ({examples.length})
        </button>
      </div>

      {/* Tag Filter Chips */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <Tag size={14} style={{ color: 'var(--text-muted)' }} />
        <button style={chipStyle(filterTag === 'all')} onClick={() => setFilterTag('all')}>
          全部 ({currentItems.length})
        </button>
        {TAGS.map(t => (
          <button
            key={t.value}
            style={chipStyle(filterTag === t.value, t.color)}
            onClick={() => setFilterTag(filterTag === t.value ? 'all' : t.value)}
          >
            {t.label} {counts[t.value] > 0 ? `(${counts[t.value]})` : ''}
          </button>
        ))}
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
              <TagSelect value={newRuleTag} onChange={setNewRuleTag} />
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
          ) : filteredRules.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>尚無規則</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', paddingRight: 4 }}>
              {filteredRules.map(r => {
                const isEditing = editing?.id === r.id && editing.type === 'rule';
                return (
                  <div key={r.id} style={{
                    padding: '0.75rem 1rem', background: 'var(--bg-secondary)',
                    border: `1px solid ${isEditing ? 'var(--primary)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius-sm)',
                  }}>
                    {isEditing ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          <TagSelect value={editTag} onChange={setEditTag} small />
                          <input
                            autoFocus
                            value={editContent}
                            onChange={e => setEditContent(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') saveEditRule(r.id); if (e.key === 'Escape') cancelEdit(); }}
                            style={{
                              flex: 1, padding: '0.375rem 0.625rem', border: '1px solid var(--primary)',
                              borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
                              color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none',
                            }}
                          />
                          <button onClick={() => saveEditRule(r.id)} disabled={saving} style={{ ...iconBtnStyle('#42be65') }}>
                            <Checkmark size={16} />
                          </button>
                          <button onClick={cancelEdit} style={iconBtnStyle()}>
                            <Close size={16} />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                        <span style={{ color: 'var(--accent)', fontSize: '1rem', lineHeight: 1.5 }}>•</span>
                        <span style={{ flex: 1, fontSize: '0.875rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                          {r.content}
                        </span>
                        <TagBadge tag={r.tag} />
                        <button
                          onClick={() => startEditRule(r)}
                          style={iconBtnStyle()}
                          onMouseEnter={e => (e.currentTarget.style.color = 'var(--primary)')}
                          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
                        >
                          <Edit size={14} />
                        </button>
                        <button
                          onClick={() => deleteRule(r.id)}
                          style={iconBtnStyle()}
                          onMouseEnter={e => (e.currentTarget.style.color = '#da1e28')}
                          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
                        >
                          <TrashCan size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
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
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <TagSelect value={newExTag} onChange={setNewExTag} />
                <input
                  value={newQ}
                  onChange={e => setNewQ(e.target.value)}
                  placeholder='問：EMU900 有幾組車組？'
                  style={{
                    flex: 1, padding: '0.5rem 0.75rem', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
                    color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none',
                  }}
                />
              </div>
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
          ) : filteredExamples.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>尚無範例</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', paddingRight: 4 }}>
              {filteredExamples.map(ex => {
                const isEditing = editing?.id === ex.id && editing.type === 'example';
                return (
                  <div key={ex.id} style={{
                    background: 'var(--bg-secondary)',
                    border: `1px solid ${isEditing ? 'var(--primary)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius-md)', overflow: 'hidden',
                  }}>
                    {isEditing ? (
                      <div style={{ padding: '0.75rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          <TagSelect value={editTag} onChange={setEditTag} small />
                          <input
                            autoFocus
                            value={editQ}
                            onChange={e => setEditQ(e.target.value)}
                            style={{
                              flex: 1, padding: '0.375rem 0.625rem', border: '1px solid var(--primary)',
                              borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
                              color: 'var(--text-primary)', fontSize: '0.875rem', outline: 'none',
                            }}
                          />
                        </div>
                        <textarea
                          value={editSQL}
                          onChange={e => setEditSQL(e.target.value)}
                          rows={4}
                          style={{
                            padding: '0.375rem 0.625rem', border: '1px solid var(--primary)',
                            borderRadius: 'var(--radius-sm)', background: 'var(--bg-primary)',
                            color: 'var(--text-primary)', fontSize: '0.8125rem', outline: 'none',
                            resize: 'vertical', fontFamily: 'monospace',
                          }}
                        />
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                          <button onClick={cancelEdit} style={{ padding: '0.375rem 0.75rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8125rem' }}>
                            取消
                          </button>
                          <button
                            onClick={() => saveEditExample(ex.id)}
                            disabled={saving || !editQ.trim() || !editSQL.trim()}
                            style={{ padding: '0.375rem 0.875rem', background: 'var(--primary)', color: 'white', border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: 4 }}
                          >
                            <Checkmark size={14} /> 儲存
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.625rem 1rem', borderBottom: '1px solid var(--border)', gap: '0.5rem' }}>
                          <span style={{ fontSize: '0.875rem', color: 'var(--text-primary)', fontWeight: 500, flex: 1 }}>
                            {ex.question}
                          </span>
                          <TagBadge tag={ex.tag} />
                          <button
                            onClick={() => startEditExample(ex)}
                            style={iconBtnStyle()}
                            onMouseEnter={e => (e.currentTarget.style.color = 'var(--primary)')}
                            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
                          >
                            <Edit size={14} />
                          </button>
                          <button
                            onClick={() => deleteExample(ex.id)}
                            style={iconBtnStyle()}
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
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
