'use client';
import { useState, useEffect } from 'react';
import { Code, Copy, Checkmark, DocumentDownload } from '@carbon/icons-react';
import ChartRenderer from './ChartRenderer';
import FeedbackButtons from './FeedbackButtons';
import QueryResultTable from './QueryResultTable';
import RelatedDocsPanel from './RelatedDocsPanel';

interface SqlResultData {
  success: boolean;
  explanation?: string;
  columns?: string[];
  data?: Record<string, unknown>[];
  row_count?: number;
  chart_suggestion?: any;
  cached?: boolean;
  summary?: string;
  suggestions?: Array<{label: string; query: string; type?: string}>;
  column_labels?: Record<string, string>;
  budget?: string;
  spilled?: boolean;
  result_id?: string;
  total_rows?: number;
  // Tool-router fields (012-maximo-query-tools)
  route_path?: 'tool' | 'nl2sql';
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  // Technical details (admin/analyst only)
  debug?: {
    sql?: string;
    model?: string;
    llm_ms?: number;
    execution_ms?: number;
    confidence?: number;
    [k: string]: unknown;
  };
  // Backward compat — old responses may still have these at top level
  sql?: string;
  model?: string;
  llm_ms?: number;
  execution_ms?: number;
  confidence?: number;
}

interface SqlResultCardProps {
  result: SqlResultData;
  question: string;  // original user question, for feedback
  onRequery?: (query: string) => void;  // callback to re-run with different query
  isAdmin?: boolean;
}

