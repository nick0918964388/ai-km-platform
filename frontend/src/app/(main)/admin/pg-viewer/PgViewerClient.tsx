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
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import {
  DataBase,
  InProgress,
  ErrorFilled,
  Warning,
  Table,
  DataTable,
} from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import { useTables } from '@/hooks/useTables';
import { TableList } from '@/components/admin/pg-viewer/TableList';

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

// TableList and useTables are in their own files (T-032).

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
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const user = useStore((s) => s.user);

  // Initialise from URL query param ?table=
  const [selectedTable, setSelectedTable] = useState<string | null>(
    () => searchParams.get('table')
  );

  const { tables, loading, error, featureDisabled, forbidden, refresh } = useTables();

  // Sync selection to URL query param
  const handleSelect = useCallback(
    (name: string) => {
      setSelectedTable(name);
      const params = new URLSearchParams(searchParams.toString());
      params.set('table', name);
      router.replace(`${pathname}?${params.toString()}`);
    },
    [router, pathname, searchParams]
  );

  // Admin guard: redirect non-admin to / (403-equivalent)
  useEffect(() => {
    if (user && user.role !== 'admin') {
      router.replace('/');
    }
  }, [user, router]);

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
  if (featureDisabled) {
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

      {/* Two-pane layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <TableList
          tables={tables}
          loading={loading}
          error={error}
          selectedTable={selectedTable}
          onSelect={handleSelect}
          onRefresh={refresh}
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
