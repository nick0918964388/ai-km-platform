'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Add,
  TrashCan,
  Edit,
  Checkmark,
  Close,
  Renew,
  InProgress,
  ErrorFilled,
  ChevronRight,
  ChevronDown,
  Flash,
  PlayFilledAlt,
  PauseFilled,
} from '@carbon/icons-react';
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api';

// ── Types ────────────────────────────────────────────────────────────────────

interface SkillSecurity {
  allowed_roles?: string[];
  row_filter?: boolean;
}

interface SkillStats {
  usage_count?: number;
  success_rate?: number;
  last_used?: string;
}

interface Skill {
  id: string;
  name: string;
  version: number;
  is_current: boolean;
  active: boolean;
  description: string;
  triggers: string[];
  sql_template: string;
  params_schema: Record<string, unknown>;
  security: SkillSecurity;
  stats: SkillStats;
}

interface SeedResult {
  created: number;
  skipped: number;
  failed: number;
}

interface SkillFormState {
  name: string;
  description: string;
  triggersText: string;       // one trigger per line
  sql_template: string;
  params_schema_text: string; // JSON string
  allowed_roles: string[];
  row_filter: boolean;
  active: boolean;
}

const ALL_ROLES = ['admin', 'maint_manager', 'maint_tech', 'analyst', 'viewer'];

