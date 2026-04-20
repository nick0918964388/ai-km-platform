'use client';

import { useState, useCallback } from 'react';
import {
  Activity,
  Renew,
  InProgress,
  ErrorFilled,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
} from '@carbon/icons-react';
import type { AuditEntry } from '@/types/pgViewer';
import { usePgViewerAudit } from '@/hooks/usePgViewerAudit';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZES = [10, 50, 100] as const;

type QueryType = 'schema' | 'table_browse' | 'sql_editor';
type AuditStatus = 'ok' | 'error' | 'timeout' | 'forbidden' | 'rate_limited';

const QUERY_TYPE_OPTIONS: { value: QueryType | ''; label: string }[] = [
  { value: '', label: '全部類型' },
  { value: 'schema', label: 'schema' },
  { value: 'table_browse', label: 'table_browse' },
  { value: 'sql_editor', label: 'sql_editor' },
];

const STATUS_OPTIONS: { value: AuditStatus | ''; label: string }[] = [
  { value: '', label: '全部狀態' },
  { value: 'ok', label: 'ok' },
  { value: 'error', label: 'error' },
  { value: 'timeout', label: 'timeout' },
  { value: 'forbidden', label: 'forbidden' },
  { value: 'rate_limited', label: 'rate_limited' },
];

// ---------------------------------------------------------------------------
// Status tag colors
// ---------------------------------------------------------------------------

function statusStyle(status: string | undefined): { background: string; color: string } {
  switch (status) {
    case 'ok':
      return { background: 'rgba(25,128,56,0.15)', color: '#198038' };
    case 'error':
      return { background: 'rgba(218,30,40,0.15)', color: '#da1e28' };
    case 'forbidden':
      return { background: 'rgba(218,30,40,0.12)', color: '#b81921' };
    case 'timeout':
      return { background: 'rgba(136,38,218,0.15)', color: '#8a3ffc' };
    case 'rate_limited':
      return { background: 'rgba(255,131,0,0.15)', color: '#e68900' };
    default:
      return { background: 'var(--bg-tertiary)', color: 'var(--text-muted)' };
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDateTime(iso: string | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-TW', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatMs(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function truncate(text: string | null | undefined, len = 80): string {
  if (!text) return '—';
  if (text.length <= len) return text;
  return text.slice(0, len) + '…';
}

// ---------------------------------------------------------------------------
// SQL modal
// ---------------------------------------------------------------------------

function SqlModal({
  sql,
  onClose,
}: {
  sql: string;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="完整 SQL"
      data-testid="sql-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9000,
        padding: '2rem',
      }}
    >
      <div
        style={{
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-light)',
          borderRadius: 10,
          padding: '1.5rem',
          maxWidth: 720,
          width: '100%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span
            style={{
              fontWeight: 600,
              fontSize: '0.9375rem',
              color: 'var(--text-primary)',
            }}
          >
            完整 SQL
          </span>
          <button
            onClick={onClose}
            aria-label="關閉"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              fontSize: '1.25rem',
              lineHeight: 1,
              padding: '0.25rem 0.5rem',
              borderRadius: 4,
            }}
          >
            ×
          </button>
        </div>
        <pre
          style={{
            flex: 1,
            overflowY: 'auto',
            fontFamily: 'monospace',
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-light)',
            borderRadius: 6,
            padding: '1rem',
            margin: 0,
          }}
        >
          {sql}
        </pre>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter row
// ---------------------------------------------------------------------------

interface FilterState {
  userId: string;
  queryType: string;
  status: string;
  since: string;
  until: string;
}

