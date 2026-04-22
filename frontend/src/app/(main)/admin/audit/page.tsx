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
  ChatLaunch,
} from '@carbon/icons-react';
import { apiGet, apiRequest } from '@/lib/api';

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
  conversation_id: string | null;
  recovery_path?: string | null;
}

interface RewriteAttempt {
  attempt: number;
  query: string;
  reason: string;
  success: boolean;
  ms: number;
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
  // SQL rewrite history fields
  original_question?: string | null;
  rewrite_history?: RewriteAttempt[] | null;
  recovery_path?: string | null;
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
  const [collapsedConversations, setCollapsedConversations] = useState<Record<string, boolean>>({});
  const pageSize = 20;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (filter !== 'all') params.set('type_filter', filter);
      const data = await apiGet<{ logs: AuditLog[]; total: number }>(`/api/admin/audit-logs?${params}`);
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
        const d = await apiGet<AuditDetail>(`/api/admin/audit-logs/${log.id}?type=${log.type}`);
        setDetails(prev => ({ ...prev, [key]: d }));
        if (d.request_id) {
          try {
            const traceData = await apiGet<CallTrace[]>(`/api/admin/call-traces/${d.request_id}`);
            setTraces(prev => ({ ...prev, [key]: traceData }));
            if (traceData.length > 0) {
              setTraceOpen(prev => ({ ...prev, [key]: true }));
            }
          } catch { /* traces are non-critical */ }
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
                {(() => {
                  // Group logs by conversation_id
                  const groups: { convId: string | null; logs: AuditLog[] }[] = [];
                  const convMap = new Map<string, AuditLog[]>();
                  const ungrouped: AuditLog[] = [];

                  for (const log of logs) {
                    if (log.conversation_id) {
                      if (!convMap.has(log.conversation_id)) convMap.set(log.conversation_id, []);
                      convMap.get(log.conversation_id)!.push(log);
                    } else {
                      ungrouped.push(log);
                    }
                  }

                  // Build ordered groups preserving original order
                  const seen = new Set<string>();
                  for (const log of logs) {
                    if (log.conversation_id && !seen.has(log.conversation_id)) {
                      seen.add(log.conversation_id);
                      groups.push({ convId: log.conversation_id, logs: convMap.get(log.conversation_id)! });
                    } else if (!log.conversation_id) {
                      groups.push({ convId: null, logs: [log] });
                    }
                  }

                  const renderLogRow = (log: AuditLog, indented = false) => {
                    const key = `${log.type}-${log.id}`;
                    const isExpanded = expandedId === key;
                    const det = details[key];
                    const isLoadingDet = loadingDetail === key;

                    return (
                      <React.Fragment key={key}>
                        <tr
                          onClick={() => toggleExpand(log)}
                          style={{
                            cursor: 'pointer',
                            ...(indented ? {
                              borderLeft: '3px solid var(--accent)',
                              background: 'rgba(80,144,211,0.04)',
                            } : {}),
                          }}
                        >
                          <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', paddingLeft: indented ? '2rem' : undefined }}>
                            {indented && <span style={{ color: 'var(--accent)', marginRight: '0.25rem' }}>┗</span>}
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
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', maxWidth: 300 }}>
                              <div style={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                flex: 1,
                              }}>
                                {log.query}
                              </div>
                              {log.recovery_path === 'sql_retry' && (
                                <span style={{
                                  flexShrink: 0,
                                  padding: '1px 6px',
                                  borderRadius: 99,
                                  fontSize: '0.625rem',
                                  fontWeight: 600,
                                  background: 'rgba(255,152,0,0.15)',
                                  color: '#e68900',
                                  whiteSpace: 'nowrap',
                                }}>
                                  SQL 改寫重試
                                </span>
                              )}
                              {log.recovery_path === 'rag_fallback' && (
                                <span style={{
                                  flexShrink: 0,
                                  padding: '1px 6px',
                                  borderRadius: 99,
                                  fontSize: '0.625rem',
                                  fontWeight: 600,
                                  background: 'rgba(218,30,40,0.12)',
                                  color: '#da1e28',
                                  whiteSpace: 'nowrap',
                                }}>
                                  轉 RAG
                                </span>
                              )}
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
                                    {traces[key]?.length > 0 && !det.execution_ms && (
                                      <div style={{ marginBottom: '0.5rem' }}>
                                        <strong>總耗時：</strong>
                                        {(traces[key].reduce((sum, t) => sum + (t.duration_ms || 0), 0) / 1000).toFixed(1)}s
                                        （{traces[key].length} 步驟）
                                      </div>
                                    )}
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
                  };

                  return groups.map((group, gi) => {
                    if (!group.convId || group.logs.length === 1) {
                      return renderLogRow(group.logs[0]);
                    }

                    const isCollapsed = collapsedConversations[group.convId] !== false;
                    const shortId = group.convId.slice(0, 8);
                    const toggleCollapse = () =>
                      setCollapsedConversations(prev => ({ ...prev, [group.convId!]: !isCollapsed }));

                    return (
                      <React.Fragment key={`conv-${group.convId}`}>
                        <tr
                          onClick={toggleCollapse}
                          style={{
                            cursor: 'pointer',
                            background: 'var(--bg-tertiary, #f4f4f4)',
                          }}
                        >
                          <td colSpan={7} style={{ padding: '0.5rem 1rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                              <ChatLaunch size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                對話 #{shortId}
                              </span>
                              <span style={{
                                padding: '1px 6px',
                                borderRadius: 99,
                                fontSize: '0.6875rem',
                                fontWeight: 600,
                                background: 'rgba(33,150,243,0.12)',
                                color: '#1976d2',
                              }}>
                                {group.logs.length} 筆查詢
                              </span>
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                {relativeTime(group.logs[0].created_at)}
                              </span>
                              <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>
                                {isCollapsed
                                  ? <ChevronDown size={14} />
                                  : <ChevronUp size={14} />}
                              </span>
                            </div>
                          </td>
                        </tr>
                        {!isCollapsed && group.logs.map(log => renderLogRow(log, true))}
                      </React.Fragment>
                    );
                  });
                })()}
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
      {detail.recovery_path && detail.recovery_path !== 'direct' && (
        <DetailRow label="Recovery" value={
          <span style={{
            padding: '1px 6px',
            borderRadius: 99,
            fontSize: '0.6875rem',
            fontWeight: 600,
            background: detail.recovery_path === 'sql_retry' ? 'rgba(255,152,0,0.15)' : 'rgba(218,30,40,0.12)',
            color: detail.recovery_path === 'sql_retry' ? '#e68900' : '#da1e28',
          }}>
            {detail.recovery_path === 'sql_retry' ? 'SQL 改寫重試' : detail.recovery_path === 'rag_fallback' ? '轉 RAG Fallback' : detail.recovery_path}
          </span>
        } />
      )}
      {detail.original_question && (
        <DetailRow label="原始問題" value={
          <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            {detail.original_question}
          </span>
        } />
      )}
      {detail.rewrite_history && detail.rewrite_history.length > 0 && (
        <div style={{ marginTop: '0.75rem' }}>
          <div style={{
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            marginBottom: '0.5rem',
          }}>
            改寫歷程
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {detail.rewrite_history.map((attempt, idx) => (
              <div key={idx} style={{
                padding: '0.5rem 0.75rem',
                background: 'var(--bg-primary)',
                borderRadius: 'var(--radius-md)',
                border: `1px solid ${attempt.success ? 'rgba(25,128,56,0.3)' : 'rgba(218,30,40,0.2)'}`,
                fontSize: '0.8125rem',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                  <span style={{
                    padding: '1px 6px',
                    borderRadius: 99,
                    fontSize: '0.625rem',
                    fontWeight: 700,
                    background: attempt.success ? 'rgba(25,128,56,0.12)' : 'rgba(218,30,40,0.12)',
                    color: attempt.success ? '#198038' : '#da1e28',
                  }}>
                    #{attempt.attempt} {attempt.success ? '成功' : '失敗'}
                  </span>
                  {attempt.ms > 0 && (
                    <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                      {attempt.ms}ms
                    </span>
                  )}
                </div>
                {attempt.reason && (
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: '0.25rem' }}>
                    原因：{attempt.reason}
                  </div>
                )}
                <div style={{
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  wordBreak: 'break-all',
                }}>
                  {attempt.query}
                </div>
              </div>
            ))}
          </div>
        </div>
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
