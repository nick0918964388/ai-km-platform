'use client';

/**
 * SqlEditorClient — orchestrator for the SQL editor page.
 *
 * Responsibilities:
 * - Admin guard (redirect non-admin)
 * - Feature-flag guard
 * - Compose SqlEditor + useSqlQuery + result DataTable + banners
 *
 * Aesthetic: IBM Carbon workbench — monospace, hard left-borders, no
 * decorative elements.  Inline banners, no modals/toasts.
 */

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  ErrorFilled,
  Warning,
  CheckmarkFilled,
  Terminal,
  ViewOff,
  ArrowLeft,
} from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import { SqlEditor } from '@/components/admin/pg-viewer/SqlEditor';
import { useSqlQuery } from '@/components/admin/pg-viewer/hooks/useSqlQuery';
import type { SqlResult, SqlResultColumn } from '@/types/pgViewer';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SqlEditorClientProps {
  featureEnabled: boolean;
}

// ---------------------------------------------------------------------------
// Sub-components: inline banners
// ---------------------------------------------------------------------------

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="sql-error-banner"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        padding: '0.875rem 1.25rem',
        background: 'var(--bg-secondary, #161616)',
        borderLeft: '4px solid var(--error, #da1e28)',
        borderTop: '1px solid rgba(218,30,40,0.25)',
        borderBottom: '1px solid rgba(218,30,40,0.25)',
        borderRight: '1px solid rgba(218,30,40,0.25)',
      }}
    >
      <ErrorFilled
        size={16}
        style={{ color: 'var(--error, #da1e28)', flexShrink: 0, marginTop: 2 }}
        aria-hidden="true"
      />
      <p
        style={{
          margin: 0,
          fontSize: '0.8125rem',
          fontFamily: "'IBM Plex Mono', monospace",
          color: 'var(--error, #da1e28)',
          lineHeight: 1.5,
          wordBreak: 'break-word',
        }}
      >
        {message}
      </p>
    </div>
  );
}

function WarningBanner({ message, testId }: { message: string; testId?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid={testId}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        padding: '0.875rem 1.25rem',
        background: 'var(--bg-secondary, #161616)',
        borderLeft: '4px solid #f1c21b',
        borderTop: '1px solid rgba(241,194,27,0.25)',
        borderBottom: '1px solid rgba(241,194,27,0.25)',
        borderRight: '1px solid rgba(241,194,27,0.25)',
      }}
    >
      <Warning
        size={16}
        style={{ color: '#f1c21b', flexShrink: 0, marginTop: 2 }}
        aria-hidden="true"
      />
      <p
        style={{
          margin: 0,
          fontSize: '0.8125rem',
          color: '#f1c21b',
          lineHeight: 1.5,
        }}
      >
        {message}
      </p>
    </div>
  );
}

function DisabledBanner() {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        padding: '1rem 1.25rem',
        background: 'var(--bg-secondary, #262626)',
        borderLeft: '4px solid var(--text-muted, #6f6f6f)',
        maxWidth: 560,
      }}
    >
      <Warning
        size={20}
        style={{ color: 'var(--text-muted, #6f6f6f)', flexShrink: 0, marginTop: 2 }}
        aria-hidden="true"
      />
      <div>
        <p
          style={{
            fontWeight: 600,
            color: 'var(--text-primary, #f4f4f4)',
            marginBottom: '0.25rem',
            fontSize: '0.9375rem',
          }}
        >
          PostgreSQL Viewer 暫停服務
        </p>
        <p style={{ color: 'var(--text-secondary, #c6c6c6)', fontSize: '0.875rem', lineHeight: 1.5 }}>
          此功能目前已停用或後端尚未就緒。請確認{' '}
          <code
            style={{
              fontFamily: 'monospace',
              fontSize: '0.8125rem',
              background: 'var(--bg-tertiary, #393939)',
              padding: '1px 4px',
            }}
          >
            PG_VIEWER_ENABLED
          </code>{' '}
          環境變數設定。
        </p>
      </div>
    </div>
  );
}

