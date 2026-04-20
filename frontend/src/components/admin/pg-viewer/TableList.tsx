'use client';

import {
  useState,
  useDeferredValue,
  useRef,
  useCallback,
  useEffect,
  KeyboardEvent,
} from 'react';
import {
  DataBase,
  InProgress,
  ErrorFilled,
  Renew,
  Table,
  RowDelete,
  ChevronDown,
  ChevronRight,
} from '@carbon/icons-react';
import type { TableSummary } from '@/types/pgViewer';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export type TableListProps = {
  selectedTable: string | null;
  onSelect: (table: string) => void;
  tables: TableSummary[];
  loading: boolean;
  error: string | null;
  onRefresh?: () => void;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** "schema.name" identifier used for URL query param matching */
function tableKey(t: TableSummary): string {
  return `${t.schema}.${t.name}`;
}

/**
 * Derive a display-group prefix from the table name.
 * Strategy: use the segment before the first `_` if the name contains one,
 * otherwise fall back to the schema name.
 * Special-cased: pg_* → "pg_catalog", information_schema.* → "information_schema".
 */
function deriveGroup(t: TableSummary): string {
  if (t.group) return t.group;
  if (t.schema === 'pg_catalog' || t.name.startsWith('pg_')) return 'pg_catalog';
  if (t.schema === 'information_schema') return 'information_schema';
  const underscore = t.name.indexOf('_');
  return underscore > 0 ? t.name.slice(0, underscore) : t.schema;
}

/** Compact badge label for approx_row_count */
function formatCount(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

// ---------------------------------------------------------------------------
// Skeleton rows
// ---------------------------------------------------------------------------

function SkeletonRows() {
  const widths = ['62%', '78%', '55%', '70%', '48%', '65%'];
  return (
    <div style={{ padding: '0.25rem 0' }} aria-busy="true" aria-label="載入中">
      {widths.map((w, i) => (
        <div
          key={i}
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '0 1rem',
            height: 36,
            gap: '0.5rem',
          }}
        >
          <div
            style={{
              width: 14,
              height: 14,
              borderRadius: 2,
              background: 'var(--bg-tertiary)',
              flexShrink: 0,
            }}
          />
          <div
            style={{
              height: 10,
              width: w,
              borderRadius: 4,
              background: 'var(--bg-tertiary)',
              animation: 'pulse 1.4s ease-in-out infinite',
            }}
          />
        </div>
      ))}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Group header
// ---------------------------------------------------------------------------

function GroupHeader({
  label,
  count,
  collapsed,
  onToggle,
}: {
  label: string;
  count: number;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      aria-expanded={!collapsed}
      style={{
        display: 'flex',
        alignItems: 'center',
        width: '100%',
        padding: '0.375rem 0.75rem',
        background: 'transparent',
        border: 'none',
        cursor: 'pointer',
        gap: '0.25rem',
        textAlign: 'left',
        marginTop: '0.125rem',
      }}
    >
      {collapsed ? (
        <ChevronRight size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} aria-hidden="true" />
      ) : (
        <ChevronDown size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} aria-hidden="true" />
      )}
      <span
        style={{
          fontSize: '0.6875rem',
          fontWeight: 600,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: '0.625rem',
          color: 'var(--text-muted)',
          background: 'var(--bg-tertiary)',
          padding: '0 4px',
          borderRadius: 8,
          fontFamily: 'monospace',
          flexShrink: 0,
        }}
      >
        {count}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Table row
// ---------------------------------------------------------------------------

function TableRow({
  table,
  isSelected,
  isFocused,
  onSelect,
  rowRef,
}: {
  table: TableSummary;
  isSelected: boolean;
  isFocused: boolean;
  onSelect: () => void;
  rowRef?: (el: HTMLButtonElement | null) => void;
}) {
  const key = tableKey(table);

  return (
    <li role="option" aria-selected={isSelected} style={{ listStyle: 'none' }}>
      <button
        ref={rowRef}
        id={`table-row-${key.replace(/[^a-zA-Z0-9_-]/g, '-')}`}
        onClick={onSelect}
        data-table={key}
        style={{
          display: 'flex',
          alignItems: 'center',
          width: '100%',
          height: 36,
          padding: '0 1rem',
          background: isSelected
            ? 'var(--primary-light, rgba(80,144,211,0.1))'
            : isFocused
            ? 'var(--bg-tertiary, rgba(255,255,255,0.04))'
            : 'transparent',
          border: 'none',
          borderLeft: isSelected
            ? '3px solid var(--accent)'
            : '3px solid transparent',
          cursor: 'pointer',
          gap: '0.5rem',
          textAlign: 'left',
          transition: 'background 0.1s ease',
          outline: isFocused ? '2px solid var(--accent)' : 'none',
          outlineOffset: -2,
        }}
        onMouseEnter={(e) => {
          if (!isSelected) {
            (e.currentTarget as HTMLButtonElement).style.background =
              'var(--bg-tertiary, rgba(255,255,255,0.04))';
          }
        }}
        onMouseLeave={(e) => {
          if (!isSelected && !isFocused) {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
          }
        }}
      >
        {table.kind === 'view' ? (
          <RowDelete
            size={14}
            style={{ color: 'var(--text-muted)', flexShrink: 0 }}
            aria-hidden="true"
          />
        ) : (
          <Table
            size={14}
            style={{
              color: isSelected ? 'var(--accent)' : 'var(--text-muted)',
              flexShrink: 0,
            }}
            aria-hidden="true"
          />
        )}

        <span
          style={{
            flex: 1,
            fontSize: '0.8125rem',
            color: isSelected ? 'var(--accent)' : 'var(--text-primary)',
            fontWeight: isSelected ? 500 : 400,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {table.name}
        </span>

        {/* Row-count badge */}
        <span
          style={{
            fontSize: '0.6875rem',
            color: 'var(--text-muted)',
            background: 'var(--bg-tertiary)',
            padding: '1px 5px',
            borderRadius: 10,
            flexShrink: 0,
            fontFamily: 'monospace',
          }}
          aria-label={`approximately ${table.approx_row_count ?? 0} rows`}
        >
          {formatCount(table.approx_row_count)}
        </span>

        {/* Grant missing amber dot */}
        {table.grant_missing && (
          <span
            title="no SELECT grant — operator action needed"
            aria-label="no SELECT grant — operator action needed"
            data-testid="grant-missing-dot"
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#f1c21b',
              flexShrink: 0,
              border: '1px solid rgba(241,194,27,0.5)',
            }}
          />
        )}
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Main TableList component
// ---------------------------------------------------------------------------

export function TableList({
  selectedTable,
  onSelect,
  tables,
  loading,
  error,
  onRefresh,
}: TableListProps) {
  const [searchRaw, setSearchRaw] = useState('');
  const searchDeferred = useDeferredValue(searchRaw);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const rowRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  // Filter by substring (case-insensitive) using deferred value for <100ms feel
  const filtered = tables.filter(
    (t) =>
      !searchDeferred ||
      t.name.toLowerCase().includes(searchDeferred.toLowerCase()) ||
      t.schema.toLowerCase().includes(searchDeferred.toLowerCase())
  );

  // Group tables
  const groups = filtered.reduce<Map<string, TableSummary[]>>((acc, t) => {
    const g = deriveGroup(t);
    if (!acc.has(g)) acc.set(g, []);
    acc.get(g)!.push(t);
    return acc;
  }, new Map());

  // Flat list of visible rows for keyboard nav (respects collapsed groups)
  const visibleRows: TableSummary[] = [];
  for (const [group, rows] of groups) {
    if (!collapsedGroups.has(group)) {
      visibleRows.push(...rows);
    }
  }

  const toggleGroup = useCallback((group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) {
        next.delete(group);
      } else {
        next.add(group);
      }
      return next;
    });
    // Reset focus when collapsing
    setFocusedIndex(-1);
  }, []);

  // Keyboard handler for the list area
  const handleListKeyDown = useCallback(
    (e: KeyboardEvent<HTMLUListElement>) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedIndex((i) => Math.min(i + 1, visibleRows.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        if (focusedIndex >= 0 && focusedIndex < visibleRows.length) {
          onSelect(tableKey(visibleRows[focusedIndex]));
        }
      }
    },
    [focusedIndex, visibleRows, onSelect]
  );

  // Global keydown for `/` → focus search, `Esc` → clear search
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      const active = document.activeElement;
      const isInput =
        active instanceof HTMLInputElement ||
        active instanceof HTMLTextAreaElement;

      if (e.key === '/' && !isInput) {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === 'Escape' && searchRaw) {
        setSearchRaw('');
        setFocusedIndex(-1);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [searchRaw]);

  // Scroll focused row into view
  useEffect(() => {
    if (focusedIndex < 0 || focusedIndex >= visibleRows.length) return;
    const key = tableKey(visibleRows[focusedIndex]);
    rowRefs.current.get(key)?.scrollIntoView({ block: 'nearest' });
  }, [focusedIndex, visibleRows]);

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
      {/* ── Pane header ───────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.875rem 1rem 0.5rem',
          borderBottom: '1px solid var(--border-light)',
          flexShrink: 0,
          gap: '0.5rem',
        }}
      >
        <span
          style={{
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            flexShrink: 0,
          }}
        >
          Tables
        </span>
        {onRefresh && (
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
              marginLeft: 'auto',
              flexShrink: 0,
            }}
          >
            <Renew size={16} className={loading ? 'spinner' : ''} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* ── Search input ──────────────────────────────────────────────────── */}
      <div
        style={{
          padding: '0.5rem 0.75rem',
          borderBottom: '1px solid var(--border-light)',
          flexShrink: 0,
        }}
      >
        <input
          ref={searchRef}
          type="search"
          placeholder="搜尋資料表… ( / )"
          value={searchRaw}
          onChange={(e) => {
            setSearchRaw(e.target.value);
            setFocusedIndex(-1);
          }}
          aria-label="搜尋資料表"
          style={{
            width: '100%',
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid transparent',
            outline: 'none',
            fontSize: '0.8125rem',
            color: 'var(--text-primary)',
            padding: '0.25rem 0',
            fontFamily: 'inherit',
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderBottomColor = 'var(--accent)';
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderBottomColor = 'transparent';
          }}
        />
      </div>

      {/* ── Body ──────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && tables.length === 0 ? (
          <SkeletonRows />
        ) : error ? (
          <div
            role="alert"
            style={{
              padding: '1rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
                color: 'var(--error)',
                fontSize: '0.8125rem',
              }}
            >
              <ErrorFilled size={14} aria-hidden="true" />
              <span>載入失敗</span>
            </div>
            <p
              style={{
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
                lineHeight: 1.4,
                margin: 0,
              }}
            >
              {error}
            </p>
            {onRefresh && (
              <button
                onClick={onRefresh}
                style={{
                  alignSelf: 'flex-start',
                  padding: '0.25rem 0.625rem',
                  background: 'transparent',
                  border: '1px solid var(--error)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--error)',
                  fontSize: '0.75rem',
                  cursor: 'pointer',
                }}
              >
                重試
              </button>
            )}
          </div>
        ) : filtered.length === 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '2.5rem 1rem',
              color: 'var(--text-muted)',
              fontSize: '0.8125rem',
              textAlign: 'center',
            }}
          >
            <DataBase size={28} style={{ opacity: 0.3 }} aria-hidden="true" />
            <span>
              {searchDeferred ? `找不到「${searchDeferred}」` : '無資料表'}
            </span>
          </div>
        ) : (
          <ul
            ref={listRef}
            role="listbox"
            aria-label="資料表"
            aria-activedescendant={
              focusedIndex >= 0 && focusedIndex < visibleRows.length
                ? `table-row-${tableKey(visibleRows[focusedIndex]).replace(/[^a-zA-Z0-9_-]/g, '-')}`
                : undefined
            }
            tabIndex={0}
            onKeyDown={handleListKeyDown}
            style={{ listStyle: 'none', padding: '0.25rem 0', margin: 0, outline: 'none' }}
          >
            {Array.from(groups.entries()).map(([group, rows]) => {
              const isCollapsed = collapsedGroups.has(group);
              return (
                <li key={group} style={{ listStyle: 'none' }}>
                  {groups.size > 1 && (
                    <GroupHeader
                      label={group}
                      count={rows.length}
                      collapsed={isCollapsed}
                      onToggle={() => toggleGroup(group)}
                    />
                  )}
                  {!isCollapsed && (
                    <ul
                      role="group"
                      aria-label={group}
                      style={{ listStyle: 'none', padding: 0, margin: 0 }}
                    >
                      {rows.map((t) => {
                        const key = tableKey(t);
                        const globalIdx = visibleRows.indexOf(t);
                        return (
                          <TableRow
                            key={key}
                            table={t}
                            isSelected={selectedTable === key}
                            isFocused={focusedIndex === globalIdx}
                            onSelect={() => onSelect(key)}
                            rowRef={(el) => {
                              if (el) rowRefs.current.set(key, el);
                              else rowRefs.current.delete(key);
                            }}
                          />
                        );
                      })}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* ── Footer: count ─────────────────────────────────────────────────── */}
      {tables.length > 0 && (
        <div
          style={{
            padding: '0.5rem 1rem',
            borderTop: '1px solid var(--border-light)',
            fontSize: '0.75rem',
            color: 'var(--text-muted)',
            flexShrink: 0,
          }}
        >
          {filtered.length < tables.length
            ? `${filtered.length} / ${tables.length} 個資料表`
            : `${tables.length} 個資料表`}
        </div>
      )}
    </aside>
  );
}
