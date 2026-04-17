'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Renew,
  InProgress,
  ErrorFilled,
  Checkmark,
  Close,
  DataTable,
} from '@carbon/icons-react';
import { STREAM_API_URL, getApiHeaders } from '@/lib/api';

interface PendingExample {
  id: number;
  question: string;
  sql: string;
  submitted_by: string | null;
  status: 'pending' | 'approved' | 'rejected';
  notes: string | null;
  created_at: string | null;
}

type StatusFilter = 'pending' | 'approved' | 'rejected';

function relativeTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    const now = Date.now();
    const then = new Date(iso).getTime();
    const diffSec = Math.floor((now - then) / 1000);
    if (diffSec < 60) return '剛剛';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} 分鐘前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} 小時前`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 7) return `${diffDay} 天前`;
    const d = new Date(iso);
    return d.toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

export default function PendingExamplesPage() {
  const [filter, setFilter] = useState<StatusFilter>('pending');
  const [examples, setExamples] = useState<PendingExample[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const fetchExamples = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/pending-examples?status=${filter}`, {
        headers: getApiHeaders(),
      });
      if (!res.ok) throw new Error(`載入失敗 (${res.status})`);
      const data = await res.json();
      setExamples(Array.isArray(data) ? data : data.examples || []);
    } catch (e: any) {
      setError(e.message || '載入失敗');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchExamples();
  }, [fetchExamples]);

  const handleApprove = async (id: number) => {
    setActionLoading(id);
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/pending-examples/${id}/approve`, {
        method: 'PUT',
        headers: getApiHeaders(),
      });
      if (!res.ok) throw new Error(`操作失敗 (${res.status})`);
      await fetchExamples();
    } catch (e: any) {
      alert(e.message || '操作失敗');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: number) => {
    const notes = window.prompt('請輸入拒絕原因：');
    if (notes === null) return;
    setActionLoading(id);
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/pending-examples/${id}/reject`, {
        method: 'PUT',
        headers: getApiHeaders(),
        body: JSON.stringify({ notes }),
      });
      if (!res.ok) throw new Error(`操作失敗 (${res.status})`);
      await fetchExamples();
    } catch (e: any) {
      alert(e.message || '操作失敗');
    } finally {
      setActionLoading(null);
    }
  };

  const handleFilterChange = (f: StatusFilter) => {
    setFilter(f);
  };

  const filters: { key: StatusFilter; label: string }[] = [
    { key: 'pending', label: '待審' },
    { key: 'approved', label: '已通過' },
    { key: 'rejected', label: '已拒絕' },
  ];

  return (
    <div style={{
      height: '100%',
      overflow: 'auto',
      background: 'var(--bg-primary)',
      padding: '1.5rem 2rem',
    }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{
          fontSize: '1.5rem',
          fontWeight: 700,
          color: 'var(--text-primary)',
          marginBottom: '0.25rem',
        }}>
          SQL 範例審核
        </h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          審核使用者提交的 NL→SQL 校正範例
        </p>
      </div>

      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1.5rem',
        borderBottom: '1px solid var(--border)',
        paddingBottom: '0.5rem',
      }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {filters.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => handleFilterChange(key)}
              style={{
                padding: '0.625rem 1.25rem',
                background: filter === key ? 'var(--accent)' : 'transparent',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                color: filter === key ? 'white' : 'var(--text-muted)',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
                fontSize: '0.875rem',
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={fetchExamples}
          title="重新載入"
          style={{
            display: 'flex', alignItems: 'center', gap: '0.375rem',
            padding: '0.5rem 1rem', fontSize: '0.8125rem',
            color: 'var(--text-muted)', background: 'var(--bg-tertiary)',
            border: 'none', borderRadius: 'var(--radius-md)', cursor: 'pointer',
          }}
        >
          <Renew size={16} />
          重新載入
        </button>
      </div>

      {loading ? (
        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <InProgress size={32} className="spinner" style={{ color: 'var(--accent)', marginBottom: '0.75rem' }} />
          <div>載入中...</div>
        </div>
      ) : error ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--error)' }}>
          <ErrorFilled size={32} style={{ marginBottom: '0.75rem' }} />
          <div>{error}</div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ minWidth: 780 }}>
              <thead>
                <tr>
                  <th style={{ width: 250 }}>問題</th>
                  <th>SQL</th>
                  <th style={{ width: 140 }}>提交者</th>
                  <th style={{ width: 110 }}>提交時間</th>
                  {filter === 'pending' && (
                    <th style={{ width: 140, textAlign: 'center' }}>操作</th>
                  )}
                  {filter === 'rejected' && (
                    <th style={{ width: 200 }}>拒絕原因</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {examples.map((ex) => (
                  <tr key={ex.id}>
                    <td style={{ fontSize: '0.8125rem', color: 'var(--text-primary)' }}>
                      <div style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        maxWidth: 250,
                      }}>
                        {ex.question}
                      </div>
                    </td>
                    <td>
                      <pre style={{
                        margin: 0,
                        fontFamily: 'monospace',
                        fontSize: '0.75rem',
                        color: 'var(--text-secondary)',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                        maxWidth: 350,
                      }}>
                        {ex.sql}
                      </pre>
                    </td>
                    <td style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                      {ex.submitted_by || '—'}
                    </td>
                    <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {relativeTime(ex.created_at)}
                    </td>
                    {filter === 'pending' && (
                      <td style={{ textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                          <button
                            onClick={() => handleApprove(ex.id)}
                            disabled={actionLoading === ex.id}
                            style={{
                              display: 'flex', alignItems: 'center', gap: '0.25rem',
                              padding: '0.375rem 0.75rem',
                              background: '#198038',
                              color: 'white',
                              border: 'none',
                              borderRadius: 'var(--radius-md)',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: actionLoading === ex.id ? 'not-allowed' : 'pointer',
                              opacity: actionLoading === ex.id ? 0.6 : 1,
                            }}
                          >
                            <Checkmark size={14} />
                            通過
                          </button>
                          <button
                            onClick={() => handleReject(ex.id)}
                            disabled={actionLoading === ex.id}
                            style={{
                              display: 'flex', alignItems: 'center', gap: '0.25rem',
                              padding: '0.375rem 0.75rem',
                              background: '#da1e28',
                              color: 'white',
                              border: 'none',
                              borderRadius: 'var(--radius-md)',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: actionLoading === ex.id ? 'not-allowed' : 'pointer',
                              opacity: actionLoading === ex.id ? 0.6 : 1,
                            }}
                          >
                            <Close size={14} />
                            拒絕
                          </button>
                        </div>
                      </td>
                    )}
                    {filter === 'rejected' && (
                      <td style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                        {ex.notes || '—'}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>

            {examples.length === 0 && (
              <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                <DataTable size={40} style={{ marginBottom: '0.75rem', opacity: 0.4 }} />
                <div>
                  {filter === 'pending' ? '目前沒有待審範例' :
                   filter === 'approved' ? '尚無已通過的範例' : '尚無已拒絕的範例'}
                </div>
              </div>
            )}
          </div>

          {examples.length > 0 && (
            <div style={{
              padding: '0.75rem 1.5rem',
              borderTop: '1px solid var(--border)',
              background: 'var(--bg-secondary)',
              fontSize: '0.8125rem',
              color: 'var(--text-muted)',
            }}>
              共 {examples.length} 筆記錄
            </div>
          )}
        </div>
      )}
    </div>
  );
}
