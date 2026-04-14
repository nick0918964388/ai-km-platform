'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Renew,
  InProgress,
  ErrorFilled,
  ChevronLeft,
  ChevronRight,
} from '@carbon/icons-react';
import { STREAM_API_URL, getApiHeaders } from '@/lib/api';

interface AuditLog {
  id: number;
  type: 'sql' | 'rag';
  user_email: string | null;
  query: string;
  detail: string | null;
  tables_accessed: string[] | null;
  row_count: number | null;
  duration_ms: number | null;
  mode: string | null;
  cached: boolean | null;
  created_at: string | null;
}

interface AuditDetail {
  type: string;
  request_id?: string;
  // SQL fields
  sql_generated?: string;
  tables_accessed?: string[];
  mode?: string;
  cached?: boolean;
  execution_ms?: number;
  row_count?: number;
  // RAG fields
  search_query?: string;
  top_score?: number;
  avg_score?: number;
  quality?: string;
  rewrite_used?: boolean;
  rewrite_query?: string;
  source_count?: number;
  intent?: string;
}

interface CallTrace {
  step: string;
  status: string;
  duration_ms: number;
  url: string;
  model: string;
  request_body?: string;
  response_body?: string;
  error?: string;
}

type FilterType = 'all' | 'sql' | 'rag';

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

function formatDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function AuditPage() {
  const [filter, setFilter] = useState<FilterType>('all');
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, AuditDetail>>({});
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);
  const [traces, setTraces] = useState<Record<string, CallTrace[]>>({});
  const [traceOpen, setTraceOpen] = useState<Record<string, boolean>>({});
  const toggleTraceView = (id: string) => setTraceOpen(prev => ({ ...prev, [id]: !prev[id] }));
  const pageSize = 20;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (filter !== 'all') params.set('type_filter', filter);
      const res = await fetch(`${STREAM_API_URL}/api/admin/audit-logs?${params}`, {
        headers: getApiHeaders(),
      });
      if (!res.ok) throw new Error(`載入失敗 (${res.status})`);
      const data = await res.json();
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      setError(e.message || '載入失敗');
    } finally {
      setLoading(false);
    }
  }, [page, filter]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleFilterChange = (f: FilterType) => {
    setFilter(f);
    setPage(1);
    setExpandedId(null);
  };

  const toggleExpand = async (log: AuditLog) => {
    const key = `${log.type}-${log.id}`;
    if (expandedId === key) {
      setExpandedId(null);
      return;
    }
    setExpandedId(key);

    if (!details[key]) {
      setLoadingDetail(key);
      try {
        const res = await fetch(
          `${STREAM_API_URL}/api/admin/audit-logs/${log.id}?type=${log.type}`,
          { headers: getApiHeaders() }
        );
        if (res.ok) {
          const d = await res.json();
          setDetails(prev => ({ ...prev, [key]: d }));
          if (d.request_id) {
            const traceRes = await fetch(
              `${STREAM_API_URL}/api/admin/call-traces/${d.request_id}`,
              { headers: getApiHeaders() }
            );
            if (traceRes.ok) {
              const traceData = await traceRes.json();
              setTraces(prev => ({ ...prev, [key]: traceData }));
              if (traceData.length > 0) {
                setTraceOpen(prev => ({ ...prev, [key]: true }));
              }
            }
          }
        }
      } catch { /* ignore */ }
      setLoadingDetail(null);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const filters: { key: FilterType; label: string }[] = [
    { key: 'all', label: '全部' },
    { key: 'sql', label: 'SQL 查詢' },
    { key: 'rag', label: 'RAG 搜尋' },
  ];

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
          稽核日誌
        </h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          管理者查詢稽核與系統呼叫記錄
        </p>
      </div>

      {/* Filter tabs + reload */}
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
          onClick={fetchLogs}
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

      {/* Content */}
      {loading ? (
        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <InProgress size={32} className="spinner" style={{ color: 'var(--accent)', marginBottom: '0.75rem' }} />
          <div>載入稽核記錄...</div>
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
                  <th style={{ width: 110 }}>時間</th>
                  <th style={{ width: 70 }}>類型</th>
                  <th style={{ width: 140 }}>使用者</th>
                  <th>查詢內容</th>
                  <th style={{ width: 80, textAlign: 'right' }}>結果</th>
                  <th style={{ width: 70, textAlign: 'right' }}>耗時</th>
                  <th style={{ width: 50, textAlign: 'center' }}></th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const key = `${log.type}-${log.id}`;
                  const isExpanded = expandedId === key;
                  const det = details[key];
                  const isLoadingDet = loadingDetail === key;

                  return (
                    <React.Fragment key={key}>
                      <tr
                        onClick={() => toggleExpand(log)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                          {relativeTime(log.created_at)}
                        </td>
                        <td>
                          <span style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            borderRadius: 99,
                            fontSize: '0.6875rem',
                            fontWeight: 600,
                            background: log.type === 'sql' ? 'rgba(255,152,0,0.15)' : 'rgba(33,150,243,0.15)',
                            color: log.type === 'sql' ? '#e68900' : '#1976d2',
                          }}>
                            {log.type === 'sql' ? 'SQL' : 'RAG'}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                          {log.user_email || '—'}
                        </td>
                        <td style={{ fontSize: '0.8125rem', color: 'var(--text-primary)', maxWidth: 300 }}>
                          <div style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: 300,
                          }}>
                            {log.query}
                          </div>
                        </td>
                        <td style={{ textAlign: 'right', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                          {log.row_count != null ? `${log.row_count} 筆` : '—'}
                        </td>
                        <td style={{ textAlign: 'right', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                          {formatDuration(log.duration_ms)}
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          {isExpanded
                            ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} />
                            : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr>
                          <td colSpan={7} style={{ padding: 0, background: 'var(--bg-secondary)' }}>
                            <div style={{ padding: '1rem 1.5rem' }}>
                              {isLoadingDet ? (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                                  <InProgress size={16} className="spinner" /> 載入詳情...
                                </div>
                              ) : det ? (
                                <>
                                  {log.type === 'sql' ? (
                                    <SqlDetail detail={det} />
                                  ) : (
                                    <RagDetail detail={det} />
                                  )}
                                  {/* Total duration from traces */}
                                  {traces[key]?.length > 0 && !det.execution_ms && (
                                    <div style={{ marginBottom: '0.5rem' }}>
                                      <strong>總耗時：</strong>
                                      {(traces[key].reduce((sum, t) => sum + (t.duration_ms || 0), 0) / 1000).toFixed(1)}s
                                      （{traces[key].length} 步驟）
                                    </div>
                                  )}
                                  {/* System Call Chain */}
                                  {traces[key]?.length > 0 && (
                                    <div style={{ marginTop: '0.75rem' }}>
                                      <button
                                        onClick={(e) => { e.stopPropagation(); toggleTraceView(key); }}
                                        style={{
                                          background: 'none',
                                          border: 'none',
                                          cursor: 'pointer',
                                          color: 'var(--text-secondary)',
                                          fontSize: '0.8125rem',
                                          fontWeight: 600,
                                          padding: '0.25rem 0',
                                        }}
                                      >
                                        {traceOpen[key] ? '▼' : '▶'} 系統呼叫鏈 ({traces[key].length} calls)
                                      </button>
                                      {traceOpen[key] && (
                                        <div style={{
                                          marginTop: '0.5rem',
                                          background: '#1e1e1e',
                                          borderRadius: 8,
                                          padding: '1rem',
                                          fontFamily: 'monospace',
                                          fontSize: '0.75rem',
                                          color: '#d4d4d4',
                                          maxHeight: 400,
                                          overflow: 'auto',
                                        }}>
                                          {traces[key].map((trace, idx) => (
                                            <div key={idx} style={{ marginBottom: '1rem', borderBottom: '1px solid #333', paddingBottom: '0.75rem' }}>
                                              <div style={{ color: '#569cd6', fontWeight: 'bold' }}>
                                                [{idx + 1}] {trace.step}
                                                <span style={{ color: trace.status === 'ok' ? '#4ec9b0' : '#f44747', marginLeft: 8 }}>
                                                  {trace.status === 'ok' ? '✓' : '✗'} {trace.duration_ms}ms
                                                </span>
                                              </div>
                                              <div style={{ color: '#9cdcfe', marginTop: 4 }}>
                                                URL: {trace.url}
                                              </div>
                                              <div style={{ color: '#9cdcfe' }}>
                                                Model: {trace.model}
                                              </div>
                                              {trace.request_body && (
                                                <details style={{ marginTop: 4 }}>
                                                  <summary style={{ cursor: 'pointer', color: '#dcdcaa' }}>Request Body</summary>
                                                  <pre style={{
                                                    whiteSpace: 'pre-wrap',
                                                    wordBreak: 'break-all',
                                                    color: '#ce9178',
                                                    margin: '4px 0',
                                                    padding: '0.5rem',
                                                    background: '#2d2d2d',
                                                    borderRadius: 4,
                                                    maxHeight: 200,
                                                    overflow: 'auto',
                                                  }}>{trace.request_body}</pre>
                                                </details>
                                              )}
                                              {trace.response_body && (
                                                <details style={{ marginTop: 4 }}>
                                                  <summary style={{ cursor: 'pointer', color: '#dcdcaa' }}>Response</summary>
                                                  <pre style={{
                                                    whiteSpace: 'pre-wrap',
                                                    wordBreak: 'break-all',
                                                    color: '#b5cea8',
                                                    margin: '4px 0',
                                                    padding: '0.5rem',
                                                    background: '#2d2d2d',
                                                    borderRadius: 4,
                                                    maxHeight: 200,
                                                    overflow: 'auto',
                                                  }}>{trace.response_body}</pre>
                                                </details>
                                              )}
                                              {trace.error && (
                                                <div style={{ color: '#f44747', marginTop: 4 }}>
                                                  Error: {trace.error}
                                                </div>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </>
                              ) : (
                                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                                  無詳細資料
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>

            {logs.length === 0 && (
              <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                <Activity size={40} style={{ marginBottom: '0.75rem', opacity: 0.4 }} />
                <div>尚無稽核記錄</div>
              </div>
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '0.75rem 1.5rem',
              borderTop: '1px solid var(--border)',
              background: 'var(--bg-secondary)',
              fontSize: '0.8125rem',
              color: 'var(--text-muted)',
            }}>
              <span>共 {total} 筆，第 {page}/{totalPages} 頁</span>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(p => p - 1)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.25rem',
                    padding: '0.375rem 0.75rem',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--bg-primary)',
                    color: page <= 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                    cursor: page <= 1 ? 'not-allowed' : 'pointer',
                    opacity: page <= 1 ? 0.5 : 1,
                    fontSize: '0.8125rem',
                  }}
                >
                  <ChevronLeft size={14} /> 上一頁
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage(p => p + 1)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.25rem',
                    padding: '0.375rem 0.75rem',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--bg-primary)',
                    color: page >= totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                    cursor: page >= totalPages ? 'not-allowed' : 'pointer',
                    opacity: page >= totalPages ? 0.5 : 1,
                    fontSize: '0.8125rem',
                  }}
                >
                  下一頁 <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}

          {logs.length > 0 && totalPages <= 1 && (
            <div style={{
              padding: '0.75rem 1.5rem',
              borderTop: '1px solid var(--border)',
              background: 'var(--bg-secondary)',
              fontSize: '0.8125rem',
              color: 'var(--text-muted)',
            }}>
              共 {total} 筆記錄
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.8125rem', marginBottom: '0.375rem' }}>
      <span style={{ color: 'var(--text-muted)', minWidth: 90, flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

function SqlDetail({ detail }: { detail: AuditDetail }) {
  return (
    <div>
      {detail.sql_generated && (
        <pre style={{
          margin: '0 0 0.75rem',
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
          {detail.sql_generated}
        </pre>
      )}
      <DetailRow label="Tables" value={
        detail.tables_accessed?.length
          ? detail.tables_accessed.map((t, i) => (
              <span key={i} style={{
                display: 'inline-block',
                padding: '1px 6px',
                borderRadius: 99,
                fontSize: '0.6875rem',
                fontWeight: 600,
                background: 'var(--primary-light)',
                color: 'var(--accent)',
                marginRight: '0.25rem',
              }}>
                {t}
              </span>
            ))
          : '—'
      } />
      <DetailRow label="Mode" value={detail.mode || '—'} />
      <DetailRow label="Cached" value={detail.cached ? 'Yes' : 'No'} />
      {detail.execution_ms != null && (
        <DetailRow label="Execution" value={`${detail.execution_ms.toFixed(0)}ms`} />
      )}
      {detail.row_count != null && (
        <DetailRow label="Rows" value={`${detail.row_count} 筆`} />
      )}
    </div>
  );
}

function RagDetail({ detail }: { detail: AuditDetail }) {
  return (
    <div>
      <DetailRow label="Search Query" value={detail.search_query || '—'} />
      <DetailRow label="Top Score" value={detail.top_score != null ? detail.top_score.toFixed(4) : '—'} />
      <DetailRow label="Avg Score" value={detail.avg_score != null ? detail.avg_score.toFixed(4) : '—'} />
      <DetailRow label="Quality" value={
        detail.quality ? (
          <span style={{
            display: 'inline-block',
            padding: '1px 6px',
            borderRadius: 99,
            fontSize: '0.6875rem',
            fontWeight: 600,
            background: detail.quality === 'good' ? 'rgba(25,128,56,0.15)' : detail.quality === 'low' ? 'rgba(255,152,0,0.15)' : 'rgba(218,30,40,0.15)',
            color: detail.quality === 'good' ? '#198038' : detail.quality === 'low' ? '#e68900' : '#da1e28',
          }}>
            {detail.quality}
          </span>
        ) : '—'
      } />
      <DetailRow label="Rewrite" value={detail.rewrite_used ? 'Yes' : 'No'} />
      {detail.rewrite_query && (
        <DetailRow label="Rewrite Query" value={detail.rewrite_query} />
      )}
      {detail.source_count != null && (
        <DetailRow label="Sources" value={`${detail.source_count} 筆文件`} />
      )}
      {detail.intent && (
        <DetailRow label="Intent" value={detail.intent} />
      )}
    </div>
  );
}
