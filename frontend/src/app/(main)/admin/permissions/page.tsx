'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  UserMultiple,
  Security,
  RecentlyViewed,
  TrashCan,
  Edit,
  Save,
  Checkmark,
  InProgress,
  ErrorFilled,
  Renew,
} from '@carbon/icons-react';
import { apiGet, apiRequest, apiDelete } from '@/lib/api';

interface UserRecord {
  id: string;
  email: string;
  display_name: string;
  role: string;
  last_login: string | null;
  group_name: string | null;
  group_display: string | null;
  section: string | null;
  workshop: string | null;
}

interface PermGroup {
  id: number;
  name: string;
  display_name: string;
  description: string;
}

interface AuditLog {
  user_email: string;
  question: string;
  sql: string;
  tables: string[];
  row_count: number;
  created_at: string | null;
}

interface EditingUser {
  id: string;
  role: string;
  group_name: string;
  section: string;
  workshop: string;
}

const roleLabel = (role: string) => role === 'admin' ? '管理員' : '使用者';
const roleBadgeColor = (role: string) => role === 'admin' ? 'var(--error)' : 'var(--accent)';

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

export default function PermissionsPage() {
  const [activeTab, setActiveTab] = useState<'users' | 'audit'>('users');

  // Users tab state
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [groups, setGroups] = useState<PermGroup[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [usersError, setUsersError] = useState('');
  const [editing, setEditing] = useState<EditingUser | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveOk, setSaveOk] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Audit tab state
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [auditError, setAuditError] = useState('');
  const [expandedSql, setExpandedSql] = useState<number | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoadingUsers(true);
    setUsersError('');
    try {
      const [ud, gd] = await Promise.all([
        apiGet<{ users: UserRecord[] }>('/api/auth/users'),
        apiGet<{ groups: PermGroup[] }>('/api/auth/groups'),
      ]);
      setUsers(ud.users || []);
      setGroups(gd.groups || []);
    } catch (e: any) {
      setUsersError(e.message || '載入失敗');
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  const fetchAudit = useCallback(async () => {
    setLoadingAudit(true);
    setAuditError('');
    try {
      const data = await apiGet<{ logs: AuditLog[] }>('/api/maximo/audit');
      setAuditLogs(data.logs || []);
    } catch (e: any) {
      setAuditError(e.message || '載入失敗');
    } finally {
      setLoadingAudit(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  useEffect(() => {
    if (activeTab === 'audit' && auditLogs.length === 0 && !loadingAudit && !auditError) {
      fetchAudit();
    }
  }, [activeTab, auditLogs.length, loadingAudit, auditError, fetchAudit]);

  const startEdit = (user: UserRecord) => {
    setEditing({
      id: user.id,
      role: user.role,
      group_name: user.group_name || '',
      section: user.section || '',
      workshop: user.workshop || '',
    });
    setSaveOk(false);
  };

  const cancelEdit = () => setEditing(null);

  const handleSave = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      const body: Record<string, string> = { role: editing.role };
      if (editing.group_name) body.group_name = editing.group_name;
      if (editing.section) body.section = editing.section;
      if (editing.workshop) body.workshop = editing.workshop;

      await apiRequest(`/api/auth/users/${editing.id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      setSaveOk(true);
      setEditing(null);
      await fetchUsers();
      setTimeout(() => setSaveOk(false), 2000);
    } catch (e: any) {
      alert(e.message || '儲存失敗');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (userId: string, email: string) => {
    if (!confirm(`確定要刪除使用者「${email}」？此操作無法復原。`)) return;
    setDeleting(userId);
    try {
      await apiDelete(`/api/auth/users/${userId}`);
      setUsers(prev => prev.filter(u => u.id !== userId));
    } catch (e: any) {
      alert(e.message || '刪除失敗');
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div style={{
      height: '100%',
      overflow: 'auto',
      background: 'var(--bg-primary)',
      padding: '1.5rem 2rem',
    }}>
      {/* Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{
          fontSize: '1.5rem',
          fontWeight: 700,
          color: 'var(--text-primary)',
          marginBottom: '0.25rem',
        }}>
          權限管理
        </h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          管理使用者帳號、權限群組及查詢稽核
        </p>
      </div>

      {/* Success banner */}
      {saveOk && (
        <div style={{
          padding: '0.75rem 1.25rem',
          background: 'var(--success-light)',
          border: '1px solid rgba(25,128,56,0.3)',
          borderRadius: 'var(--radius-lg)',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          color: 'var(--success)',
          fontWeight: 500,
          fontSize: '0.875rem',
        }}>
          <Checkmark size={16} />
          已儲存
        </div>
      )}

      {/* Tabs */}
      <div style={{
        display: 'flex',
        gap: '0.5rem',
        marginBottom: '1.5rem',
        borderBottom: '1px solid var(--border)',
        paddingBottom: '0.5rem',
      }}>
        {[
          { key: 'users' as const, label: '使用者管理', icon: UserMultiple },
          { key: 'audit' as const, label: '查詢稽核', icon: RecentlyViewed },
        ].map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: '0.625rem 1.25rem',
              background: activeTab === key ? 'var(--accent)' : 'transparent',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              color: activeTab === key ? 'white' : 'var(--text-muted)',
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all var(--transition-fast)',
              fontSize: '0.875rem',
            }}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab: Users ─────────────────────────────────────────── */}
      {activeTab === 'users' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
            <button
              onClick={fetchUsers}
              title="重新載入"
              style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', padding: '0.5rem 1rem', fontSize: '0.8125rem', color: 'var(--text-muted)', background: 'var(--bg-tertiary)', border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer' }}
            >
              <Renew size={16} />
              重新載入
            </button>
          </div>

          {loadingUsers ? (
            <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              <InProgress size={32} className="spinner" style={{ color: 'var(--accent)', marginBottom: '0.75rem' }} />
              <div>載入使用者列表...</div>
            </div>
          ) : usersError ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--error)' }}>
              <ErrorFilled size={32} style={{ marginBottom: '0.75rem' }} />
              <div>{usersError}</div>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" style={{ minWidth: 720 }}>
                  <thead>
                    <tr>
                      <th>使用者</th>
                      <th>角色</th>
                      <th>權限群組</th>
                      <th>部門 / 工場</th>
                      <th>最後登入</th>
                      <th style={{ width: 100, textAlign: 'center' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(user => {
                      const isEditing = editing?.id === user.id;
                      return (
                        <tr key={user.id}>
                          {/* 使用者 */}
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                              <div style={{
                                width: 36, height: 36, borderRadius: '50%',
                                background: 'var(--accent)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: 'white', fontWeight: 600, fontSize: '0.875rem', flexShrink: 0,
                              }}>
                                {(user.display_name || user.email).charAt(0).toUpperCase()}
                              </div>
                              <div>
                                <div style={{ fontWeight: 500, color: 'var(--text-primary)', fontSize: '0.875rem' }}>
                                  {user.display_name || '—'}
                                </div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{user.email}</div>
                              </div>
                            </div>
                          </td>

                          {/* 角色 */}
                          <td>
                            {isEditing ? (
                              <select
                                value={editing.role}
                                onChange={e => setEditing(prev => prev ? { ...prev, role: e.target.value } : prev)}
                                style={{
                                  padding: '0.25rem 0.5rem',
                                  border: '1px solid var(--border)',
                                  borderRadius: 'var(--radius-sm)',
                                  background: 'var(--bg-primary)',
                                  color: 'var(--text-primary)',
                                  fontSize: '0.8125rem',
                                  cursor: 'pointer',
                                }}
                              >
                                <option value="user">使用者</option>
                                <option value="admin">管理員</option>
                              </select>
                            ) : (
                              <span style={{
                                display: 'inline-block',
                                padding: '0.125rem 0.625rem',
                                borderRadius: 99,
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                background: `${roleBadgeColor(user.role)}22`,
                                color: roleBadgeColor(user.role),
                              }}>
                                {roleLabel(user.role)}
                              </span>
                            )}
                          </td>

                          {/* 權限群組 */}
                          <td>
                            {isEditing ? (
                              <select
                                value={editing.group_name}
                                onChange={e => setEditing(prev => prev ? { ...prev, group_name: e.target.value } : prev)}
                                style={{
                                  padding: '0.25rem 0.5rem',
                                  border: '1px solid var(--border)',
                                  borderRadius: 'var(--radius-sm)',
                                  background: 'var(--bg-primary)',
                                  color: 'var(--text-primary)',
                                  fontSize: '0.8125rem',
                                  cursor: 'pointer',
                                  maxWidth: 140,
                                }}
                              >
                                <option value="">— 不指定 —</option>
                                {groups.map(g => (
                                  <option key={g.id} value={g.name}>{g.display_name || g.name}</option>
                                ))}
                              </select>
                            ) : (
                              <span style={{ fontSize: '0.8125rem', color: user.group_display ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                                {user.group_display || '—'}
                              </span>
                            )}
                          </td>

                          {/* 部門 / 工場 */}
                          <td>
                            {isEditing ? (
                              <div style={{ display: 'flex', gap: '0.375rem' }}>
                                <input
                                  type="text"
                                  placeholder="部門"
                                  value={editing.section}
                                  onChange={e => setEditing(prev => prev ? { ...prev, section: e.target.value } : prev)}
                                  style={{
                                    width: 72,
                                    padding: '0.25rem 0.5rem',
                                    border: '1px solid var(--border)',
                                    borderRadius: 'var(--radius-sm)',
                                    background: 'var(--bg-primary)',
                                    color: 'var(--text-primary)',
                                    fontSize: '0.8125rem',
                                  }}
                                />
                                <input
                                  type="text"
                                  placeholder="工場"
                                  value={editing.workshop}
                                  onChange={e => setEditing(prev => prev ? { ...prev, workshop: e.target.value } : prev)}
                                  style={{
                                    width: 72,
                                    padding: '0.25rem 0.5rem',
                                    border: '1px solid var(--border)',
                                    borderRadius: 'var(--radius-sm)',
                                    background: 'var(--bg-primary)',
                                    color: 'var(--text-primary)',
                                    fontSize: '0.8125rem',
                                  }}
                                />
                              </div>
                            ) : (
                              <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                                {[user.section, user.workshop].filter(Boolean).join(' / ') || '—'}
                              </span>
                            )}
                          </td>

                          {/* 最後登入 */}
                          <td style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                            {formatDateTime(user.last_login)}
                          </td>

                          {/* 操作 */}
                          <td>
                            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.375rem' }}>
                              {isEditing ? (
                                <>
                                  <button
                                    className="btn-icon"
                                    title="儲存"
                                    onClick={handleSave}
                                    disabled={saving}
                                    style={{ color: 'var(--success)' }}
                                  >
                                    {saving ? <InProgress size={16} className="spinner" /> : <Save size={16} />}
                                  </button>
                                  <button
                                    className="btn-icon"
                                    title="取消"
                                    onClick={cancelEdit}
                                    disabled={saving}
                                    style={{ color: 'var(--text-muted)' }}
                                  >
                                    <Security size={16} />
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button
                                    className="btn-icon"
                                    title="編輯"
                                    onClick={() => startEdit(user)}
                                  >
                                    <Edit size={16} />
                                  </button>
                                  <button
                                    className="btn-icon"
                                    title="刪除"
                                    onClick={() => handleDelete(user.id, user.email)}
                                    disabled={deleting === user.id}
                                    style={{ color: 'var(--error)' }}
                                  >
                                    {deleting === user.id
                                      ? <InProgress size={16} className="spinner" />
                                      : <TrashCan size={16} />}
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {users.length === 0 && (
                  <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    <UserMultiple size={40} style={{ marginBottom: '0.75rem', opacity: 0.4 }} />
                    <div>尚無使用者</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Tab: Audit ─────────────────────────────────────────── */}
      {activeTab === 'audit' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
            <button
              onClick={fetchAudit}
              title="重新載入"
              style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', padding: '0.5rem 1rem', fontSize: '0.8125rem', color: 'var(--text-muted)', background: 'var(--bg-tertiary)', border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer' }}
            >
              <Renew size={16} />
              重新載入
            </button>
          </div>

          {loadingAudit ? (
            <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              <InProgress size={32} className="spinner" style={{ color: 'var(--accent)', marginBottom: '0.75rem' }} />
              <div>載入稽核記錄...</div>
            </div>
          ) : auditError ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--error)' }}>
              <ErrorFilled size={32} style={{ marginBottom: '0.75rem' }} />
              <div>{auditError}</div>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" style={{ minWidth: 700 }}>
                  <thead>
                    <tr>
                      <th style={{ width: 130 }}>時間</th>
                      <th style={{ width: 160 }}>使用者</th>
                      <th>問題</th>
                      <th style={{ width: 120 }}>存取表</th>
                      <th style={{ width: 60, textAlign: 'right' }}>筆數</th>
                      <th style={{ width: 60, textAlign: 'center' }}>SQL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.map((log, idx) => (
                      <React.Fragment key={idx}>
                        <tr>
                          <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                            {formatDateTime(log.created_at)}
                          </td>
                          <td style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                            {log.user_email || '—'}
                          </td>
                          <td style={{ fontSize: '0.8125rem', color: 'var(--text-primary)', maxWidth: 280 }}>
                            <div style={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              maxWidth: 280,
                            }}>
                              {log.question}
                            </div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                              {(log.tables || []).map((t: string, ti: number) => (
                                <span key={ti} style={{
                                  display: 'inline-block',
                                  padding: '1px 6px',
                                  borderRadius: 99,
                                  fontSize: '0.6875rem',
                                  fontWeight: 600,
                                  background: 'var(--primary-light)',
                                  color: 'var(--accent)',
                                }}>
                                  {t}
                                </span>
                              ))}
                              {(!log.tables || log.tables.length === 0) && (
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
                              )}
                            </div>
                          </td>
                          <td style={{ textAlign: 'right', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                            {log.row_count ?? '—'}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <button
                              className="btn-icon"
                              title="展開 SQL"
                              onClick={() => setExpandedSql(expandedSql === idx ? null : idx)}
                              style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}
                            >
                              {expandedSql === idx ? '▲' : '▼'}
                            </button>
                          </td>
                        </tr>
                        {expandedSql === idx && log.sql && (
                          <tr>
                            <td colSpan={6} style={{ padding: '0.5rem 1rem 1rem', background: 'var(--bg-secondary)' }}>
                              <pre style={{
                                margin: 0,
                                fontFamily: 'monospace',
                                fontSize: '0.75rem',
                                color: 'var(--text-secondary)',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-all',
                                padding: '0.75rem',
                                background: 'var(--bg-primary)',
                                borderRadius: 'var(--radius-md)',
                                border: '1px solid var(--border)',
                              }}>
                                {log.sql}
                              </pre>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>

                {auditLogs.length === 0 && (
                  <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    <RecentlyViewed size={40} style={{ marginBottom: '0.75rem', opacity: 0.4 }} />
                    <div>尚無查詢記錄</div>
                  </div>
                )}
              </div>

              {auditLogs.length > 0 && (
                <div style={{
                  padding: '0.75rem 1.5rem',
                  borderTop: '1px solid var(--border)',
                  background: 'var(--bg-secondary)',
                  fontSize: '0.8125rem',
                  color: 'var(--text-muted)',
                }}>
                  顯示最近 {auditLogs.length} 筆記錄
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
