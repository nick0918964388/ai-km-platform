'use client';

/**
 * PgViewerClient — the interactive shell for the PostgreSQL Viewer.
 *
 * Layout: 260px left navigator (table list) + flex-grow right pane
 * (Data / Schema / Audit tabs — stubbed until T-032/T-033/T-034 land).
 *
 * Auth guard: redirects non-admin to / on mount (consistent with sidebar guard).
 * Feature flag: renders InlineNotification banner when disabled.
 * Backend 404: also renders InlineNotification (same "feature disabled" path).
 */

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  DataBase,
  InProgress,
  ErrorFilled,
  Renew,
  Table,
  Warning,
  RowDelete,
  DataTable,
} from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import type { TableSummary } from '@/types/pgViewer';
import { FeatureDisabledError, ForbiddenError } from '@/types/pgViewer';

// ---------------------------------------------------------------------------
// Minimal pgViewerService stub — wired to T-030's real service when it lands.
// Inline here so this file compiles independently of T-030.
// ---------------------------------------------------------------------------
async function listTables(): Promise<TableSummary[]> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch('/api/pg-viewer/tables', { headers });

  if (res.status === 404) throw new FeatureDisabledError();
  if (res.status === 403) throw new ForbiddenError();
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const data = await res.json();
  // API returns { tables: [...] } per OpenAPI contract
  return (data.tables ?? data) as TableSummary[];
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface PgViewerClientProps {
  nonce: string;
  featureEnabled: boolean;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

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
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-light)',
        borderLeft: '4px solid var(--text-muted)',
        borderRadius: '8px',
        maxWidth: 560,
      }}
    >
      <Warning
        size={20}
        style={{ color: 'var(--text-muted)', flexShrink: 0, marginTop: 2 }}
        aria-hidden="true"
      />
      <div>
        <p style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem', fontSize: '0.9375rem' }}>
          PostgreSQL Viewer 暫停服務
        </p>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', lineHeight: 1.5 }}>
          此功能目前已停用或後端尚未就緒。請聯繫系統管理員確認{' '}
          <code style={{ fontFamily: 'monospace', fontSize: '0.8125rem', background: 'var(--bg-tertiary)', padding: '1px 4px', borderRadius: 3 }}>
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
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-light)',
        borderLeft: '4px solid var(--error)',
        borderRadius: '8px',
        maxWidth: 560,
      }}
    >
      <ErrorFilled
        size={20}
        style={{ color: 'var(--error)', flexShrink: 0, marginTop: 2 }}
        aria-hidden="true"
      />
      <div>
        <p style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem', fontSize: '0.9375rem' }}>
          存取遭拒 (403)
        </p>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
          此頁面限系統管理員存取。
        </p>
      </div>
    </div>
  );
}

function ComingSoonCard({ label }: { label: string }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.75rem',
      padding: '3rem 2rem',
      background: 'var(--bg-secondary)',
      border: '1px dashed var(--border-light)',
      borderRadius: '10px',
      color: 'var(--text-muted)',
      fontSize: '0.875rem',
      textAlign: 'center',
    }}>
      <DataTable size={32} style={{ opacity: 0.35 }} aria-hidden="true" />
      <span>{label} — coming soon</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TableList (left pane)
// ---------------------------------------------------------------------------

interface TableListProps {
  tables: TableSummary[];
  loading: boolean;
  error: string | null;
  selected: string | null;
  onSelect: (name: string) => void;
  onRefresh: () => void;
}