const EMPTY_FORM: SkillFormState = {
  name: '',
  description: '',
  triggersText: '',
  sql_template: '',
  params_schema_text: '{}',
  allowed_roles: [],
  row_filter: false,
  active: true,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatPct(rate?: number): string {
  if (rate == null) return '—';
  return `${Math.round(rate * 100)}%`;
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

function triggersPreview(triggers: string[]): string {
  if (!triggers || triggers.length === 0) return '—';
  const first2 = triggers.slice(0, 2).join('、');
  return triggers.length > 2 ? `${first2}…` : first2;
}

function skillToForm(skill: Skill): SkillFormState {
  return {
    name: skill.name,
    description: skill.description || '',
    triggersText: (skill.triggers || []).join('\n'),
    sql_template: skill.sql_template || '',
    params_schema_text: JSON.stringify(skill.params_schema || {}, null, 2),
    allowed_roles: skill.security?.allowed_roles || [],
    row_filter: skill.security?.row_filter ?? false,
    active: skill.active,
  };
}

function formToPayload(form: SkillFormState) {
  let params_schema: Record<string, unknown> = {};
  try { params_schema = JSON.parse(form.params_schema_text); } catch { /* keep empty */ }
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    triggers: form.triggersText.split('\n').map(t => t.trim()).filter(Boolean),
    sql_template: form.sql_template.trim(),
    params_schema,
    security: {
      allowed_roles: form.allowed_roles.length > 0 ? form.allowed_roles : undefined,
      row_filter: form.row_filter,
    },
    active: form.active,
  };
}

function validateForm(form: SkillFormState): string | null {
  if (!form.name.trim()) return 'name 為必填';
  const triggers = form.triggersText.split('\n').map(t => t.trim()).filter(Boolean);
  if (triggers.length === 0) return '至少需要一個觸發句';
  const sql = form.sql_template.trim().toUpperCase();
  if (!sql) return 'SQL 模板為必填';
  if (!sql.startsWith('SELECT') && !sql.startsWith('WITH')) return 'SQL 模板必須以 SELECT 或 WITH 開頭';
  try { JSON.parse(form.params_schema_text); } catch { return 'params_schema 不是合法 JSON'; }
  return null;
}

// ── Inline style helpers (matching existing admin pages) ──────────────────────

const tabStyle = (active: boolean) => ({
  padding: '0.625rem 1.25rem',
  background: active ? 'var(--accent)' : 'transparent',
  border: 'none',
  borderRadius: 'var(--radius-md)',
  color: active ? 'white' : 'var(--text-muted)',
  fontWeight: 500,
  cursor: 'pointer' as const,
  display: 'flex' as const,
  alignItems: 'center' as const,
  gap: '0.5rem',
  transition: 'all var(--transition-fast)',
  fontSize: '0.875rem',
});

const inputStyle = {
  width: '100%',
  padding: '0.5rem 0.75rem',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  fontSize: '0.875rem',
  outline: 'none',
  boxSizing: 'border-box' as const,
};

const labelStyle = {
  fontSize: '0.8125rem',
  color: 'var(--text-muted)',
  marginBottom: '0.375rem',
  display: 'block' as const,
};

// ── SkillForm ─────────────────────────────────────────────────────────────────

interface SkillFormProps {
  form: SkillFormState;
  onChange: (f: SkillFormState) => void;
  editingVersion?: number; // if set, show "will create v{N+1}" notice
}

function SkillForm({ form, onChange, editingVersion }: SkillFormProps) {
  const set = <K extends keyof SkillFormState>(k: K, v: SkillFormState[K]) =>
    onChange({ ...form, [k]: v });

  const toggleRole = (role: string) => {
    const next = form.allowed_roles.includes(role)
      ? form.allowed_roles.filter(r => r !== role)
      : [...form.allowed_roles, role];
    set('allowed_roles', next);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {editingVersion != null && (
        <div style={{
          padding: '0.5rem 0.875rem',
          background: 'rgba(15,98,254,0.08)',
          border: '1px solid rgba(15,98,254,0.25)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '0.8125rem',
          color: 'var(--accent)',
        }}>
          儲存後將建立 v{editingVersion + 1}，舊版本保留為歷史記錄
        </div>
      )}

      {/* name */}
      <div>
        <label style={labelStyle}>name <span style={{ color: 'var(--error)' }}>*</span></label>
        <input
          style={inputStyle}
          value={form.name}
          onChange={e => set('name', e.target.value)}
          placeholder="例：query_fault_by_vehicle（slug 格式）"
        />
      </div>

      {/* description */}
      <div>
        <label style={labelStyle}>描述</label>
        <textarea
          style={{ ...inputStyle, resize: 'vertical', minHeight: 60 }}
          value={form.description}
          onChange={e => set('description', e.target.value)}
          placeholder="這個 Skill 的用途說明"
          rows={2}
        />
      </div>

      {/* triggers */}
      <div>
        <label style={labelStyle}>觸發句 <span style={{ color: 'var(--error)' }}>*</span> <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>（每行一個）</span></label>
        <textarea
          style={{ ...inputStyle, resize: 'vertical', minHeight: 80, fontFamily: 'inherit' }}
          value={form.triggersText}
          onChange={e => set('triggersText', e.target.value)}
          placeholder={'查詢 {vehicle} 的故障記錄\n{vehicle_type} 的維修費用統計'}
          rows={4}
        />
      </div>

      {/* sql_template */}
      <div>
        <label style={labelStyle}>SQL 模板 <span style={{ color: 'var(--error)' }}>*</span> <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>（使用 :param 佔位符）</span></label>
        <textarea
          style={{ ...inputStyle, resize: 'vertical', minHeight: 120, fontFamily: 'monospace', fontSize: '0.8125rem' }}
          value={form.sql_template}
          onChange={e => set('sql_template', e.target.value)}
          placeholder={'SELECT * FROM maximo_fault_reports\nWHERE assetnum = :vehicle\nORDER BY reportdate DESC\nLIMIT 50'}
          rows={6}
        />
      </div>

      {/* params_schema */}
      <div>
        <label style={labelStyle}>params_schema <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>（JSON，選填）</span></label>
        <textarea
          style={{ ...inputStyle, resize: 'vertical', minHeight: 60, fontFamily: 'monospace', fontSize: '0.8125rem' }}
          value={form.params_schema_text}
          onChange={e => set('params_schema_text', e.target.value)}
          rows={3}
        />
      </div>

      {/* security: allowed_roles */}
      <div>
        <label style={labelStyle}>allowed_roles <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>（空 = 全部角色允許）</span></label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {ALL_ROLES.map(role => {
            const checked = form.allowed_roles.includes(role);
            return (
              <button
                key={role}
                type="button"
                onClick={() => toggleRole(role)}
                style={{
                  padding: '0.25rem 0.75rem',
                  borderRadius: 99,
                  border: `1px solid ${checked ? 'var(--accent)' : 'var(--border)'}`,
                  background: checked ? 'rgba(15,98,254,0.12)' : 'transparent',
                  color: checked ? 'var(--accent)' : 'var(--text-muted)',
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                  fontWeight: checked ? 600 : 400,
                  transition: 'all 0.12s',
                }}
              >
                {role}
              </button>
            );
          })}
        </div>
      </div>

      {/* security: row_filter + active */}
      <div style={{ display: 'flex', gap: '2rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem', color: 'var(--text-primary)' }}>
          <input
            type="checkbox"
            checked={form.row_filter}
            onChange={e => set('row_filter', e.target.checked)}
            style={{ width: 16, height: 16, cursor: 'pointer', accentColor: 'var(--accent)' }}
          />
          row_filter
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem', color: 'var(--text-primary)' }}>
          <input
            type="checkbox"
            checked={form.active}
            onChange={e => set('active', e.target.checked)}
            style={{ width: 16, height: 16, cursor: 'pointer', accentColor: 'var(--accent)' }}
          />
          active
        </label>
      </div>
    </div>
  );
}

// ── SkillDrawer ───────────────────────────────────────────────────────────────

interface DrawerProps {
  skill: Skill;
  onClose: () => void;
  onUpdated: (s: Skill) => void;
  onDeleted: (id: string) => void;
}

function SkillDrawer({ skill, onClose, onUpdated, onDeleted }: DrawerProps) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<SkillFormState>(skillToForm(skill));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Sync when skill changes externally (e.g. toggle active from table)
  useEffect(() => {
    setForm(skillToForm(skill));
    setEditing(false);
    setError('');
  }, [skill.id]);

  const handleSave = async () => {
    const err = validateForm(form);
    if (err) { setError(err); return; }
    setSaving(true);
    setError('');
    try {
      const updated = await apiPut<Skill>(`/api/admin/skills/${skill.id}`, formToPayload(form));
      onUpdated(updated);
      setEditing(false);
    } catch (e: any) {
      setError(e.message || '儲存失敗');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`確定停用 skill「${skill.name}」？（soft delete，可重新建立）`)) return;
    setSaving(true);
    try {
      await apiDelete(`/api/admin/skills/${skill.id}`);
      onDeleted(skill.id);
    } catch (e: any) {
      setError(e.message || '停用失敗');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, bottom: 0,
      width: 'min(520px, 100vw)',
      background: 'var(--bg-primary)',
      borderLeft: '1px solid var(--border)',
      boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
      zIndex: 200,
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Drawer header */}
      <div style={{
        padding: '1rem 1.25rem',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: '0.75rem', flexShrink: 0,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {skill.name}
            </span>
            <span style={{
              padding: '1px 8px', borderRadius: 99, fontSize: '0.6875rem', fontWeight: 700,
              background: 'rgba(15,98,254,0.12)', color: 'var(--accent)',
            }}>
              v{skill.version}
            </span>
            {!skill.active && (
              <span style={{
                padding: '1px 8px', borderRadius: 99, fontSize: '0.6875rem', fontWeight: 600,
                background: 'rgba(218,30,40,0.1)', color: 'var(--error)',
              }}>
                inactive
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {skill.description || '無描述'}
          </div>
        </div>
        <button
          className="btn-icon"
          onClick={onClose}
          title="關閉"
          style={{ flexShrink: 0, color: 'var(--text-muted)' }}
        >
          <Close size={18} />
        </button>
      </div>

      {/* Drawer body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem' }}>
        {editing ? (
          <>
            {error && (
              <div style={{
                padding: '0.5rem 0.875rem', marginBottom: '1rem',
                background: 'rgba(218,30,40,0.08)', border: '1px solid rgba(218,30,40,0.2)',
                borderRadius: 'var(--radius-sm)', fontSize: '0.8125rem', color: 'var(--error)',
              }}>
                {error}
              </div>
            )}
            <SkillForm form={form} onChange={setForm} editingVersion={skill.version} />
          </>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Stats */}
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem',
            }}>
              {[
                { label: '使用次數', value: skill.stats?.usage_count ?? '—' },
                { label: '成功率', value: formatPct(skill.stats?.success_rate) },
                { label: '最後使用', value: formatDate(skill.stats?.last_used) },
              ].map(({ label, value }) => (
                <div key={label} style={{
                  padding: '0.625rem 0.75rem',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  textAlign: 'center' as const,
                }}>
                  <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>{String(value)}</div>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
                </div>
              ))}
            </div>

            {/* Triggers */}
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.5rem' }}>
                觸發句 ({(skill.triggers || []).length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                {(skill.triggers || []).map((t, i) => (
                  <div key={i} style={{
                    padding: '0.375rem 0.625rem',
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.8125rem',
                    color: 'var(--text-primary)',
                  }}>
                    {t}
                  </div>
                ))}
                {(!skill.triggers || skill.triggers.length === 0) && (
                  <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>無觸發句</span>
                )}
              </div>
            </div>

            {/* SQL template */}
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.5rem' }}>
                SQL 模板
              </div>
              <pre style={{
                margin: 0, padding: '0.75rem',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                fontFamily: 'monospace', fontSize: '0.75rem',
                color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                lineHeight: 1.6,
              }}>
                {skill.sql_template || '—'}
              </pre>
            </div>

            {/* params_schema */}
            {skill.params_schema && Object.keys(skill.params_schema).length > 0 && (
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.5rem' }}>
                  params_schema
                </div>
                <pre style={{
                  margin: 0, padding: '0.75rem',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'monospace', fontSize: '0.75rem',
                  color: 'var(--text-secondary)', whiteSpace: 'pre-wrap',
                  lineHeight: 1.6,
                }}>
                  {JSON.stringify(skill.params_schema, null, 2)}
                </pre>
              </div>
            )}

            {/* Security */}
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.5rem' }}>
                安全設定
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                {(skill.security?.allowed_roles || []).length === 0 ? (
                  <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>全部角色</span>
                ) : (
                  (skill.security.allowed_roles || []).map(r => (
                    <span key={r} style={{
                      padding: '2px 8px', borderRadius: 99,
                      fontSize: '0.75rem', fontWeight: 600,
                      background: 'rgba(15,98,254,0.1)', color: 'var(--accent)',
                    }}>
                      {r}
                    </span>
                  ))
                )}
                {skill.security?.row_filter && (
                  <span style={{
                    padding: '2px 8px', borderRadius: 99,
                    fontSize: '0.75rem', fontWeight: 600,
                    background: 'rgba(255,131,43,0.12)', color: '#ff832b',
                  }}>
                    row_filter
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Drawer footer */}
      <div style={{
        padding: '0.875rem 1.25rem',
        borderTop: '1px solid var(--border)',
        display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', flexShrink: 0,
        background: 'var(--bg-secondary)',
      }}>
        {editing ? (
          <>
            <button
              onClick={() => { setEditing(false); setForm(skillToForm(skill)); setError(''); }}
              disabled={saving}
              style={{
                padding: '0.5rem 1rem', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', background: 'transparent',
                color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8125rem',
              }}
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '0.5rem 1rem', background: 'var(--accent)', color: 'white',
                border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: 6,
                opacity: saving ? 0.65 : 1,
              }}
            >
              {saving ? <InProgress size={14} className="spinner" /> : <Checkmark size={14} />}
              儲存
            </button>
          </>
        ) : (
          <>
            <button
              onClick={handleDelete}
              disabled={saving || !skill.active}
              title={!skill.active ? '已停用' : '停用此 Skill'}
              style={{
                padding: '0.5rem 1rem', border: '1px solid rgba(218,30,40,0.35)',
                borderRadius: 'var(--radius-sm)', background: 'transparent',
                color: 'var(--error)', cursor: skill.active ? 'pointer' : 'not-allowed',
                fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: 6,
                opacity: !skill.active || saving ? 0.5 : 1,
              }}
            >
              <TrashCan size={14} />
              停用
            </button>
            <button
              onClick={() => { setEditing(true); setForm(skillToForm(skill)); setError(''); }}
              style={{
                padding: '0.5rem 1rem', background: 'var(--accent)', color: 'white',
                border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              <Edit size={14} />
              編輯
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── CreateModal ───────────────────────────────────────────────────────────────

interface CreateModalProps {
  onClose: () => void;
  onCreated: (s: Skill) => void;
}

function CreateModal({ onClose, onCreated }: CreateModalProps) {
  const [form, setForm] = useState<SkillFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    const err = validateForm(form);
    if (err) { setError(err); return; }
    setSaving(true);
    setError('');
    try {
      const created = await apiPost<Skill>('/api/admin/skills', formToPayload(form));
      onCreated(created);
    } catch (e: any) {
      setError(e.message || '建立失敗');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 300,
        }}
      />
      {/* Modal */}
      <div style={{
        position: 'fixed', top: '50%', left: '50%',
        transform: 'translate(-50%,-50%)',
        width: 'min(600px, calc(100vw - 2rem))',
        maxHeight: 'calc(100vh - 4rem)',
        background: 'var(--bg-primary)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: '0 8px 40px rgba(0,0,0,0.24)',
        zIndex: 301,
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Modal header */}
        <div style={{
          padding: '1rem 1.25rem',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>新增 Skill</div>
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: 2 }}>建立一個新的 NL→SQL Skill</div>
          </div>
          <button className="btn-icon" onClick={onClose} style={{ color: 'var(--text-muted)' }}>
            <Close size={18} />
          </button>
        </div>

        {/* Modal body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem' }}>
          {error && (
            <div style={{
              padding: '0.5rem 0.875rem', marginBottom: '1rem',
              background: 'rgba(218,30,40,0.08)', border: '1px solid rgba(218,30,40,0.2)',
              borderRadius: 'var(--radius-sm)', fontSize: '0.8125rem', color: 'var(--error)',
            }}>
              {error}
            </div>
          )}
          <SkillForm form={form} onChange={setForm} />
        </div>

        {/* Modal footer */}
        <div style={{
          padding: '0.875rem 1.25rem',
          borderTop: '1px solid var(--border)',
          display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', flexShrink: 0,
          background: 'var(--bg-secondary)',
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '0.5rem 1rem', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', background: 'transparent',
              color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8125rem',
            }}
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            style={{
              padding: '0.5rem 1.25rem', background: 'var(--accent)', color: 'white',
              border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
              fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: 6,
              opacity: saving ? 0.65 : 1,
            }}
          >
            {saving ? <InProgress size={14} className="spinner" /> : <Add size={14} />}
            建立 Skill
          </button>
        </div>
      </div>
    </>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedResult, setSeedResult] = useState<SeedResult | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiGet<{ skills: Skill[] }>('/api/admin/skills?only_current=true&limit=200');
      setSkills(data.skills || []);
    } catch (e: any) {
      setError(e.message || '載入失敗');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  const filteredSkills = skills.filter(s => {
    const matchSearch = !search || s.name.toLowerCase().includes(search.toLowerCase()) ||
      (s.description || '').toLowerCase().includes(search.toLowerCase());
    const matchActive = showInactive ? true : s.active;
    return matchSearch && matchActive;
  });

  const selectedSkill = selectedId ? skills.find(s => s.id === selectedId) ?? null : null;

  const handleToggleActive = async (skill: Skill, e: React.MouseEvent) => {
    e.stopPropagation();
    if (togglingId) return;
    setTogglingId(skill.id);
    try {
      if (skill.active) {
        // Soft delete = deactivate
        await apiDelete(`/api/admin/skills/${skill.id}`);
        setSkills(prev => prev.map(s => s.id === skill.id ? { ...s, active: false } : s));
        if (selectedId === skill.id) setSelectedId(null);
      } else {
        // Re-activate via PUT
        const updated = await apiPut<Skill>(`/api/admin/skills/${skill.id}`, {
          name: skill.name,
          description: skill.description,
          triggers: skill.triggers,
          sql_template: skill.sql_template,
          params_schema: skill.params_schema,
          security: skill.security,
          active: true,
        });
        setSkills(prev => prev.map(s => s.id === skill.id ? updated : s));
      }
    } catch (e: any) {
      alert(e.message || '操作失敗');
    } finally {
      setTogglingId(null);
    }
  };

  const handleSeed = async () => {
    if (!confirm('從 nl_sql_examples 批次 seed Skills？已存在同名 Skill 將略過。')) return;
    setSeeding(true);
    setSeedResult(null);
    try {
      const result = await apiPost<SeedResult>('/api/admin/skills/seed', {});
      setSeedResult(result);
      await fetchSkills();
    } catch (e: any) {
      alert(e.message || 'Seed 失敗');
    } finally {
      setSeeding(false);
    }
  };

  const handleCreated = (skill: Skill) => {
    setSkills(prev => [skill, ...prev]);
    setShowCreate(false);
    setSelectedId(skill.id);
  };

  const handleUpdated = (updated: Skill) => {
    setSkills(prev => prev.map(s => s.id === updated.id ? updated : s));
  };

  const handleDeleted = (id: string) => {
    setSkills(prev => prev.map(s => s.id === id ? { ...s, active: false } : s));
    setSelectedId(null);
  };

  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--bg-primary)', padding: '1.5rem 2rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
          Skills 管理
        </h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: 0 }}>
          管理 NL→SQL Skill 模板（v2 pipeline，命中率 80%，0 LLM cost）
        </p>
      </div>

      {/* Stats bar */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {[
          { label: '全部 Skills', value: skills.length, color: '#0f62fe' },
          { label: '啟用中', value: skills.filter(s => s.active).length, color: '#42be65' },
          { label: '已停用', value: skills.filter(s => !s.active).length, color: '#6f6f6f' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            padding: '0.875rem 1.25rem',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            display: 'flex', alignItems: 'center', gap: '0.75rem',
          }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{
        display: 'flex', gap: '0.75rem', marginBottom: '1.25rem',
        flexWrap: 'wrap', alignItems: 'center',
      }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="搜尋 Skill 名稱或描述..."
          style={{
            flex: '1 1 220px', padding: '0.5rem 0.75rem',
            border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
            background: 'var(--bg-secondary)', color: 'var(--text-primary)',
            fontSize: '0.875rem', outline: 'none',
          }}
        />
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.875rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          <input
            type="checkbox"
            checked={showInactive}
            onChange={e => setShowInactive(e.target.checked)}
            style={{ width: 15, height: 15, cursor: 'pointer', accentColor: 'var(--accent)' }}
          />
          顯示停用
        </label>
        <button
          onClick={fetchSkills}
          title="重新載入"
          style={{
            display: 'flex', alignItems: 'center', gap: '0.375rem',
            padding: '0.5rem 0.875rem', fontSize: '0.8125rem',
            color: 'var(--text-muted)', background: 'var(--bg-secondary)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', cursor: 'pointer',
          }}
        >
          <Renew size={15} />
        </button>
        <button
          onClick={handleSeed}
          disabled={seeding}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.375rem',
            padding: '0.5rem 1rem', fontSize: '0.8125rem',
            color: seeding ? 'var(--text-muted)' : 'var(--text-primary)',
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', cursor: seeding ? 'wait' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {seeding ? <InProgress size={14} className="spinner" /> : <Flash size={14} />}
          從 nl_sql_examples 重 seed
        </button>
        <button
          onClick={() => setShowCreate(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.375rem',
            padding: '0.5rem 1.125rem', fontSize: '0.875rem', fontWeight: 600,
            color: 'white', background: 'var(--accent)',
            border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          <Add size={16} />
          新增 Skill
        </button>
      </div>

      {/* Seed result banner */}
      {seedResult && (
        <div style={{
          padding: '0.625rem 1rem', marginBottom: '1rem',
          background: 'rgba(66,190,101,0.08)', border: '1px solid rgba(66,190,101,0.25)',
          borderRadius: 'var(--radius-sm)', fontSize: '0.8125rem', color: '#24a148',
          display: 'flex', alignItems: 'center', gap: '0.5rem',
        }}>
          <Checkmark size={14} />
          Seed 完成：新增 {seedResult.created} 個、略過 {seedResult.skipped} 個、失敗 {seedResult.failed} 個
          <button onClick={() => setSeedResult(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#24a148' }}>
            <Close size={14} />
          </button>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <InProgress size={32} className="spinner" style={{ color: 'var(--accent)', marginBottom: '0.75rem' }} />
          <div>載入 Skills...</div>
        </div>
      ) : error ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--error)' }}>
          <ErrorFilled size={32} style={{ marginBottom: '0.75rem' }} />
          <div>{error}</div>
          <button
            onClick={fetchSkills}
            style={{ marginTop: '1rem', padding: '0.5rem 1.25rem', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer', fontSize: '0.875rem' }}
          >
            重試
          </button>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ minWidth: 680 }}>
              <thead>
                <tr>
                  <th style={{ width: 28 }} />
                  <th>名稱</th>
                  <th style={{ width: 52, textAlign: 'center' }}>版本</th>
                  <th>觸發句預覽</th>
                  <th style={{ width: 80, textAlign: 'right' }}>使用次數</th>
                  <th style={{ width: 72, textAlign: 'right' }}>成功率</th>
                  <th style={{ width: 80, textAlign: 'center' }}>啟用</th>
                  <th style={{ width: 72, textAlign: 'center' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredSkills.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      <Flash size={36} style={{ marginBottom: '0.75rem', opacity: 0.3, display: 'block', margin: '0 auto 0.75rem' }} />
                      {search ? `找不到「${search}」相關的 Skill` : '尚無 Skill，點「新增 Skill」或「重 seed」'}
                    </td>
                  </tr>
                ) : (
                  filteredSkills.map(skill => {
                    const isSelected = selectedId === skill.id;
                    const isExpanded = expandedRow === skill.id;
                    return (
                      <React.Fragment key={skill.id}>
                        <tr
                          style={{
                            cursor: 'pointer',
                            background: isSelected ? 'rgba(15,98,254,0.06)' : undefined,
                            opacity: skill.active ? 1 : 0.55,
                          }}
                          onClick={() => setSelectedId(isSelected ? null : skill.id)}
                        >
                          {/* expand chevron */}
                          <td style={{ paddingRight: 0, color: 'var(--text-muted)' }}
                            onClick={e => { e.stopPropagation(); setExpandedRow(isExpanded ? null : skill.id); }}
                          >
                            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </td>

                          {/* name */}
                          <td>
                            <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                              {skill.name}
                            </div>
                            {skill.description && (
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 260 }}>
                                {skill.description}
                              </div>
                            )}
                          </td>

                          {/* version */}
                          <td style={{ textAlign: 'center' }}>
                            <span style={{
                              padding: '1px 7px', borderRadius: 99,
                              fontSize: '0.6875rem', fontWeight: 700,
                              background: 'rgba(15,98,254,0.1)', color: 'var(--accent)',
                            }}>
                              v{skill.version}
                            </span>
                          </td>

                          {/* triggers preview */}
                          <td style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', maxWidth: 240 }}>
                            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {triggersPreview(skill.triggers)}
                            </div>
                          </td>

                          {/* usage_count */}
                          <td style={{ textAlign: 'right', fontSize: '0.875rem', color: 'var(--text-primary)', fontWeight: 500 }}>
                            {skill.stats?.usage_count ?? '—'}
                          </td>

                          {/* success_rate */}
                          <td style={{ textAlign: 'right', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                            {formatPct(skill.stats?.success_rate)}
                          </td>

                          {/* active toggle */}
                          <td style={{ textAlign: 'center' }} onClick={e => e.stopPropagation()}>
                            <button
                              onClick={e => handleToggleActive(skill, e)}
                              disabled={togglingId === skill.id}
                              title={skill.active ? '點擊停用' : '點擊啟用'}
                              style={{
                                background: 'none', border: 'none', cursor: 'pointer',
                                color: skill.active ? '#42be65' : 'var(--text-muted)',
                                display: 'inline-flex', alignItems: 'center',
                                opacity: togglingId === skill.id ? 0.5 : 1,
                              }}
                            >
                              {togglingId === skill.id
                                ? <InProgress size={18} className="spinner" />
                                : skill.active
                                  ? <PlayFilledAlt size={18} />
                                  : <PauseFilled size={18} />
                              }
                            </button>
                          </td>

                          {/* actions */}
                          <td style={{ textAlign: 'center' }} onClick={e => e.stopPropagation()}>
                            <button
                              className="btn-icon"
                              title="詳情 / 編輯"
                              onClick={() => setSelectedId(isSelected ? null : skill.id)}
                              style={{ color: isSelected ? 'var(--accent)' : 'var(--text-muted)' }}
                            >
                              <Edit size={15} />
                            </button>
                          </td>
                        </tr>

                        {/* Inline expanded SQL preview */}
                        {isExpanded && (
                          <tr>
                            <td colSpan={8} style={{ padding: '0.5rem 1.25rem 1rem', background: 'var(--bg-secondary)' }}>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.375rem', fontWeight: 600 }}>
                                SQL 模板
                              </div>
                              <pre style={{
                                margin: 0, padding: '0.625rem 0.75rem',
                                background: 'var(--bg-primary)', border: '1px solid var(--border)',
                                borderRadius: 'var(--radius-sm)', fontFamily: 'monospace',
                                fontSize: '0.75rem', color: 'var(--text-secondary)',
                                whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.6,
                              }}>
                                {skill.sql_template || '—'}
                              </pre>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {filteredSkills.length > 0 && (
            <div style={{
              padding: '0.75rem 1.5rem',
              borderTop: '1px solid var(--border)',
              background: 'var(--bg-secondary)',
              fontSize: '0.8125rem', color: 'var(--text-muted)',
            }}>
              顯示 {filteredSkills.length} / {skills.length} 個 Skill
            </div>
          )}
        </div>
      )}

      {/* Drawer overlay backdrop */}
      {selectedSkill && (
        <div
          onClick={() => setSelectedId(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.2)', zIndex: 199,
          }}
        />
      )}

      {/* Detail Drawer */}
      {selectedSkill && (
        <SkillDrawer
          skill={selectedSkill}
          onClose={() => setSelectedId(null)}
          onUpdated={handleUpdated}
          onDeleted={handleDeleted}
        />
      )}

      {/* Create Modal */}
      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}