export default function SqlResultCard({ result, question, onRequery, isAdmin }: SqlResultCardProps) {
  const [showSQL, setShowSQL] = useState(false);
  const [copied, setCopied] = useState(false);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [docSearchRow, setDocSearchRow] = useState<Record<string, unknown> | null>(null);
  const [viewMode, setViewMode] = useState<'table' | 'chart'>(
    result.chart_suggestion || (result.row_count && result.row_count > 20) ? 'chart' : 'table'
  );
  const [chartType, setChartType] = useState<'bar' | 'line' | 'pie'>(result.chart_suggestion?.type || 'bar');
  const [showMeta, setShowMeta] = useState(false);
  const [extraData, setExtraData] = useState<any[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadOffset, setLoadOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => {
    setExtraData([]);
    setLoadOffset(result.data?.length || 0);
    setHasMore(!!result.spilled && !!result.result_id);
  }, [result]);

  // Resolve technical fields from debug or top-level (backward compat)
  const sql = result.debug?.sql || result.sql;
  const model = result.debug?.model || result.model;
  const llm_ms = result.debug?.llm_ms ?? result.llm_ms;
  const execution_ms = result.debug?.execution_ms ?? result.execution_ms;
  const confidence = result.debug?.confidence ?? result.confidence;

  const copySQL = () => {
    if (sql) {
      navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleLoadMore = async () => {
    if (!result.result_id || loadingMore) return;
    setLoadingMore(true);
    try {
      const { apiGet } = await import('@/lib/api');
      const page = await apiGet<{ data: Record<string, unknown>[]; has_more: boolean }>(
        `/chat/results/${result.result_id}?offset=${loadOffset}&limit=100`
      );
      setExtraData(prev => [...prev, ...page.data]);
      setLoadOffset(prev => prev + page.data.length);
      setHasMore(page.has_more);
    } catch (e) {
      console.error('Failed to load more:', e);
    }
    setLoadingMore(false);
  };

  const exportExcel = async () => {
    try {
      const { fetchWithTimeout, getApiHeaders } = await import('@/lib/api');
      const res = await fetchWithTimeout(`/api/maximo/export?question=${encodeURIComponent(question)}`, {
        headers: getApiHeaders(),
      });
      if (res.status === 401) {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user_session');
        window.location.href = '/login';
        return;
      }
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `maximo_export.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Export error:', e);
    }
  };

  if (!result.success) {
    return (
      <div style={{ padding: '0.75rem', background: 'rgba(218,30,40,0.08)', border: '1px solid rgba(218,30,40,0.2)', borderRadius: 8, fontSize: '0.8125rem', color: '#da1e28' }}>
        查詢失敗：{result.explanation || '未知錯誤'}
      </div>
    );
  }

  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', overflow: 'hidden', marginTop: '0.5rem',
      position: 'relative',
    }}>
      {/* Compact meta badge — top right corner */}
      <div style={{
        position: 'absolute', top: '0.5rem', right: '0.5rem', zIndex: 1,
        display: 'flex', alignItems: 'center', gap: '0.25rem',
      }}>
        <span style={{
          padding: '0.1rem 0.4rem', borderRadius: 99, fontSize: '0.65rem', fontWeight: 600,
          background: 'rgba(66,190,101,0.12)', color: '#42be65',
        }}>
          {result.data?.length !== result.row_count
            ? `${result.data?.length ?? 0} / ${result.row_count} 筆`
            : `${result.row_count} 筆`}
        </span>
        {isAdmin && confidence != null && (
          <span style={{
            padding: '0.1rem 0.4rem', borderRadius: 99, fontSize: '0.65rem', fontWeight: 600,
            background: confidence >= 0.8 ? 'rgba(66,190,101,0.12)' : confidence >= 0.5 ? 'rgba(241,194,50,0.12)' : 'rgba(218,30,40,0.12)',
            color: confidence >= 0.8 ? '#42be65' : confidence >= 0.5 ? '#f1c232' : '#da1e28',
          }}>
            {Math.round(confidence * 100)}%
          </span>
        )}
        {result.cached && (
          <span style={{ padding: '0.1rem 0.4rem', borderRadius: 99, fontSize: '0.65rem', background: 'rgba(80,144,211,0.12)', color: 'var(--accent)' }}>
            快取
          </span>
        )}
        {isAdmin && (
          <button
            onClick={() => setShowMeta(v => !v)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: '0.65rem', color: 'var(--text-muted)', padding: '0.1rem 0.25rem',
            }}
            title="詳細資訊"
          >
            {showMeta ? '▲' : 'ⓘ'}
          </button>
        )}
      </div>

      {/* Expanded meta info (toggled, admin only) */}
      {isAdmin && showMeta && (
        <div style={{
          padding: '0.5rem 1rem', borderBottom: '1px solid var(--border)',
          fontSize: '0.7rem', color: 'var(--text-muted)',
          display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center',
        }}>
          {model && <span>模型：<b>{model}</b></span>}
          {llm_ms != null && <span>LLM：{(llm_ms / 1000).toFixed(1)}s</span>}
          {execution_ms != null && <span>查詢：{execution_ms}ms</span>}
          {confidence != null && <span>信心度：{Math.round(confidence * 100)}%</span>}
          {result.cached && <span>來源：快取 SQL</span>}
        </div>
      )}

      {/* Main content area */}
      <div style={{ padding: '0.75rem 1rem' }}>
        {/* Summary for large results */}
        {result.summary && (
          <div style={{
            padding: '0.5rem 0.75rem', margin: '0 0 0.5rem',
            background: 'rgba(80,144,211,0.08)', borderRadius: 6,
            fontSize: '0.8125rem', color: 'var(--text-secondary)',
            borderLeft: '3px solid var(--accent)',
          }}>
            {result.summary}
          </div>
        )}

        {/* Chart + Table using shared components */}
        {result.data && result.data.length > 0 && result.columns && result.columns.length >= 2 && (
          <ChartRenderer
            data={result.data}
            columns={result.columns}
            chartSuggestion={result.chart_suggestion}
            showControls={true}
            height={250}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            chartType={chartType}
            onChartTypeChange={setChartType}
          />
        )}

        {/* Data table */}
        {viewMode === 'table' && result.data && result.data.length > 0 && result.columns && (
          <div style={{ marginTop: '0.5rem' }}>
            <QueryResultTable
              columns={result.columns}
              data={[...result.data, ...extraData]}
              rowCount={result.row_count || 0}
              selectedRow={selectedRow}
              onDocSearch={(row, i) => { setSelectedRow(i); setDocSearchRow(row); }}
              columnLabels={result.column_labels}
            />
          </div>
        )}

        {hasMore && (
          <div style={{ textAlign: 'center', padding: '0.5rem' }}>
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              style={{
                padding: '0.4rem 1rem', fontSize: '0.8125rem',
                background: 'var(--accent)', color: '#fff',
                border: 'none', borderRadius: '6px', cursor: 'pointer',
                opacity: loadingMore ? 0.6 : 1,
              }}
            >
              {loadingMore ? '載入中...' : `載入更多（已顯示 ${(result.data?.length || 0) + extraData.length} / ${result.total_rows || result.row_count} 筆）`}
            </button>
          </div>
        )}

        {result.budget && (
          <div style={{
            padding: '0.5rem 1rem', fontSize: '0.8125rem', color: 'var(--text-muted)',
            background: 'rgba(241,194,50,0.08)', borderTop: '1px solid var(--border-subtle)',
          }}>
            {result.budget}
          </div>
        )}

        {result.row_count === 0 && !result.suggestions?.length && (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '1rem', fontSize: '0.8125rem' }}>
            查無結果
          </div>
        )}

        {result.suggestions && result.suggestions.length > 0 && (
          <div style={{ padding: '0.75rem 1rem' }}>
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
              查無結果。以下是一些替代建議：
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
              {result.suggestions.map((s: any, i: number) => (
                s.type === 'info' ? (
                  <div key={i} style={{
                    padding: '0.5rem 0.75rem', fontSize: '0.8125rem',
                    background: 'rgba(80,144,211,0.08)', borderRadius: 6,
                    color: 'var(--text-secondary)', borderLeft: '3px solid var(--accent)',
                  }}>
                    {s.label}
                  </div>
                ) : (
                  <button
                    key={i}
                    onClick={() => onRequery?.(s.query)}
                    style={{
                      padding: '0.5rem 0.875rem', borderRadius: 99,
                      border: '2px solid var(--primary)', background: 'transparent',
                      color: 'var(--primary)', cursor: 'pointer',
                      fontSize: '0.8125rem', fontWeight: 600, textAlign: 'left',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'var(--primary)'; e.currentTarget.style.color = 'white'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--primary)'; }}
                  >
                    {s.label}
                  </button>
                )
              ))}
            </div>
          </div>
        )}

        {/* Related docs */}
        <RelatedDocsPanel
          row={docSearchRow}
          autoSearch={true}
          onClose={() => { setDocSearchRow(null); setSelectedRow(null); }}
        />
      </div>

      {/* Action bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap',
        padding: '0.5rem 1rem', borderTop: '1px solid var(--border)',
        fontSize: '0.75rem',
      }}>
        {/* Feedback */}
        {sql && <FeedbackButtons question={question} sql={sql} />}

        {/* SQL toggle (admin only) */}
        {isAdmin && sql && (
          <button onClick={() => setShowSQL(v => !v)} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', fontSize: '0.75rem',
          }}>
            <Code size={14} /> {showSQL ? '隱藏 SQL' : 'SQL'}
          </button>
        )}

        {/* Copy SQL (admin only) */}
        {isAdmin && sql && (
          <button onClick={copySQL} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            color: copied ? '#42be65' : 'var(--text-muted)', fontSize: '0.75rem',
          }}>
            {copied ? <Checkmark size={14} /> : <Copy size={14} />}
            {copied ? '已複製' : '複製'}
          </button>
        )}

        {/* Excel export */}
        {result.row_count && result.row_count > 0 && (
          <button onClick={exportExcel} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', fontSize: '0.75rem',
          }}>
            <DocumentDownload size={14} style={{ color: '#217346' }} /> Excel
          </button>
        )}
      </div>

      {/* SQL block (expanded, admin only) */}
      {isAdmin && showSQL && sql && (
        <pre style={{
          margin: 0, padding: '0.75rem 1rem',
          background: '#161616', color: '#f4f4f4',
          fontSize: '0.75rem', fontFamily: 'monospace',
          whiteSpace: 'pre-wrap', lineHeight: 1.5,
          borderTop: '1px solid var(--border)',
        }}>{sql}</pre>
      )}
    </div>
  );
}
