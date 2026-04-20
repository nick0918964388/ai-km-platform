'use client';

import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';
import {
  InProgress,
  ErrorFilled,
  Warning,
  Key,
  DataBase,
  ArrowRight,
} from '@carbon/icons-react';
import type { Column, Index, ForeignKey } from '@/types/pgViewer';
import { useTableSchema } from '@/hooks/useTableSchema';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SchemaTabProps {
  tableName: string;
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        marginBottom: '0.75rem',
      }}
    >
      <span
        style={{
          fontSize: '0.75rem',
          fontWeight: 700,
          color: 'var(--text-secondary)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}
      >
        {title}
      </span>
      {count !== undefined && (
        <span
          style={{
            fontSize: '0.625rem',
            color: 'var(--text-muted)',
            background: 'var(--bg-tertiary)',
            padding: '1px 5px',
            borderRadius: 8,
            fontFamily: 'monospace',
          }}
        >
          {count}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Null/empty value display helper
// ---------------------------------------------------------------------------

function NullBadge() {
  return (
    <span
      style={{
        fontSize: '0.6875rem',
        color: 'var(--text-muted)',
        background: 'var(--bg-tertiary)',
        padding: '1px 5px',
        borderRadius: 4,
        fontFamily: 'monospace',
        letterSpacing: '0.02em',
      }}
    >
      NULL
    </span>
  );
}

// ---------------------------------------------------------------------------
// Columns section
// ---------------------------------------------------------------------------

function ColumnsSection({ columns, primaryKey }: { columns: Column[]; primaryKey: string[] }) {
  const pkSet = new Set(primaryKey);

  return (
    <section style={{ marginBottom: '2rem' }}>
      <SectionHeader title="Columns" count={columns.length} />
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '0.8125rem',
            minWidth: 480,
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: '1px solid var(--border-light)',
              }}
            >
              {['Column', 'Data Type', 'Nullable', 'Default'].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: '0.375rem 0.75rem',
                    textAlign: 'left',
                    fontSize: '0.6875rem',
                    fontWeight: 700,
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    whiteSpace: 'nowrap',
                    background: 'var(--bg-secondary)',
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {columns.map((col) => {
              const isPk = pkSet.has(col.name) || col.is_pk === true;
              return (
                <tr
                  key={col.name}
                  data-testid={`col-row-${col.name}`}
                  data-pk={isPk ? 'true' : undefined}
                  style={{
                    background: isPk ? 'var(--accent-subtle, rgba(80,144,211,0.08))' : 'transparent',
                    borderBottom: '1px solid var(--border-light)',
                    transition: 'background 0.1s ease',
                  }}
                >
                  {/* Column name */}
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      fontFamily: 'monospace',
                      fontWeight: isPk ? 600 : 400,
                      color: isPk ? 'var(--accent)' : 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      {isPk && (
                        <Key
                          size={12}
                          style={{ color: 'var(--accent)', flexShrink: 0 }}
                          aria-label="Primary key"
                        />
                      )}
                      {col.name}
                    </span>
                  </td>

                  {/* Data type */}
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: 'var(--text-secondary)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      {col.data_type}
                    </span>
                  </td>

                  {/* Nullable */}
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      color: col.nullable ? 'var(--text-muted)' : 'var(--text-secondary)',
                      fontSize: '0.75rem',
                    }}
                  >
                    {col.nullable ? (
                      <span style={{ color: 'var(--text-muted)' }}>YES</span>
                    ) : (
                      <span
                        style={{
                          fontWeight: 600,
                          color: 'var(--text-primary)',
                          fontSize: '0.6875rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                        }}
                      >
                        NOT NULL
                      </span>
                    )}
                  </td>

                  {/* Default */}
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: 'var(--text-muted)',
                      maxWidth: 240,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col.default != null ? col.default : <NullBadge />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Primary Key section
// ---------------------------------------------------------------------------

function PrimaryKeySection({ primaryKey }: { primaryKey: string[] }) {
  return (
    <section style={{ marginBottom: '2rem' }}>
      <SectionHeader title="Primary Key" />
      {primaryKey.length === 0 ? (
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
          None
        </span>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
          {primaryKey.map((col, idx) => (
            <span
              key={col}
              data-testid={`pk-chip-${col}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.25rem',
                padding: '0.25rem 0.625rem',
                background: 'var(--accent-subtle, rgba(80,144,211,0.1))',
                border: '1px solid var(--accent)',
                borderRadius: 12,
                fontSize: '0.8125rem',
                fontFamily: 'monospace',
                fontWeight: 600,
                color: 'var(--accent)',
              }}
            >
              <Key size={12} aria-hidden="true" />
              <span>{col}</span>
              {primaryKey.length > 1 && (
                <span
                  style={{
                    fontSize: '0.625rem',
                    color: 'var(--text-muted)',
                    marginLeft: 2,
                  }}
                >
                  #{idx + 1}
                </span>
              )}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Indexes section
// ---------------------------------------------------------------------------

function IndexesSection({ indexes }: { indexes: Index[] }) {
  return (
    <section style={{ marginBottom: '2rem' }}>
      <SectionHeader title="Indexes" count={indexes.length} />
      {indexes.length === 0 ? (
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
          None
        </span>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.8125rem',
              minWidth: 400,
            }}
          >
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-light)' }}>
                {['Name', 'Definition', 'Unique'].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: '0.375rem 0.75rem',
                      textAlign: 'left',
                      fontSize: '0.6875rem',
                      fontWeight: 700,
                      color: 'var(--text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      whiteSpace: 'nowrap',
                      background: 'var(--bg-secondary)',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {indexes.map((idx, i) => (
                <tr
                  key={idx.name ?? i}
                  style={{
                    borderBottom: '1px solid var(--border-light)',
                  }}
                >
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {idx.name ?? '—'}
                  </td>
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: 'var(--text-secondary)',
                      maxWidth: 360,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={idx.definition}
                  >
                    {idx.definition ?? '—'}
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    {idx.unique ? (
                      <span
                        style={{
                          fontSize: '0.6875rem',
                          fontWeight: 700,
                          color: 'var(--accent)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                        }}
                      >
                        YES
                      </span>
                    ) : (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Foreign Keys section
// ---------------------------------------------------------------------------

function ForeignKeysSection({
  foreignKeys,
  onNavigate,
}: {
  foreignKeys: ForeignKey[];
  onNavigate: (table: string) => void;
}) {
  return (
    <section style={{ marginBottom: '2rem' }}>
      <SectionHeader title="Foreign Keys" count={foreignKeys.length} />
      {foreignKeys.length === 0 ? (
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
          None
        </span>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.8125rem',
              minWidth: 400,
            }}
          >
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-light)' }}>
                {['Column', 'References Table', 'References Column'].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: '0.375rem 0.75rem',
                      textAlign: 'left',
                      fontSize: '0.6875rem',
                      fontWeight: 700,
                      color: 'var(--text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      whiteSpace: 'nowrap',
                      background: 'var(--bg-secondary)',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {foreignKeys.map((fk, i) => (
                <tr
                  key={`${fk.column ?? ''}-${i}`}
                  style={{ borderBottom: '1px solid var(--border-light)' }}
                >
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {fk.column ?? '—'}
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem', whiteSpace: 'nowrap' }}>
                    {fk.foreign_table ? (
                      <button
                        onClick={() => onNavigate(fk.foreign_table!)}
                        data-testid={`fk-link-${fk.foreign_table}`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          background: 'transparent',
                          border: 'none',
                          padding: 0,
                          cursor: 'pointer',
                          fontFamily: 'monospace',
                          fontSize: '0.75rem',
                          color: 'var(--accent)',
                          fontWeight: 500,
                          textDecoration: 'underline',
                          textDecorationColor: 'transparent',
                          transition: 'text-decoration-color 0.12s ease',
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.textDecorationColor =
                            'var(--accent)';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.textDecorationColor =
                            'transparent';
                        }}
                        aria-label={`Navigate to ${fk.foreign_table}`}
                      >
                        <ArrowRight size={12} aria-hidden="true" />
                        {fk.foreign_table}
                      </button>
                    ) : (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>—</span>
                    )}
                  </td>
                  <td
                    style={{
                      padding: '0.5rem 0.75rem',
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: 'var(--text-secondary)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {fk.foreign_column ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main SchemaTab
// ---------------------------------------------------------------------------

export function SchemaTab({ tableName }: SchemaTabProps) {
  const { schema, loading, error, featureDisabled, forbidden } = useTableSchema(tableName);

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const handleNavigate = useCallback(
    (refTable: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set('table', refTable);
      router.replace(`${pathname}?${params.toString()}`);
    },
    [router, pathname, searchParams]
  );

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          color: 'var(--text-muted)',
          fontSize: '0.875rem',
          padding: '1rem 0',
        }}
        aria-live="polite"
        aria-busy="true"
      >
        <InProgress size={16} className="spinner" aria-hidden="true" />
        <span>載入 schema…</span>
      </div>
    );
  }

  // ── Error states ───────────────────────────────────────────────────────────
  if (featureDisabled) {
    return (
      <div
        role="status"
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.625rem',
          padding: '0.875rem 1rem',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-light)',
          borderLeft: '3px solid var(--text-muted)',
          borderRadius: 6,
          maxWidth: 480,
        }}
      >
        <Warning size={16} style={{ color: 'var(--text-muted)', flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
        <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          Schema 功能暫停服務
        </span>
      </div>
    );
  }

  if (forbidden) {
    return (
      <div
        role="alert"
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.625rem',
          padding: '0.875rem 1rem',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-light)',
          borderLeft: '3px solid var(--error)',
          borderRadius: 6,
          maxWidth: 480,
        }}
      >
        <ErrorFilled size={16} style={{ color: 'var(--error)', flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
        <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          存取遭拒 (403)
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.625rem',
          padding: '0.875rem 1rem',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-light)',
          borderLeft: '3px solid var(--error)',
          borderRadius: 6,
          maxWidth: 480,
        }}
      >
        <ErrorFilled size={16} style={{ color: 'var(--error)', flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
        <div>
          <p style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.125rem' }}>
            載入失敗
          </p>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{error}</p>
        </div>
      </div>
    );
  }

  if (!schema) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '2.5rem 1rem',
          color: 'var(--text-muted)',
          fontSize: '0.875rem',
          textAlign: 'center',
        }}
      >
        <DataBase size={28} style={{ opacity: 0.3 }} aria-hidden="true" />
        <span>無 schema 資料</span>
      </div>
    );
  }

  const columns = schema.columns ?? [];
  const primaryKey = schema.primary_key ?? [];
  const indexes = schema.indexes ?? [];
  const foreignKeys = schema.foreign_keys ?? [];

  return (
    <div data-testid="schema-tab">
      <ColumnsSection columns={columns} primaryKey={primaryKey} />
      <PrimaryKeySection primaryKey={primaryKey} />
      <IndexesSection indexes={indexes} />
      <ForeignKeysSection foreignKeys={foreignKeys} onNavigate={handleNavigate} />
    </div>
  );
}
