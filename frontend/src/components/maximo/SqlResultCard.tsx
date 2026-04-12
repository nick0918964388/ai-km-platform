'use client';
import { useState } from 'react';
import { Code, Copy, Checkmark } from '@carbon/icons-react';
import ChartRenderer from './ChartRenderer';
import FeedbackButtons from './FeedbackButtons';
import QueryResultTable from './QueryResultTable';
import RelatedDocsPanel from './RelatedDocsPanel';

interface SqlResultData {
  success: boolean;
  sql?: string;
  explanation?: string;
  columns?: string[];
  data?: Record<string, unknown>[];
  row_count?: number;
  execution_ms?: number;
  llm_ms?: number;
  model?: string;
  confidence?: number;
  chart_suggestion?: any;
  cached?: boolean;
}

interface SqlResultCardProps {
  result: SqlResultData;
  question: string;  // original user question, for feedback
}

export default function SqlResultCard({ result, question }: SqlResultCardProps) {
  const [showSQL, setShowSQL] = useState(false);
  const [copied, setCopied] = useState(false);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [docSearchRow, setDocSearchRow] = useState<Record<string, unknown> | null>(null);
  const [viewMode, setViewMode] = useState<'table' | 'chart'>(result.chart_suggestion ? 'chart' : 'table');
  const [chartType, setChartType] = useState<'bar' | 'line' | 'pie'>(result.chart_suggestion?.type || 'bar');

  const copySQL = () => {
    if (result.sql) {
      navigator.clipboard.writeText(result.sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
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
    }}>
      {/* Summary metrics bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap',
        padding: '0.75rem 1rem', borderBottom: '1px solid var(--border)',
        fontSize: '0.75rem', color: 'var(--text-muted)',
      }}>
        <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.8125rem' }}>
          查詢結果
        </span>
        <span style={{
          padding: '0.125rem 0.5rem', borderRadius: 99,
          background: 'rgba(66,190,101,0.12)', color: '#42be65', fontWeight: 600,
        }}>
          {result.row_count} 筆
        </span>
        {result.execution_ms != null && (
          <span>{result.execution_ms} ms</span>
        )}
        {result.confidence != null && (
          <span style={{
            padding: '0.125rem 0.5rem', borderRadius: 99,
            background: result.confidence >= 0.8 ? 'rgba(66,190,101,0.12)' : result.confidence >= 0.5 ? 'rgba(241,194,50,0.12)' : 'rgba(218,30,40,0.12)',
            color: result.confidence >= 0.8 ? '#42be65' : result.confidence >= 0.5 ? '#f1c232' : '#da1e28',
            fontWeight: 600,
          }}>
            信心 {Math.round(result.confidence * 100)}%
          </span>
        )}
        {result.cached && (
          <span style={{ padding: '0.125rem 0.5rem', borderRadius: 99, background: 'rgba(80,144,211,0.12)', color: 'var(--accent)' }}>
            快取
          </span>
        )}
        {result.model && (
          <span style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            {result.model}
          </span>
        )}
      </div>

      {/* Main content area */}
      <div style={{ padding: '0.75rem 1rem' }}>
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
              data={result.data}
              rowCount={result.row_count || 0}
              selectedRow={selectedRow}
              onDocSearch={(row, i) => { setSelectedRow(i); setDocSearchRow(row); }}
            />
          </div>
        )}

        {result.row_count === 0 && (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '1rem', fontSize: '0.8125rem' }}>
            查無結果
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
        {result.sql && <FeedbackButtons question={question} sql={result.sql} />}

        {/* SQL toggle */}
        {result.sql && (
          <button onClick={() => setShowSQL(v => !v)} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', fontSize: '0.75rem',
          }}>
            <Code size={14} /> {showSQL ? '隱藏 SQL' : 'SQL'}
          </button>
        )}

        {/* Copy SQL */}
        {result.sql && (
          <button onClick={copySQL} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            color: copied ? '#42be65' : 'var(--text-muted)', fontSize: '0.75rem',
          }}>
            {copied ? <Checkmark size={14} /> : <Copy size={14} />}
            {copied ? '已複製' : '複製'}
          </button>
        )}
      </div>

      {/* SQL block (expanded) */}
      {showSQL && result.sql && (
        <pre style={{
          margin: 0, padding: '0.75rem 1rem',
          background: '#161616', color: '#f4f4f4',
          fontSize: '0.75rem', fontFamily: 'monospace',
          whiteSpace: 'pre-wrap', lineHeight: 1.5,
          borderTop: '1px solid var(--border)',
        }}>{result.sql}</pre>
      )}
    </div>
  );
}