function TableList({ tables, loading, error, selected, onSelect, onRefresh }: TableListProps) {
  return (
    <aside
      aria-label="資料表列表"
      style={{
        width: 260,
        flexShrink: 0,
        borderRight: '1px solid var(--border-light)',
        background: 'var(--bg-secondary)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Pane header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.875rem 1rem',
        borderBottom: '1px solid var(--border-light)',
        flexShrink: 0,
      }}>
        <span style={{
          fontSize: '0.8125rem',
          fontWeight: 600,
          color: 'var(--text-secondary)',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}>
          Tables
        </span>
        <button
          onClick={onRefresh}
          disabled={loading}
          title="重新整理"
          aria-label="重新整理資料表列表"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 28,
            height: 28,
            background: 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-muted)',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.5 : 1,
          }}
        >
          <Renew size={16} className={loading ? 'spinner' : ''} />
        </button>
      </div>

      {/* Table list body */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && tables.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem', padding: '2.5rem 1rem', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
            <InProgress size={24} className="spinner" style={{ color: 'var(--accent)' }} aria-hidden="true" />
            載入中...
          </div>
        ) : error ? (
          <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', color: 'var(--error)', fontSize: '0.8125rem' }}>
              <ErrorFilled size={14} aria-hidden="true" />
              <span>載入失敗</span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>{error}</p>
          </div>
        ) : tables.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem', padding: '2.5rem 1rem', color: 'var(--text-muted)', fontSize: '0.8125rem', textAlign: 'center' }}>
            <DataBase size={28} style={{ opacity: 0.3 }} aria-hidden="true" />
            <span>無資料表</span>
          </div>
        ) : (
          <ul role="listbox" aria-label="資料表" style={{ listStyle: 'none', padding: '0.25rem 0', margin: 0 }}>
            {tables.map((t) => {
              const isSelected = selected === `${t.schema}.${t.name}`;
              return (
                <li key={`${t.schema}.${t.name}`} role="option" aria-selected={isSelected}>
                  <button
                    onClick={() => onSelect(`${t.schema}.${t.name}`)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      width: '100%',
                      padding: '0.5rem 1rem',
                      background: isSelected ? 'var(--primary-light, rgba(80,144,211,0.1))' : 'transparent',
                      border: 'none',
                      borderLeft: isSelected ? '3px solid var(--accent)' : '3px solid transparent',
                      cursor: 'pointer',
                      gap: '0.5rem',
                      textAlign: 'left',
                      transition: 'background 0.12s ease',
                    }}
                  >
                    {t.kind === 'view' ? (
                      <RowDelete size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} aria-hidden="true" />
                    ) : (
                      <Table size={14} style={{ color: isSelected ? 'var(--accent)' : 'var(--text-muted)', flexShrink: 0 }} aria-hidden="true" />
                    )}
                    <span style={{
                      flex: 1,
                      fontSize: '0.8125rem',
                      color: isSelected ? 'var(--accent)' : 'var(--text-primary)',
                      fontWeight: isSelected ? 500 : 400,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      fontFamily: isSelected ? 'inherit' : 'inherit',
                    }}>
                      {t.name}
                    </span>
                    {t.approx_row_count != null && (
                      <span style={{
                        fontSize: '0.6875rem',
                        color: 'var(--text-muted)',
                        background: 'var(--bg-tertiary)',
                        padding: '1px 5px',
                        borderRadius: 10,
                        flexShrink: 0,
                        fontFamily: 'monospace',
                      }}>
                        {t.approx_row_count >= 1000
                          ? `${(t.approx_row_count / 1000).toFixed(0)}k`
                          : String(t.approx_row_count)}
                      </span>
                    )}
                    {t.grant_missing && (
                      <span
                        title="SELECT grant missing"
                        aria-label="no access"
                        style={{
                          fontSize: '0.625rem',
                          color: 'var(--error)',
                          background: 'rgba(218,30,40,0.1)',
                          padding: '1px 4px',
                          borderRadius: 4,
                          flexShrink: 0,
                        }}
                      >
                        NO ACCESS
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Footer: count */}
      {tables.length > 0 && (
        <div style={{
          padding: '0.5rem 1rem',
          borderTop: '1px solid var(--border-light)',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
          flexShrink: 0,
        }}>
          {tables.length} 個資料表
        </div>
      )}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Tab bar + Detail pane (right side)
// ---------------------------------------------------------------------------

type DetailTab = 'data' | 'schema' | 'audit';

const TAB_LABELS: { key: DetailTab; label: string }[] = [
  { key: 'data', label: 'Data' },
  { key: 'schema', label: 'Schema' },
  { key: 'audit', label: 'Audit' },
];

function DetailPane({ selectedTable }: { selectedTable: string | null }) {
  const [activeTab, setActiveTab] = useState<DetailTab>('data');

  if (!selectedTable) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.75rem',
          color: 'var(--text-muted)',
          padding: '3rem',
        }}
      >
        <DataBase size={40} style={{ opacity: 0.2 }} aria-hidden="true" />
        <p style={{ fontSize: '0.9375rem' }}>從左側選擇一個資料表以開始瀏覽</p>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Tab bar */}
      <div
        role="tablist"
        aria-label="Detail tabs"
        style={{
          display: 'flex',
          gap: 0,
          borderBottom: '1px solid var(--border-light)',
          padding: '0 1.5rem',
          background: 'var(--bg-secondary)',
          flexShrink: 0,
        }}
      >
        {TAB_LABELS.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            aria-selected={activeTab === key}
            aria-controls={`tabpanel-${key}`}
            id={`tab-${key}`}
            onClick={() => setActiveTab(key)}
            style={{
              padding: '0.75rem 1.25rem',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === key ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === key ? 'var(--accent)' : 'var(--text-muted)',
              fontWeight: activeTab === key ? 600 : 400,
              fontSize: '0.875rem',
              cursor: 'pointer',
              fontFamily: 'monospace',
              letterSpacing: '0.02em',
              transition: 'color 0.12s ease',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Panel: table name badge */}
      <div style={{
        padding: '0.75rem 1.5rem',
        borderBottom: '1px solid var(--border-light)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        flexShrink: 0,
        background: 'var(--bg-primary)',
      }}>
        <Table size={14} style={{ color: 'var(--accent)' }} aria-hidden="true" />
        <code style={{
          fontSize: '0.875rem',
          fontFamily: 'monospace',
          fontWeight: 600,
          color: 'var(--text-primary)',
        }}>
          {selectedTable}
        </code>
      </div>

      {/* Tab panels */}
      <div
        id={`tabpanel-data`}
        role="tabpanel"
        aria-labelledby="tab-data"
        hidden={activeTab !== 'data'}
        style={{ flex: 1, overflow: 'auto', padding: '1.5rem' }}
      >
        <ComingSoonCard label="Data browser (T-032)" />
      </div>

      <div
        id={`tabpanel-schema`}
        role="tabpanel"
        aria-labelledby="tab-schema"
        hidden={activeTab !== 'schema'}
        style={{ flex: 1, overflow: 'auto', padding: '1.5rem' }}
      >
        <ComingSoonCard label="Schema inspector (T-033)" />
      </div>

      <div
        id={`tabpanel-audit`}
        role="tabpanel"
        aria-labelledby="tab-audit"
        hidden={activeTab !== 'audit'}
        style={{ flex: 1, overflow: 'auto', padding: '1.5rem' }}
      >
        <ComingSoonCard label="Audit log (T-034)" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main client component
// ---------------------------------------------------------------------------

export default function PgViewerClient({ featureEnabled }: PgViewerClientProps) {
  const router = useRouter();
  const user = useStore((s) => s.user);

  const [tables, setTables] = useState<TableSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendDisabled, setBackendDisabled] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);

  // Admin guard: redirect non-admin to / (403-equivalent)
  useEffect(() => {
    if (user && user.role !== 'admin') {
      router.replace('/');
    }
  }, [user, router]);

  const fetchTables = useCallback(async () => {
    if (!featureEnabled) return;
    setLoading(true);
    setError(null);
    setBackendDisabled(false);
    setForbidden(false);
    try {
      const data = await listTables();
      setTables(data);
    } catch (e) {
      if (e instanceof FeatureDisabledError) {
        setBackendDisabled(true);
      } else if (e instanceof ForbiddenError) {
        setForbidden(true);
      } else {
        setError(e instanceof Error ? e.message : '載入失敗');
      }
    } finally {
      setLoading(false);
    }
  }, [featureEnabled]);

  useEffect(() => {
    if (user?.role === 'admin') {
      fetchTables();
    }
  }, [user, fetchTables]);

  // If user is not admin, show nothing (redirect is in flight)
  if (user && user.role !== 'admin') {
    return null;
  }

  // SSR feature-flag disabled
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

  // Backend 404 → feature disabled on server side
  if (backendDisabled) {
    return (
      <div style={{ padding: '1.5rem 2rem' }}>
        <PageHeader />
        <div style={{ marginTop: '1.5rem' }}>
          <DisabledBanner />
        </div>
      </div>
    );
  }

  // 403 from backend
  if (forbidden) {
    return (
      <div style={{ padding: '1.5rem 2rem' }}>
        <PageHeader />
        <div style={{ marginTop: '1.5rem' }}>
          <ForbiddenBanner />
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-primary)' }}>
      {/* Page header */}
      <div style={{
        padding: '1rem 1.5rem',
        borderBottom: '1px solid var(--border-light)',
        flexShrink: 0,
        background: 'var(--bg-secondary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div>
          <h1 style={{
            fontSize: '1.125rem',
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginBottom: '0.125rem',
          }}>
            PostgreSQL Viewer
          </h1>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            Admin-only · Read-only
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {loading && (
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
              <InProgress size={14} className="spinner" aria-hidden="true" />
              載入中
            </span>
          )}
          {/* Admin badge */}
          <span style={{
            padding: '0.2rem 0.625rem',
            borderRadius: 12,
            fontSize: '0.6875rem',
            fontWeight: 600,
            background: 'rgba(218,30,40,0.1)',
            color: 'var(--error)',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}>
            Admin
          </span>
        </div>
      </div>

      {/* Error banner (non-fatal fetch error) */}
      {error && (
        <div
          role="alert"
          style={{
            padding: '0.75rem 1.5rem',
            background: 'rgba(218,30,40,0.06)',
            borderBottom: '1px solid rgba(218,30,40,0.2)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.875rem',
            color: 'var(--error)',
            flexShrink: 0,
          }}
        >
          <ErrorFilled size={16} aria-hidden="true" />
          {error}
          <button
            onClick={fetchTables}
            style={{
              marginLeft: 'auto',
              padding: '0.25rem 0.75rem',
              background: 'transparent',
              border: '1px solid var(--error)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--error)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
            }}
          >
            重試
          </button>
        </div>
      )}

      {/* Two-pane layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <TableList
          tables={tables}
          loading={loading}
          error={error}
          selected={selectedTable}
          onSelect={setSelectedTable}
          onRefresh={fetchTables}
        />
        <main style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <DetailPane selectedTable={selectedTable} />
        </main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PageHeader — standalone for the disabled/forbidden banner pages
// ---------------------------------------------------------------------------
function PageHeader() {
  return (
    <div>
      <h1 style={{
        fontSize: '1.5rem',
        fontWeight: 700,
        color: 'var(--text-primary)',
        marginBottom: '0.25rem',
      }}>
        PostgreSQL Viewer
      </h1>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
        Admin-only · Read-only
      </p>
    </div>
  );
}