function FilterRow({
  filter,
  onChange,
}: {
  filter: FilterState;
  onChange: (next: FilterState) => void;
}) {
  const inputStyle: React.CSSProperties = {
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border-light)',
    borderRadius: 4,
    padding: '0.375rem 0.625rem',
    fontSize: '0.8125rem',
    color: 'var(--text-primary)',
    fontFamily: 'inherit',
    outline: 'none',
  };

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: 'pointer',
  };

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '0.625rem',
        padding: '0.875rem 1.25rem',
        borderBottom: '1px solid var(--border-light)',
        background: 'var(--bg-secondary)',
        alignItems: 'center',
        flexShrink: 0,
      }}
    >
      {/* User ID */}
      <input
        type="text"
        placeholder="User ID"
        value={filter.userId}
        onChange={(e) => onChange({ ...filter, userId: e.target.value })}
        aria-label="Filter by user ID"
        data-testid="filter-user-id"
        style={{ ...inputStyle, width: 160 }}
      />

      {/* Query type */}
      <select
        value={filter.queryType}
        onChange={(e) => onChange({ ...filter, queryType: e.target.value })}
        aria-label="Filter by query type"
        data-testid="filter-query-type"
        style={selectStyle}
      >
        {QUERY_TYPE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      {/* Status */}
      <select
        value={filter.status}
        onChange={(e) => onChange({ ...filter, status: e.target.value })}
        aria-label="Filter by status"
        data-testid="filter-status"
        style={selectStyle}
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      {/* Date range */}
      <input
        type="datetime-local"
        value={filter.since}
        onChange={(e) => onChange({ ...filter, since: e.target.value })}
        aria-label="Filter since date"
        data-testid="filter-since"
        style={inputStyle}
      />
      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>—</span>
      <input
        type="datetime-local"
        value={filter.until}
        onChange={(e) => onChange({ ...filter, until: e.target.value })}
        aria-label="Filter until date"
        data-testid="filter-until"
        style={inputStyle}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sort state
// ---------------------------------------------------------------------------

type SortDir = 'desc' | 'asc';

// ---------------------------------------------------------------------------
// Table header cell with sort toggle
// ---------------------------------------------------------------------------

function SortableHeader({
  label,
  active,
  dir,
  onToggle,
  style,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onToggle: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <th
      style={{
        ...style,
        cursor: 'pointer',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
      onClick={onToggle}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
        {label}
        {active ? (
          dir === 'asc' ? (
            <ChevronUp size={12} aria-hidden="true" />
          ) : (
            <ChevronDown size={12} aria-hidden="true" />
          )
        ) : null}
      </span>
    </th>
  );
}

// ---------------------------------------------------------------------------
// Main AuditTab
// ---------------------------------------------------------------------------

export function AuditTab() {
  // Filter state
  const [filter, setFilter] = useState<FilterState>({
    userId: '',
    queryType: '',
    status: '',
    since: '',
    until: '',
  });

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(10);

  // Sort — only created_at is sortable for now
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Modal
  const [modalSql, setModalSql] = useState<string | null>(null);

  const offset = (page - 1) * pageSize;

  const auditParams = {
    limit: pageSize,
    offset,
    user_id: filter.userId || undefined,
    query_type: filter.queryType || undefined,
    status: filter.status || undefined,
    since: filter.since ? new Date(filter.since).toISOString() : undefined,
    until: filter.until ? new Date(filter.until).toISOString() : undefined,
  };

  const { items, total, loading, error, refresh } = usePgViewerAudit(auditParams);

  // When filter changes reset to page 1
  const handleFilterChange = useCallback((next: FilterState) => {
    setFilter(next);
    setPage(1);
  }, []);

  // Sort items client-side (server may not support order_by for audit yet)
  const sorted = [...items].sort((a, b) => {
    const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
    const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
    return sortDir === 'desc' ? tb - ta : ta - tb;
  });

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: 'var(--bg-primary)',
      }}
    >
      {/* Filter row */}
      <FilterRow filter={filter} onChange={handleFilterChange} />

      {/* Toolbar: refresh + page size */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.5rem 1.25rem',
          borderBottom: '1px solid var(--border-light)',
          flexShrink: 0,
          gap: '0.75rem',
          background: 'var(--bg-secondary)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {loading ? '載入中…' : `共 ${total} 筆`}
          </span>
          {loading && (
            <InProgress size={14} className="spinner" style={{ color: 'var(--accent)' }} aria-hidden="true" />
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Page size selector */}
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            每頁
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value) as (typeof PAGE_SIZES)[number]);
                setPage(1);
              }}
              aria-label="Page size"
              data-testid="page-size-select"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-light)',
                borderRadius: 4,
                padding: '0.125rem 0.375rem',
                fontSize: '0.8125rem',
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              {PAGE_SIZES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            筆
          </label>
          {/* Refresh */}
          <button
            onClick={refresh}
            disabled={loading}
            title="重新整理"
            aria-label="重新整理稽核記錄"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
              padding: '0.375rem 0.625rem',
              background: 'transparent',
              border: '1px solid var(--border-light)',
              borderRadius: 4,
              color: 'var(--text-muted)',
              fontSize: '0.8125rem',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.5 : 1,
            }}
          >
            <Renew size={14} aria-hidden="true" />
            重新整理
          </button>
        </div>
      </div>

      {/* Table area */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {error ? (
          <div
            role="alert"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '2rem 1.5rem',
              color: 'var(--error)',
              fontSize: '0.875rem',
            }}
          >
            <ErrorFilled size={18} aria-hidden="true" />
            {error}
          </div>
        ) : sorted.length === 0 && !loading ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '4rem 2rem',
              color: 'var(--text-muted)',
              fontSize: '0.875rem',
              textAlign: 'center',
            }}
          >
            <Activity size={36} style={{ opacity: 0.3 }} aria-hidden="true" />
            <span>尚無稽核記錄</span>
          </div>
        ) : (
          <table
            data-testid="audit-table"
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.8125rem',
              color: 'var(--text-primary)',
            }}
          >
            <thead>
              <tr
                style={{
                  background: 'var(--bg-secondary)',
                  borderBottom: '1px solid var(--border-light)',
                }}
              >
                <SortableHeader
                  label="時間"
                  active={true}
                  dir={sortDir}
                  onToggle={() => setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))}
                  style={{ padding: '0.625rem 1rem', textAlign: 'left', width: 140, color: 'var(--text-secondary)' }}
                />
                <th style={{ padding: '0.625rem 1rem', textAlign: 'left', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>User</th>
                <th style={{ padding: '0.625rem 1rem', textAlign: 'left', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>Query Type</th>
                <th style={{ padding: '0.625rem 1rem', textAlign: 'left', color: 'var(--text-secondary)' }}>Resource</th>
                <th style={{ padding: '0.625rem 1rem', textAlign: 'right', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>Rows</th>
                <th style={{ padding: '0.625rem 1rem', textAlign: 'right', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>Elapsed</th>
                <th style={{ padding: '0.625rem 1rem', textAlign: 'left', color: 'var(--text-secondary)' }}>Status</th>
                <th style={{ padding: '0.625rem 1rem', textAlign: 'left', color: 'var(--text-secondary)' }}>SQL</th>
                <th style={{ padding: '0.625rem 1rem', textAlign: 'left', color: 'var(--text-secondary)' }}>Error</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry, idx) => (
                <AuditRow
                  key={entry.id ?? idx}
                  entry={entry}
                  onShowSql={setModalSql}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.625rem 1.25rem',
          borderTop: '1px solid var(--border-light)',
          background: 'var(--bg-secondary)',
          flexShrink: 0,
          fontSize: '0.8125rem',
          color: 'var(--text-muted)',
        }}
      >
        <span>
          第 {page} / {totalPages} 頁
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => p - 1)}
            aria-label="上一頁"
            data-testid="pagination-prev"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
              padding: '0.375rem 0.75rem',
              border: '1px solid var(--border-light)',
              borderRadius: 4,
              background: 'var(--bg-primary)',
              color: page <= 1 ? 'var(--text-muted)' : 'var(--text-primary)',
              cursor: page <= 1 ? 'not-allowed' : 'pointer',
              opacity: page <= 1 ? 0.5 : 1,
              fontSize: '0.8125rem',
            }}
          >
            <ChevronLeft size={14} aria-hidden="true" /> 上一頁
          </button>
          <button
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => p + 1)}
            aria-label="下一頁"
            data-testid="pagination-next"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
              padding: '0.375rem 0.75rem',
              border: '1px solid var(--border-light)',
              borderRadius: 4,
              background: 'var(--bg-primary)',
              color: page >= totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
              cursor: page >= totalPages ? 'not-allowed' : 'pointer',
              opacity: page >= totalPages ? 0.5 : 1,
              fontSize: '0.8125rem',
            }}
          >
            下一頁 <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* SQL modal */}
      {modalSql !== null && (
        <SqlModal sql={modalSql} onClose={() => setModalSql(null)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Row component
// ---------------------------------------------------------------------------

function AuditRow({
  entry,
  onShowSql,
}: {
  entry: AuditEntry;
  onShowSql: (sql: string) => void;
}) {
  const isError =
    entry.status === 'error' ||
    entry.status === 'timeout' ||
    entry.status === 'forbidden' ||
    entry.status === 'rate_limited';

  const rowBg = isError ? 'rgba(218,30,40,0.04)' : 'transparent';
  const { background: tagBg, color: tagColor } = statusStyle(entry.status);

  const resource = entry.table_name ?? entry.action ?? '—';

  return (
    <tr
      data-testid="audit-row"
      data-status={entry.status}
      style={{
        background: rowBg,
        borderBottom: '1px solid var(--border-light)',
      }}
      onMouseEnter={(e) => {
        if (!isError)
          (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-secondary)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLTableRowElement).style.background = rowBg;
      }}
    >
      {/* created_at */}
      <td style={{ padding: '0.5rem 1rem', whiteSpace: 'nowrap', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
        {formatDateTime(entry.created_at)}
      </td>

      {/* user_id */}
      <td style={{ padding: '0.5rem 1rem', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span title={entry.user_email ?? entry.user_id}>
          {entry.user_email ?? entry.user_id ?? '—'}
        </span>
      </td>

      {/* query_type */}
      <td style={{ padding: '0.5rem 1rem', whiteSpace: 'nowrap' }}>
        <span
          style={{
            display: 'inline-block',
            padding: '2px 7px',
            borderRadius: 99,
            fontSize: '0.6875rem',
            fontWeight: 600,
            background: 'rgba(33,150,243,0.12)',
            color: '#1976d2',
          }}
        >
          {entry.query_type ?? '—'}
        </span>
      </td>

      {/* resource */}
      <td
        style={{
          padding: '0.5rem 1rem',
          maxWidth: 160,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          fontFamily: 'monospace',
          fontSize: '0.75rem',
        }}
        title={resource}
      >
        {resource}
      </td>

      {/* row_count */}
      <td style={{ padding: '0.5rem 1rem', textAlign: 'right', color: 'var(--text-muted)' }}>
        {entry.row_count != null ? entry.row_count : '—'}
      </td>

      {/* elapsed_ms */}
      <td style={{ padding: '0.5rem 1rem', textAlign: 'right', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
        {formatMs(entry.execution_ms)}
      </td>

      {/* status */}
      <td style={{ padding: '0.5rem 1rem', whiteSpace: 'nowrap' }}>
        <span
          data-testid="status-tag"
          style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: 99,
            fontSize: '0.6875rem',
            fontWeight: 600,
            background: tagBg,
            color: tagColor,
          }}
        >
          {entry.status ?? '—'}
        </span>
      </td>

      {/* raw_sql */}
      <td style={{ padding: '0.5rem 1rem', maxWidth: 200 }}>
        {entry.raw_sql ? (
          <button
            data-testid="raw-sql-cell"
            onClick={() => onShowSql(entry.raw_sql!)}
            title="點擊查看完整 SQL"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              color: 'var(--accent)',
              padding: 0,
              maxWidth: 200,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              display: 'block',
            }}
          >
            {truncate(entry.raw_sql, 60)}
          </button>
        ) : (
          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
        )}
      </td>

      {/* error */}
      <td
        style={{
          padding: '0.5rem 1rem',
          maxWidth: 180,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: entry.error_message ? 'var(--error)' : 'var(--text-muted)',
          fontSize: '0.75rem',
        }}
        title={entry.error_message ?? undefined}
      >
        {truncate(entry.error_message, 60)}
      </td>
    </tr>
  );
}
