/**
 * PostgreSQL Viewer — API service functions
 * Covers all 6 endpoints from specs/013-postgres-viewer/contracts/pg-viewer-api.yaml.
 *
 * Error handling contract:
 *   401  → apiRequest() in lib/api.ts already clears token + redirects to /login
 *   403  → throws ForbiddenError (caller shows "admin only" toast)
 *   404  → throws FeatureDisabledError (caller shows "功能暫停" banner)
 *   429  → throws RateLimitError carrying retryAfter seconds
 *   408  → re-throws as ApiError with status 408 (caller handles "statement timeout")
 *   503  → re-throws as ApiError with status 503
 *   4xx/5xx (other) → re-thrown as ApiError from lib/api.ts
 */

import { apiGet, apiPost, ApiError, TIMEOUTS } from '@/lib/api';
import type {
  TableSummary,
  TableSchema,
  RowPage,
  FilterClause,
  SqlResult,
  AuditEntry,
} from '@/types/pgViewer';
import {
  ForbiddenError,
  FeatureDisabledError,
  RateLimitError,
} from '@/types/pgViewer';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Inspect an ApiError thrown by lib/api.ts and re-throw domain-specific errors
 * for 403, 404, 429. All other statuses pass through unchanged.
 */
function remapError(err: unknown): never {
  if (err instanceof ApiError) {
    if (err.status === 403) {
      throw new ForbiddenError(err.message);
    }
    if (err.status === 404) {
      throw new FeatureDisabledError(err.message);
    }
    if (err.status === 429) {
      // Retry-After is surfaced via the data payload or defaults to 60s.
      // lib/api.ts stores response data in ApiError.data; we try to read it.
      const retryAfter = extractRetryAfter(err.data);
      throw new RateLimitError(err.message, retryAfter);
    }
  }
  throw err;
}

/**
 * Extract a numeric Retry-After value from the error data payload.
 * The backend may put it in `data.retry_after` (non-standard convenience)
 * or we fall back to 60 s (the stated rate-limit window in the spec).
 */
function extractRetryAfter(data: unknown): number {
  if (
    data !== null &&
    typeof data === 'object' &&
    'retry_after' in data &&
    typeof (data as Record<string, unknown>).retry_after === 'number'
  ) {
    return (data as Record<string, unknown>).retry_after as number;
  }
  return 60;
}

/**
 * Build a URLSearchParams string from an object, omitting undefined values.
 */
function toQs(params: Record<string, string | number | boolean | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined) {
      qs.set(key, String(val));
    }
  }
  const str = qs.toString();
  return str ? `?${str}` : '';
}

// ---------------------------------------------------------------------------
// Public service functions
// ---------------------------------------------------------------------------

/**
 * GET /api/pg-viewer/tables
 * List all tables in the public schema with approximate row counts.
 */
export async function listTables(): Promise<TableSummary[]> {
  try {
    const result = await apiGet<{ tables: TableSummary[] }>('/api/pg-viewer/tables', {
      timeout: TIMEOUTS.DEFAULT,
    });
    return result.tables;
  } catch (err) {
    remapError(err);
  }
}

/**
 * GET /api/pg-viewer/tables/{table}/schema
 * Describe a single table (columns, indexes, foreign keys).
 */
export async function getTableSchema(name: string): Promise<TableSchema> {
  try {
    return await apiGet<TableSchema>(
      `/api/pg-viewer/tables/${encodeURIComponent(name)}/schema`,
      { timeout: TIMEOUTS.DEFAULT }
    );
  } catch (err) {
    remapError(err);
  }
}

/**
 * GET /api/pg-viewer/tables/{table}/rows
 * Paginated, filterable row fetch.
 *
 * @param params.table     - Table name (path param)
 * @param params.limit     - Rows per page (1–1000, default 50)
 * @param params.offset    - Row offset (default 0)
 * @param params.order_by  - Column name to sort by
 * @param params.order_dir - Sort direction ('asc' | 'desc'); API accepts ASC/DESC
 * @param params.filters   - Array of FilterClause — JSON-serialised before sending
 */
