'use client';
import { TableSplit } from '@carbon/icons-react';

interface QueryResultTableProps {
  columns: string[];
  data: Record<string, unknown>[];
  rowCount: number;
  onDocSearch?: (row: Record<string, unknown>, index: number) => void;
  selectedRow?: number | null;
}

export default function QueryResultTable({ columns, data, rowCount, onDocSearch, selectedRow }: QueryResultTableProps) {
  const hasDocColumns = columns.some(c => ['description', 'wonum', 'ticketid', 'assetnum'].includes(c.toLowerCase()));

  return (
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0.625rem 1rem', borderBottom: '1px solid var(--border)', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
        <TableSplit size={14} />
        {rowCount} 筆
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
          <thead>
            <tr style={{ background: 'var(--bg-primary)' }}>
              {columns.map(col => (
                <th key={col} style={{
                  padding: '0.5rem 0.875rem', textAlign: 'left',
                  fontWeight: 600, color: 'var(--text-secondary)',
                  borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap',
                }}>{col}</th>
              ))}
              {hasDocColumns && (
                <th style={{ width: 60, textAlign: 'center', padding: '0.5rem', fontWeight: 600, color: 'var(--text-secondary)', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}>文件</th>
              )}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} style={{ borderBottom: i < data.length - 1 ? '1px solid var(--border)' : 'none' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-primary)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                {columns.map(col => (
                  <td key={col} style={{ padding: '0.5rem 0.875rem', color: 'var(--text-primary)', whiteSpace: 'nowrap', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {row[col] == null ? <span style={{ color: 'var(--text-muted)' }}>—</span> : String(row[col])}
                  </td>
                ))}
                {hasDocColumns && (
                  <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                    {columns.some(c => ['description','wonum','ticketid','assetnum'].includes(c.toLowerCase()) && row[c] != null) && onDocSearch && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onDocSearch(row, i); }}
                        title="搜尋相關文件"
                        style={{
                          background: selectedRow === i ? 'var(--primary)' : 'none',
                          border: '1px solid var(--border)', borderRadius: 4,
                          padding: '0.25rem 0.5rem', cursor: 'pointer',
                          color: selectedRow === i ? 'white' : 'var(--text-muted)',
                          fontSize: '0.75rem',
                        }}
                      >
                        📄
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
