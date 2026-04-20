'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  DataTable,
  Table,
  TableHead,
  TableRow,
  TableHeader,
  TableBody,
  TableCell,
  TableContainer,
  TableToolbar,
  TableToolbarContent,
  Pagination,
  Button,
  Modal,
  InlineLoading,
  InlineNotification,
} from '@carbon/react';
import {
  Download,
  Filter,
  Close,
  ArrowUp,
  ArrowDown,
  Security,
} from '@carbon/icons-react';
import { useTableRows } from '@/hooks/useTableRows';
import { getTableSchema } from '@/services/pgViewerService';
import { exportCsvUrl } from '@/services/pgViewerService';
import { FilterBar } from './FilterBar';
import type { FilterClauseExt } from '@/hooks/useTableRows';
import type { RowPageColumn } from '@/types/pgViewer';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZES = [10, 50, 100];
const TRUNCATE_CHARS = 200;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface DataTabProps {
  tableName: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a raw cell value to a React node */
function CellValue({
  value,
  onShowMore,
}: {
  value: unknown;
  onShowMore: (full: string) => void;
}) {
  if (value === null || value === undefined) {
    return (
      <i
        style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', opacity: 0.7 }}
        aria-label="null value"
      >
        (null)
      </i>
    );
  }

  const str = typeof value === 'object' ? JSON.stringify(value) : String(value);

  if (str.length > TRUNCATE_CHARS) {
    return (
      <span>
        <span style={{ fontFamily: 'monospace', fontSize: '0.8125rem' }}>
          {str.slice(0, TRUNCATE_CHARS)}
        </span>
        <button
          type="button"
          onClick={() => onShowMore(str)}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--accent)',
            cursor: 'pointer',
            fontSize: '0.75rem',
            marginLeft: '0.25rem',
            padding: 0,
            textDecoration: 'underline',
          }}
          aria-label="顯示完整內容"
        >
          …顯示更多
        </button>
      </span>
    );
  }

  return (
    <span style={{ fontFamily: 'monospace', fontSize: '0.8125rem' }}>{str}</span>
  );
}

// ---------------------------------------------------------------------------
// Main DataTab component
// ---------------------------------------------------------------------------

