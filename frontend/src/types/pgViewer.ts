/**
 * PostgreSQL Viewer — TypeScript interfaces
 * Generated from specs/013-postgres-viewer/contracts/pg-viewer-api.yaml
 * Each interface maps 1:1 to a components.schemas.* entry.
 */

// ---------------------------------------------------------------------------
// Primitive schemas
// ---------------------------------------------------------------------------

/** components/schemas/Error */
export interface PgViewerError {
  detail: string;
}

// ---------------------------------------------------------------------------
// Table listing
// ---------------------------------------------------------------------------

/** components/schemas/TableSummary */
export interface TableSummary {
  schema: string;
  name: string;
  kind: 'table' | 'view';
  approx_row_count: number;
  /** Derived from name prefix for UI grouping */
  group?: string;
  /**
   * true if information_schema.tables lists this table but
   * has_table_privilege(aikm_viewer, table, SELECT) is false.
   * Surfaced in UI as a badge instead of raw 42501.
   */
  grant_missing?: boolean;
}

// ---------------------------------------------------------------------------
// Table schema
// ---------------------------------------------------------------------------

/** components/schemas/Column */
export interface Column {
  name: string;
  data_type: string;
  nullable: boolean;
  default?: string | null;
  comment?: string | null;
  is_pk?: boolean;
  is_indexed?: boolean;
}

/** components/schemas/Index */
export interface Index {
  name?: string;
  definition?: string;
  unique?: boolean;
}

/** components/schemas/ForeignKey */
export interface ForeignKey {
  column?: string;
  foreign_table?: string;
  foreign_column?: string;
}

/** components/schemas/TableSchema */
export interface TableSchema {
  schema?: string;
  name?: string;
  columns?: Column[];
  primary_key?: string[];
  indexes?: Index[];
  foreign_keys?: ForeignKey[];
  approx_row_count?: number;
}

// ---------------------------------------------------------------------------
// Row browsing
// ---------------------------------------------------------------------------

/**
 * FilterClause — one item in the JSON-encoded `filters` query param array.
 * Operators mirror the OpenAPI description for /pg-viewer/tables/{table}/rows.
 */
export interface FilterClause {
  column: string;
  op:
    | '='
    | '<>'
    | '<'
    | '<='
    | '>'
    | '>='
    | 'LIKE'
    | 'ILIKE'
    | 'IN'
    | 'IS NULL'
    | 'IS NOT NULL';
  value?: string | number | boolean | null;
}

/** Column descriptor inside RowPage.columns */
export interface RowPageColumn {
  name: string;
  data_type: string;
  /** true if any value in this column was masked */
  redacted?: boolean;
}

/** components/schemas/RowPage */
export interface RowPage {
  columns: RowPageColumn[];
  /** Array of row objects (keys = column names). Sensitive columns may be missing or ***. */
  rows: Record<string, unknown>[];
  limit: number;
  offset: number;
  /** Approximate row count from pg_class.reltuples */
  approx_total: number;
  execution_ms: number;
  /** true if server capped below requested limit */
  truncated: boolean;
  notice?: string | null;
}

// ---------------------------------------------------------------------------
// SQL editor
// ---------------------------------------------------------------------------

/** Column descriptor inside SqlResult.columns */
export interface SqlResultColumn {
  name: string;
  data_type: string;
  /** true if this column was masked by redaction policy */
  redacted?: boolean;
}

/** components/schemas/SqlResult */
export interface SqlResult {
  columns: SqlResultColumn[];
  /** Array of row objects keyed by column name. */
  rows: Record<string, unknown>[];
  /** Number of rows returned to the client (post-LIMIT). */
  row_count: number;
  /** Server-side SELECT execution time, in milliseconds. */
  elapsed_ms: number;
  /** true if the server auto-appended LIMIT 1000 or clamped the user's LIMIT. */
  truncated: boolean;
  notice?: string | null;
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

/** components/schemas/AuditEntry */
export interface AuditEntry {
  id?: number;
  user_id?: string;
  user_email?: string | null;
  action?: string;
  table_name?: string | null;
  filters_json?: Record<string, unknown> | null;
  order_by?: string | null;
  order_dir?: string | null;
  limit_val?: number | null;
  offset_val?: number | null;
  row_count?: number;
  execution_ms?: number | null;
  error_message?: string | null;
  query_type?: 'table_browse' | 'schema' | 'sql_editor';
  /**
   * Populated only when query_type=sql_editor.
   * Passed through redact_sql_for_audit() then truncated to 8000 chars.
   */
  raw_sql?: string | null;
  status?: 'ok' | 'timeout' | 'error' | 'forbidden' | 'rate_limited';
  created_at?: string;
}

// ---------------------------------------------------------------------------
// Typed error classes (used by pgViewerService)
// ---------------------------------------------------------------------------

/** 403 — authenticated but not admin, or feature disabled */
export class ForbiddenError extends Error {
  readonly status = 403 as const;
  constructor(message = 'admin only') {
    super(message);
    this.name = 'ForbiddenError';
  }
}

/** 404 — table not found, OR feature disabled (caller decides which banner) */
export class FeatureDisabledError extends Error {
  readonly status = 404 as const;
  constructor(message = '功能暫停') {
    super(message);
    this.name = 'FeatureDisabledError';
  }
}

/** 429 — rate limit exceeded; carries the Retry-After value in seconds */
export class RateLimitError extends Error {
  readonly status = 429 as const;
  constructor(
    message = 'rate limit: wait 60s',
    /** Seconds to wait before retrying, from the Retry-After response header */
    public readonly retryAfter: number = 60
  ) {
    super(message);
    this.name = 'RateLimitError';
  }
}
