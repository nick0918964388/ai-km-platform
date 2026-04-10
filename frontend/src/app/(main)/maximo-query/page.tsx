'use client';

import { useState } from 'react';
import { Send, DataBase, Code, TableSplit, Renew } from '@carbon/icons-react';

const API = '';

const SQL_FRAMES = [
  '⠋ 解析問題中...',
  '⠙ 查詢欄位定義...',
  '⠹ 比對值域映射...',
  '⠸ 建構 SQL 語句...',
  '⠼ 驗證查詢邏輯...',
  '⠴ 最佳化條件...',
  '⠦ 即將完成...',
  '⠧ 送出查詢...',
];

const EXAMPLES = [
  '最近立案未結的故障通報有哪些？列出 10 筆',
  'EMU900 資產有幾筆？',
  '核簽中的工單有哪些？',
  'maximo_mxsr 故障通報各種 status 各有幾筆？',
  '最近 10 筆工單是哪些車？',
];

interface QueryResult {
  success: boolean;
  sql?: string;
  explanation?: string;
  data?: Record<string, unknown>[];
  columns?: string[];
  row_count?: number;
  execution_ms?: number;
  error?: string;
}

export default function MaximoQueryPage() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [showSQL, setShowSQL] = useState(false);
  const [frameIdx, setFrameIdx] = useState(0);

  const runQuery = async (q: string) => {
    const q2 = q.trim();
    if (!q2) return;
    setQuestion(q2);
    setLoading(true);
    setResult(null);
    setShowSQL(false);
    setFrameIdx(0);
    const timer = setInterval(() => {
      setFrameIdx(i => (i + 1) % SQL_FRAMES.length);
    }, 600);
    try {
      const res = await fetch(`${API}/api/maximo/nl2sql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q2 }),
      });
      const data = await res.json();
      setResult(data);
    } finally {
      clearInterval(timer);
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '1.5rem 2rem', overflowY: 'auto', height: '100%', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
          Maximo 資料查詢
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: '0.25rem 0 0' }}>
          用自然語言查詢台鐵工單、資產、故障通報（NL→SQL）
        </p>
      </div>

      {/* Input */}
      <div style={{
        background: 'var(--bg-secondary)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)', padding: '1rem',
      }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && runQuery(question)}
            placeholder='例：最近立案未結的故障通報有哪些？'
            style={{
              flex: 1, padding: '0.625rem 0.875rem',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-primary)', color: 'var(--text-primary)',
              fontSize: '0.9375rem', outline: 'none',
            }}
          />
          <button
            onClick={() => runQuery(question)}
            disabled={!question.trim() || loading}
            style={{
              padding: '0.625rem 1.25rem', background: 'var(--primary)', color: 'white',
              border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600,
              opacity: (!question.trim() || loading) ? 0.45 : 1,
            }}
          >
            {loading ? <Renew size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={16} />}
            查詢
          </button>
        </div>

        {/* Example chips */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => runQuery(ex)}
              style={{
                padding: '0.25rem 0.75rem', borderRadius: 99,
                border: '1px solid var(--border)', background: 'transparent',
                color: 'var(--text-muted)', fontSize: '0.8125rem',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--primary)'; e.currentTarget.style.color = 'var(--primary)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-muted)'; }}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '2rem' }}>
          <div style={{
            fontFamily: 'monospace', fontSize: '0.9375rem',
            color: 'var(--primary)', letterSpacing: '0.04em',
            transition: 'opacity 0.2s',
          }}>
            {SQL_FRAMES[frameIdx]}
          </div>
          <div style={{
            marginTop: '0.75rem', fontSize: '0.75rem',
            color: 'var(--text-muted)', fontFamily: 'monospace',
          }}>
            {['SELECT', 'FROM', 'WHERE', 'JOIN', 'ORDER BY'].map((kw, i) => (
              <span
                key={kw}
                style={{
                  marginRight: '0.5rem',
                  opacity: (frameIdx + i) % 5 === 0 ? 1 : 0.2,
                  transition: 'opacity 0.3s',
                  color: 'var(--accent)',
                }}
              >{kw}</span>
            ))}
          </div>
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {/* Status bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {result.success ? (
              <>
                <span style={{ color: '#42be65', fontWeight: 600 }}>✓ 查詢成功</span>
                <span>{result.row_count} 筆結果</span>
                {result.execution_ms && <span>{result.execution_ms} ms</span>}
              </>
            ) : (
              <span style={{ color: '#da1e28', fontWeight: 600 }}>✗ {result.error}</span>
            )}
            {result.sql && (
              <button
                onClick={() => setShowSQL(v => !v)}
                style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.8125rem' }}
              >
                <Code size={14} /> {showSQL ? '隱藏 SQL' : '顯示 SQL'}
              </button>
            )}
          </div>

          {/* Explanation */}
          {result.explanation && (
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', background: 'var(--bg-secondary)', padding: '0.625rem 0.875rem', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--primary)' }}>
              {result.explanation}
            </div>
          )}

          {/* SQL */}
          {showSQL && result.sql && (
            <pre style={{
              margin: 0, padding: '0.75rem 1rem',
              background: '#161616', color: '#f4f4f4',
              borderRadius: 'var(--radius-sm)', fontSize: '0.8125rem',
              fontFamily: 'monospace', whiteSpace: 'pre-wrap', lineHeight: 1.6,
              overflowX: 'auto',
            }}>{result.sql}</pre>
          )}

          {/* Table */}
          {result.success && result.data && result.data.length > 0 && (
            <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0.625rem 1rem', borderBottom: '1px solid var(--border)', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                <TableSplit size={14} />
                {result.row_count} 筆
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-primary)' }}>
                      {result.columns?.map(col => (
                        <th key={col} style={{
                          padding: '0.5rem 0.875rem', textAlign: 'left',
                          fontWeight: 600, color: 'var(--text-secondary)',
                          borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap',
                        }}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.data.map((row, i) => (
                      <tr key={i} style={{ borderBottom: i < result.data!.length - 1 ? '1px solid var(--border)' : 'none' }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-primary)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                      >
                        {result.columns?.map(col => (
                          <td key={col} style={{ padding: '0.5rem 0.875rem', color: 'var(--text-primary)', whiteSpace: 'nowrap', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {row[col] == null ? <span style={{ color: 'var(--text-muted)' }}>—</span> : String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {result.success && result.row_count === 0 && (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem', fontSize: '0.875rem' }}>
              查無結果
            </div>
          )}
        </div>
      )}

      <style jsx global>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