function ForbiddenBanner() {
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        padding: '1rem 1.25rem',
        background: 'var(--bg-secondary, #262626)',
        borderLeft: '4px solid var(--error, #da1e28)',
        maxWidth: 560,
      }}
    >
      <ErrorFilled
        size={20}
        style={{ color: 'var(--error, #da1e28)', flexShrink: 0, marginTop: 2 }}
        aria-hidden="true"
      />
      <div>
        <p
          style={{
            fontWeight: 600,
            color: 'var(--text-primary, #f4f4f4)',
            marginBottom: '0.25rem',
            fontSize: '0.9375rem',
          }}
        >
          存取遭拒 (403)
        </p>
        <p style={{ color: 'var(--text-secondary, #c6c6c6)', fontSize: '0.875rem' }}>
          此頁面限系統管理員存取。
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result grid
// ---------------------------------------------------------------------------

function ResultGrid({ result }: { result: SqlResult }) {
  if (result.columns.length === 0) {
    return (
      <p
        style={{
          fontSize: '0.8125rem',
          color: 'var(--text-muted, #6f6f6f)',
          fontFamily: 'monospace',
          padding: '1rem 0',
        }}
      >
        Query returned 0 columns.
      </p>
    );
  }

  if (result.rows.length === 0) {
    return (
      <p
        style={{
          fontSize: '0.8125rem',
          color: 'var(--text-muted, #6f6f6f)',
          fontFamily: 'monospace',
          padding: '1rem 0',
        }}
      >
        Query returned 0 rows.
      </p>
    );
  }

  return (
    <div
      style={{
        overflowX: 'auto',
        overflowY: 'auto',
        maxHeight: '50vh',
        border: '1px solid var(--border-light, #393939)',
      }}
    >
      <table
        style={{
          borderCollapse: 'collapse',
          width: '100%',
          fontFamily: "'IBM Plex Mono', 'JetBrains Mono', monospace",
          fontSize: '0.75rem',
        }}
        aria-label="Query results"
        data-testid="sql-result-table"
      >
        <thead>
          <tr>
            {result.columns.map((col: SqlResultColumn) => (
              <th
                key={col.name}
                scope="col"
                style={{
                  padding: '0.5rem 0.75rem',
                  background: 'var(--bg-tertiary, #393939)',
                  borderBottom: '1px solid var(--border-light, #525252)',
                  borderRight: '1px solid var(--border-light, #525252)',
                  color: 'var(--text-secondary, #c6c6c6)',
                  fontWeight: 600,
                  textAlign: 'left',
                  whiteSpace: 'nowrap',
                  position: 'sticky',
                  top: 0,
                  zIndex: 1,
                }}
              >
                <span
                  style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}
                >
                  {col.name}
                  {col.redacted && (
                    <ViewOff
                      size={12}
                      style={{ color: '#f1c21b', flexShrink: 0 }}
                      aria-label="column redacted"
                      title="Column values are redacted by policy"
                    />
                  )}
                </span>
                <span
                  style={{
                    display: 'block',
                    fontSize: '0.625rem',
                    color: 'var(--text-muted, #6f6f6f)',
                    fontWeight: 400,
                    marginTop: '0.125rem',
                  }}
                >
                  {col.data_type}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              style={{
                background: rowIdx % 2 === 0
                  ? 'var(--bg-primary, #262626)'
                  : 'var(--bg-secondary, #1c1c1c)',
              }}
            >
              {result.columns.map((col: SqlResultColumn) => {
                const raw = row[col.name];
                const display =
                  raw === null || raw === undefined
                    ? 'NULL'
                    : typeof raw === 'object'
                    ? JSON.stringify(raw)
                    : String(raw);
                const isNull = raw === null || raw === undefined;

                return (
                  <td
                    key={col.name}
                    style={{
                      padding: '0.375rem 0.75rem',
                      borderBottom: '1px solid var(--border-light, #393939)',
                      borderRight: '1px solid var(--border-light, #393939)',
                      color: isNull
                        ? 'var(--text-muted, #6f6f6f)'
                        : 'var(--text-primary, #f4f4f4)',
                      fontStyle: isNull ? 'italic' : 'normal',
                      whiteSpace: 'nowrap',
                      maxWidth: '320px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                    title={display}
                  >
                    {display}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toolbar: elapsed + row-count badges
// ---------------------------------------------------------------------------

function ResultToolbar({
  rowCount,
  elapsedMs,
}: {
  rowCount: number;
  elapsedMs: number | null;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.625rem',
        padding: '0.5rem 0',
        flexWrap: 'wrap',
      }}
      data-testid="result-toolbar"
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.25rem',
          padding: '0.1875rem 0.5rem',
          background: 'rgba(15,98,254,0.12)',
          border: '1px solid rgba(15,98,254,0.3)',
          color: 'var(--accent, #0f62fe)',
          fontSize: '0.6875rem',
          fontFamily: 'monospace',
          fontWeight: 600,
          letterSpacing: '0.02em',
        }}
        aria-label={`${rowCount} rows returned`}
      >
        <CheckmarkFilled size={10} aria-hidden="true" />
        {rowCount} {rowCount === 1 ? 'row' : 'rows'}
      </span>

      {elapsedMs !== null && (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '0.1875rem 0.5rem',
            background: 'var(--bg-tertiary, #393939)',
            border: '1px solid var(--border-light, #525252)',
            color: 'var(--text-muted, #6f6f6f)',
            fontSize: '0.6875rem',
            fontFamily: 'monospace',
          }}
          aria-label={`Query executed in ${elapsedMs} milliseconds`}
          data-testid="elapsed-badge"
        >
          {elapsedMs}ms
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading spinner (inline, not blocking)
// ---------------------------------------------------------------------------

function InlineSpinner() {
  return (
    <span
      aria-live="polite"
      aria-label="Running query…"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.375rem',
        fontSize: '0.8125rem',
        color: 'var(--text-muted, #6f6f6f)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          display: 'inline-block',
          width: 14,
          height: 14,
          border: '2px solid var(--border-light, #525252)',
          borderTopColor: 'var(--accent, #0f62fe)',
          borderRadius: '50%',
          animation: 'sql-spin 0.7s linear infinite',
        }}
      />
      Running…
      <style>{`
        @keyframes sql-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Run button
// ---------------------------------------------------------------------------

function RunButton({
  onClick,
  disabled,
  loading,
  retryAfter,
}: {
  onClick: () => void;
  disabled: boolean;
  loading: boolean;
  retryAfter: number | null;
}) {
  const label =
    loading
      ? 'Running…'
      : retryAfter !== null
      ? `Rate limited (${retryAfter}s)`
      : 'Run';

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled}
      data-testid="run-sql-button"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.375rem',
        padding: '0.5rem 1.25rem',
        background: disabled
          ? 'var(--bg-tertiary, #393939)'
          : 'var(--accent, #0f62fe)',
        border: 'none',
        color: disabled ? 'var(--text-muted, #6f6f6f)' : '#ffffff',
        fontSize: '0.875rem',
        fontWeight: 600,
        fontFamily: 'inherit',
        cursor: disabled ? 'not-allowed' : 'pointer',
        letterSpacing: '0.02em',
        transition: 'background 0.1s ease',
        flexShrink: 0,
        height: 40,
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLButtonElement).style.background = '#0353e9';
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLButtonElement).style.background = 'var(--accent, #0f62fe)';
        }
      }}
    >
      <Terminal size={16} aria-hidden="true" />
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main orchestrator
// ---------------------------------------------------------------------------

export default function SqlEditorClient({ featureEnabled }: SqlEditorClientProps) {
  const router = useRouter();
  const user = useStore((s) => s.user);
  const [sql, setSql] = useState('');

  const {
    result,
    loading,
    error,
    elapsedMs,
    rateLimited,
    retryAfter,
    featureDisabled: queryFeatureDisabled,
    run,
  } = useSqlQuery();

  // ── Admin guard ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (user && user.role !== 'admin') {
      router.replace('/');
    }
  }, [user, router]);

  const handleRun = useCallback(() => {
    const trimmed = sql.trim();
    if (!trimmed || loading || rateLimited) return;
    run(trimmed);
  }, [sql, loading, rateLimited, run]);

  // Non-admin render guard (redirect in flight)
  if (user && user.role !== 'admin') {
    return (
      <div style={{ padding: '1.5rem 2rem' }}>
        <ForbiddenBanner />
      </div>
    );
  }

  // SSR feature flag
  if (!featureEnabled) {
    return (
      <div style={{ padding: '1.5rem 2rem' }}>
        <PageHeader />
        <div style={{ marginTop: '1.5rem' }}>
          <DisabledBanner />
        </div>
      </div>
    );
  }

  // Backend returned 404 (feature disabled server-side)
  if (queryFeatureDisabled) {
    return (
      <div style={{ padding: '1.5rem 2rem' }}>
        <PageHeader />
        <div style={{ marginTop: '1.5rem' }}>
          <DisabledBanner />
        </div>
      </div>
    );
  }

  const isRunDisabled = loading || rateLimited || sql.trim() === '';

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: 'var(--bg-primary, #262626)',
      }}
    >
      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div
        style={{
          padding: '1rem 1.5rem',
          borderBottom: '1px solid var(--border-light, #393939)',
          flexShrink: 0,
          background: 'var(--bg-secondary, #1c1c1c)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '1.125rem',
              fontWeight: 700,
              color: 'var(--text-primary, #f4f4f4)',
              marginBottom: '0.1875rem',
              letterSpacing: '-0.01em',
            }}
          >
            PostgreSQL SQL Editor
          </h1>
          <p
            style={{
              fontSize: '0.8125rem',
              color: 'var(--text-muted, #6f6f6f)',
              fontFamily: 'monospace',
              letterSpacing: '0.01em',
            }}
          >
            SELECT-only&nbsp;&middot;&nbsp;LIMIT 1000 auto-applied&nbsp;&middot;&nbsp;10 s timeout
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          {/* Back link */}
          <button
            type="button"
            onClick={() => router.push('/admin/pg-viewer')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem',
              padding: '0.375rem 0.75rem',
              background: 'transparent',
              border: '1px solid var(--border-light, #525252)',
              color: 'var(--text-secondary, #c6c6c6)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            <ArrowLeft size={14} aria-hidden="true" />
            Back
          </button>

          <span
            style={{
              padding: '0.2rem 0.625rem',
              fontSize: '0.6875rem',
              fontWeight: 600,
              background: 'rgba(218,30,40,0.1)',
              color: 'var(--error, #da1e28)',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
            }}
          >
            Admin
          </span>
        </div>
      </div>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          padding: '1.5rem',
          gap: '1rem',
        }}
      >
        {/* Editor block */}
        <section aria-label="SQL editor">
          <SqlEditor
            value={sql}
            onChange={setSql}
            onRun={handleRun}
            disabled={loading || rateLimited}
          />

          {/* Run bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              padding: '0.75rem 0 0',
              borderTop: '1px solid var(--border-light, #393939)',
            }}
          >
            <RunButton
              onClick={handleRun}
              disabled={isRunDisabled}
              loading={loading}
              retryAfter={retryAfter}
            />
            {loading && <InlineSpinner />}
          </div>
        </section>

        {/* ── Banners ────────────────────────────────────────────────────── */}

        {/* Rate limit */}
        {rateLimited && retryAfter !== null && (
          <WarningBanner
            message={`Rate limit: 30 SQL/min. Wait ${retryAfter}s before running another query.`}
            testId="rate-limit-banner"
          />
        )}

        {/* Error */}
        {error && !loading && (
          <ErrorBanner message={error} />
        )}

        {/* ── Results ────────────────────────────────────────────────────── */}
        {result && !loading && (
          <section aria-label="Query results" data-testid="sql-results-section">
            <ResultToolbar
              rowCount={result.row_count}
              elapsedMs={elapsedMs}
            />

            {/* Truncation warning */}
            {result.truncated && (
              <div style={{ marginBottom: '0.75rem' }}>
                <WarningBanner
                  message="LIMIT 1000 auto-appended — refine your query for more rows"
                  testId="truncation-warning"
                />
              </div>
            )}

            <ResultGrid result={result} />
          </section>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PageHeader — reused in disabled/forbidden views
// ---------------------------------------------------------------------------

function PageHeader() {
  return (
    <div>
      <h1
        style={{
          fontSize: '1.5rem',
          fontWeight: 700,
          color: 'var(--text-primary, #f4f4f4)',
          marginBottom: '0.25rem',
        }}
      >
        PostgreSQL SQL Editor
      </h1>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted, #6f6f6f)' }}>
        Admin-only · Read-only
      </p>
    </div>
  );
}