export async function getTableRows(params: {
  table: string;
  limit: number;
  offset: number;
  order_by?: string;
  order_dir?: 'asc' | 'desc';
  filters?: FilterClause[];
}): Promise<RowPage> {
  const { table, filters, order_dir, ...rest } = params;

  const qsParams: Record<string, string | number | boolean | undefined> = {
    ...rest,
    order_dir: order_dir?.toUpperCase() as 'ASC' | 'DESC' | undefined,
    filters: filters && filters.length > 0 ? JSON.stringify(filters) : undefined,
  };

  try {
    return await apiGet<RowPage>(
      `/api/pg-viewer/tables/${encodeURIComponent(table)}/rows${toQs(qsParams)}`,
      { timeout: TIMEOUTS.EXPORT }
    );
  } catch (err) {
    remapError(err);
  }
}

/**
 * Download a CSV export via fetch + Authorization header, then trigger a
 * browser file-save.  This avoids appending the JWT to the URL (C-2 fix).
 *
 * @param table    - Table name
 * @param params   - Optional sort / filter overrides
 *
 * On auth failure (401/403) throws ApiError so the caller can redirect / toast.
 * On any other error throws ApiError with the HTTP status.
 */
export async function downloadCsv(
  table: string,
  params: {
    order_by?: string;
    order_dir?: 'asc' | 'desc';
    filters?: FilterClause[];
  } = {}
): Promise<void> {
  const { filters, order_dir, ...rest } = params;

  const qsParams: Record<string, string | number | boolean | undefined> = {
    ...rest,
    order_dir: order_dir?.toUpperCase() as 'ASC' | 'DESC' | undefined,
    filters: filters && filters.length > 0 ? JSON.stringify(filters) : undefined,
  };

  const apiBase =
    typeof window !== 'undefined'
      ? ''
      : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const url = `${apiBase}/api/pg-viewer/tables/${encodeURIComponent(table)}/export.csv${toQs(qsParams)}`;

  const token =
    typeof window !== 'undefined' ? localStorage.getItem('auth_token') ?? null : null;

  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(url, { headers });

  if (!res.ok) {
    throw new ApiError(res.status, `CSV export failed: ${res.statusText}`);
  }

  const blob = await res.blob();

  // Extract filename from Content-Disposition or fall back to table name.
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `${table}.csv`;

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

/**
 * POST /api/pg-viewer/sql
 * Execute a SELECT-only ad-hoc SQL statement.
 * Server wraps input as `SELECT * FROM ({sql}) _limited LIMIT 1000`.
 */
export async function runSql(sql: string): Promise<SqlResult> {
  try {
    return await apiPost<SqlResult>(
      '/api/pg-viewer/sql',
      { sql },
      { timeout: TIMEOUTS.EXPORT }
    );
  } catch (err) {
    remapError(err);
  }
}

/**
 * GET /api/pg-viewer/audit
 * Read the pg_viewer audit log (admin only).
 *
 * @param params.limit      - Max entries to return (1–500, default 100)
 * @param params.offset     - Entry offset for pagination
 * @param params.user_id    - Filter by user ID
 * @param params.query_type - Filter by query type
 * @param params.status     - Filter by status enum
 * @param params.since      - ISO 8601 lower bound on created_at
 * @param params.until      - ISO 8601 upper bound on created_at
 *
 * NOTE: The OpenAPI spec does not define `offset`, `since`, or `until` parameters
 * for /audit — they are included here for forward-compatibility and are silently
 * ignored by the server if unsupported.
 */
export async function getAudit(params: {
  limit: number;
  offset: number;
  user_id?: string;
  query_type?: string;
  status?: string;
  since?: string;
  until?: string;
}): Promise<{ items: AuditEntry[]; total: number }> {
  const qsParams: Record<string, string | number | boolean | undefined> = { ...params };

  try {
    const result = await apiGet<{ entries: AuditEntry[]; total?: number }>(
      `/api/pg-viewer/audit${toQs(qsParams)}`,
      { timeout: TIMEOUTS.DEFAULT }
    );
    // The OpenAPI spec names the array "entries"; we normalise to { items, total }
    // as required by the task contract so callers have a uniform shape.
    return {
      items: result.entries,
      total: result.total ?? result.entries.length,
    };
  } catch (err) {
    remapError(err);
  }
}