export function DataTab({ tableName }: DataTabProps) {
  // Pagination state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Sort state
  const [orderBy, setOrderBy] = useState<string | undefined>(undefined);
  const [orderDir, setOrderDir] = useState<'asc' | 'desc'>('asc');

  // Filter state
  const [filters, setFilters] = useState<FilterClauseExt[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  // "Show more" modal state
  const [modalContent, setModalContent] = useState<string | null>(null);

  // Schema columns for FilterBar (inline fetch — T-034 may supersede this)
  const [schemaColumns, setSchemaColumns] = useState<string[]>([]);
  const prevTableRef = useRef<string>('');

  // Rate-limit retry timer
  const [retryDisabled, setRetryDisabled] = useState(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset pagination when table changes
  useEffect(() => {
    if (prevTableRef.current !== tableName) {
      prevTableRef.current = tableName;
      setPage(1);
      setOrderBy(undefined);
      setOrderDir('asc');
      setFilters([]);
      setShowFilters(false);
    }
  }, [tableName]);

  // Fetch schema columns for FilterBar
  useEffect(() => {
    if (!tableName) return;
    let cancelled = false;
    getTableSchema(tableName)
      .then((schema) => {
        if (!cancelled) {
          setSchemaColumns((schema.columns ?? []).map((c) => c.name));
        }
      })
      .catch(() => {
        // Non-fatal: FilterBar will be disabled if columns are empty
      });
    return () => { cancelled = true; };
  }, [tableName]);

  const offset = (page - 1) * pageSize;

  const { rows, columns, total, executionMs, loading, error, rateLimitRetryAfter, refresh } =
    useTableRows(tableName, {
      limit: pageSize,
      offset,
      order_by: orderBy,
      order_dir: orderDir,
      filters,
    });

  // Handle 429 rate-limit: disable retry button for retryAfter seconds
  useEffect(() => {
    if (rateLimitRetryAfter !== null) {
      setRetryDisabled(true);
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      retryTimerRef.current = setTimeout(() => {
        setRetryDisabled(false);
      }, rateLimitRetryAfter * 1000);
    }
    return () => {
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [rateLimitRetryAfter]);

  // Column click → sort toggle
  const handleHeaderClick = useCallback(
    (colName: string) => {
      setPage(1);
      if (orderBy === colName) {
        setOrderDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setOrderBy(colName);
        setOrderDir('asc');
      }
    },
    [orderBy]
  );

  // Filter change → reset to page 1
  const handleFiltersChange = useCallback((next: FilterClauseExt[]) => {
    setFilters(next);
    setPage(1);
  }, []);

  // Build column metadata map
  const colMetaMap: Record<string, RowPageColumn> = {};
  for (const c of columns) {
    colMetaMap[c.name] = c;
  }

  // Carbon DataTable expects headers with `key` and `header` props
  const carbonHeaders = columns.map((c) => ({
    key: c.name,
    header: c.name,
    redacted: c.redacted ?? false,
  }));

  // Carbon DataTable expects rows with an `id` field
  const carbonRows = rows.map((row, i) => ({
    id: `row-${offset + i}`,
    ...row,
  }));

  // CSV export URL
  const csvUrl = exportCsvUrl(tableName, {
    order_by: orderBy,
    order_dir: orderDir,
    filters: filters.map((f) => ({
      column: f.column,
      op: (f.op === '!=' ? '<>' : f.op) as '<>',
      value: f.value,
    })),
  });

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}
      data-testid="data-tab"
    >
      {/* ── Toolbar ─────────────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.5rem 0 0.75rem 0',
          flexShrink: 0,
          flexWrap: 'wrap',
        }}
      >
        {/* Row count + elapsed badge */}
        <span
          style={{
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
            flexShrink: 0,
          }}
        >
          {loading
            ? '—'
            : `約 ${total.toLocaleString()} 筆`}
        </span>
        {executionMs > 0 && !loading && (
          <span
            style={{
              fontSize: '0.6875rem',
              padding: '1px 6px',
              borderRadius: 10,
              background: 'var(--bg-tertiary)',
              color: 'var(--text-muted)',
              fontFamily: 'monospace',
              flexShrink: 0,
            }}
            aria-label={`查詢耗時 ${executionMs} 毫秒`}
          >
            {executionMs} ms
          </span>
        )}

        <div style={{ flex: 1 }} />

        {/* Toggle filter bar */}
        <Button
          kind="ghost"
          size="sm"
          renderIcon={showFilters ? Close : Filter}
          onClick={() => setShowFilters((v) => !v)}
          hasIconOnly
          iconDescription={showFilters ? '隱藏篩選條件' : '顯示篩選條件'}
          tooltipPosition="bottom"
        />

        {/* ExportCSV — browser-native download via <a> */}
        <a
          href={csvUrl}
          download={`${tableName}.csv`}
          aria-label="匯出 CSV"
          data-testid="export-csv-link"
          style={{ textDecoration: 'none' }}
        >
          <Button kind="ghost" size="sm" renderIcon={Download} hasIconOnly iconDescription="匯出 CSV" tooltipPosition="bottom" as="span" />
        </a>
      </div>

      {/* ── FilterBar ───────────────────────────────────────────────────────── */}
      {showFilters && (
        <div
          style={{
            padding: '0.75rem',
            marginBottom: '0.75rem',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-sm, 4px)',
            flexShrink: 0,
          }}
        >
          <FilterBar
            columns={schemaColumns.length > 0 ? schemaColumns : columns.map((c) => c.name)}
            filters={filters}
            onChange={handleFiltersChange}
          />
        </div>
      )}

      {/* ── Error / Rate-limit banner ────────────────────────────────────────── */}
      {error && (
        <div style={{ marginBottom: '0.75rem', flexShrink: 0 }}>
          <InlineNotification
            kind={rateLimitRetryAfter !== null ? 'warning' : 'error'}
            title={rateLimitRetryAfter !== null ? '請求過於頻繁' : '載入失敗'}
            subtitle={error}
            hideCloseButton={false}
          />
          {!retryDisabled && (
            <button
              type="button"
              onClick={refresh}
              style={{
                marginTop: '0.25rem',
                background: 'transparent',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm, 4px)',
                color: 'var(--text-secondary)',
                fontSize: '0.8125rem',
                cursor: 'pointer',
                padding: '0.25rem 0.75rem',
              }}
            >
              重試
            </button>
          )}
        </div>
      )}

      {/* ── Loading indicator ───────────────────────────────────────────────── */}
      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', flexShrink: 0 }}>
          <InlineLoading description="載入中…" status="active" />
        </div>
      )}

      {/* ── Carbon DataTable ─────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {!loading && !error && columns.length === 0 ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '3rem',
              color: 'var(--text-muted)',
              fontSize: '0.875rem',
            }}
          >
            無資料
          </div>
        ) : (
          <DataTable rows={carbonRows} headers={carbonHeaders} isSortable={false}>
            {({
              rows: tableRows,
              headers: tableHeaders,
              getTableProps,
              getTableContainerProps,
            }) => (
              <TableContainer {...getTableContainerProps()}>
                <TableToolbar>
                  <TableToolbarContent>
                    <span style={{ padding: '0 1rem', fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
                      {tableName}
                    </span>
                  </TableToolbarContent>
                </TableToolbar>
                <Table {...getTableProps()} size="sm">
                  <TableHead>
                    <TableRow>
                      {tableHeaders.map((header) => {
                        const meta = colMetaMap[header.key];
                        const isActive = orderBy === header.key;
                        return (
                          <TableHeader
                            key={header.key}
                            onClick={() => handleHeaderClick(header.key)}
                            style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                            sortDirection={isActive ? (orderDir === 'asc' ? 'ASC' : 'DESC') : 'NONE'}
                            isSortHeader={isActive}
                          >
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                              {header.header}
                              {meta?.redacted && (
                                <span
                                  title="敏感欄位 — 數值可能已遮蔽"
                                  aria-label="敏感欄位 — 數值可能已遮蔽"
                                  style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--text-muted)' }}
                                >
                                  <Security size={12} aria-hidden="true" />
                                </span>
                              )}
                              {isActive && (
                                orderDir === 'asc'
                                  ? <ArrowUp size={12} aria-hidden="true" />
                                  : <ArrowDown size={12} aria-hidden="true" />
                              )}
                            </span>
                          </TableHeader>
                        );
                      })}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {tableRows.length === 0 && !loading ? (
                      <TableRow>
                        <TableCell colSpan={tableHeaders.length}>
                          <div
                            style={{
                              textAlign: 'center',
                              padding: '1.5rem',
                              color: 'var(--text-muted)',
                              fontSize: '0.875rem',
                            }}
                          >
                            查無符合條件的資料
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : (
                      tableRows.map((row) => (
                        <TableRow key={row.id}>
                          {row.cells.map((cell) => (
                            <TableCell key={cell.id}>
                              <CellValue
                                value={cell.value}
                                onShowMore={(full) => setModalContent(full)}
                              />
                            </TableCell>
                          ))}
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DataTable>
        )}
      </div>

      {/* ── Pagination ──────────────────────────────────────────────────────── */}
      {total > 0 && (
        <div style={{ flexShrink: 0, borderTop: '1px solid var(--border-light)' }}>
          <Pagination
            backwardText="上一頁"
            forwardText="下一頁"
            itemsPerPageText="每頁筆數"
            page={page}
            pageNumberText="頁碼"
            pageSize={pageSize}
            pageSizes={PAGE_SIZES}
            totalItems={total}
            onChange={({ page: newPage, pageSize: newPageSize }) => {
              setPage(newPage);
              setPageSize(newPageSize);
            }}
          />
        </div>
      )}

      {/* ── "Show more" Modal ───────────────────────────────────────────────── */}
      <Modal
        open={modalContent !== null}
        modalHeading="完整內容"
        primaryButtonText="關閉"
        onRequestClose={() => setModalContent(null)}
        onRequestSubmit={() => setModalContent(null)}
        size="lg"
        aria-label="完整儲存格內容"
        data-testid="cell-full-modal"
      >
        {modalContent !== null && (
          <pre
            style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              fontFamily: 'monospace',
              fontSize: '0.8125rem',
              lineHeight: 1.6,
              color: 'var(--text-primary)',
              maxHeight: '60vh',
              overflowY: 'auto',
            }}
          >
            {modalContent}
          </pre>
        )}
      </Modal>
    </div>
  );
}
