'use client';

import { useState, useEffect, useRef } from 'react';
import type { RowPage, RowPageColumn } from '@/types/pgViewer';
import { RateLimitError, ForbiddenError, FeatureDisabledError } from '@/types/pgViewer';
import { getTableRows } from '@/services/pgViewerService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FilterClauseExt {
  column: string;
  /** Display operator (maps != → <> for the API) */
  op:
    | '='
    | '!='
    | '<'
    | '<='
    | '>'
    | '>='
    | 'LIKE'
    | 'ILIKE'
    | 'IN'
    | 'NOT IN'
    | 'IS NULL'
    | 'IS NOT NULL';
  value?: string | number | boolean | null;
}

export interface UseTableRowsParams {
  limit: number;
  offset: number;
  order_by?: string;
  order_dir?: 'asc' | 'desc';
  filters?: FilterClauseExt[];
}

export interface UseTableRowsState {
  rows: Record<string, unknown>[];
  columns: RowPageColumn[];
  total: number;
  executionMs: number;
  loading: boolean;
  error: string | null;
  featureDisabled: boolean;
  forbidden: boolean;
  /** non-null when the last request was rate-limited; value = seconds to wait */
  rateLimitRetryAfter: number | null;
}

// ---------------------------------------------------------------------------
// Helper — map display op to API-compatible op
// Converts '!=' to '<>' and passes 'NOT IN' as-is (backend accepts both forms
// since the API contract specifies operator is a free-form string validated server-side).
// ---------------------------------------------------------------------------
function toApiFilter(f: FilterClauseExt): { column: string; op: string; value?: unknown } {
  const op = f.op === '!=' ? '<>' : f.op;
  return { column: f.column, op, value: f.value };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTableRows(
  tableName: string | null,
  params: UseTableRowsParams
): UseTableRowsState & { refresh: () => void } {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<RowPageColumn[]>([]);
  const [total, setTotal] = useState(0);
  const [executionMs, setExecutionMs] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [featureDisabled, setFeatureDisabled] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [rateLimitRetryAfter, setRateLimitRetryAfter] = useState<number | null>(null);

  // Use ref to track the latest params without triggering extra re-renders
  const paramsRef = useRef(params);
  paramsRef.current = params;

  // Serialise params to a stable string so useEffect deps compare by value
  const paramsKey = JSON.stringify({
    tableName,
    limit: params.limit,
    offset: params.offset,
    order_by: params.order_by,
    order_dir: params.order_dir,
    filters: params.filters,
  });

  const fetchRows = async (tableNameArg: string, p: UseTableRowsParams) => {
    setLoading(true);
    setError(null);
    setFeatureDisabled(false);
    setForbidden(false);
    setRateLimitRetryAfter(null);

    try {
      const apiFilters = p.filters
        ? p.filters.map(toApiFilter) as Parameters<typeof getTableRows>[0]['filters']
        : undefined;

      const result: RowPage = await getTableRows({
        table: tableNameArg,
        limit: p.limit,
        offset: p.offset,
        order_by: p.order_by,
        order_dir: p.order_dir,
        filters: apiFilters,
      });

      setRows(result.rows);
      setColumns(result.columns);
      setTotal(result.approx_total);
      setExecutionMs(result.execution_ms);
    } catch (e) {
      if (e instanceof RateLimitError) {
        setRateLimitRetryAfter(e.retryAfter);
        setError(`請求過於頻繁，請等待 ${e.retryAfter} 秒後重試`);
      } else if (e instanceof ForbiddenError) {
        setForbidden(true);
      } else if (e instanceof FeatureDisabledError) {
        setFeatureDisabled(true);
      } else {
        setError(e instanceof Error ? e.message : '載入失敗');
      }
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!tableName) {
      setRows([]);
      setColumns([]);
      setTotal(0);
      setExecutionMs(0);
      setError(null);
      return;
    }
    fetchRows(tableName, paramsRef.current);
    // paramsKey captures all params by value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  const refresh = () => {
    if (tableName) fetchRows(tableName, paramsRef.current);
  };

  return {
    rows,
    columns,
    total,
    executionMs,
    loading,
    error,
    featureDisabled,
    forbidden,
    rateLimitRetryAfter,
    refresh,
  };
}
