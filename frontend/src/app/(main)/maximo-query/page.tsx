'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, DataBase, Code, TableSplit, Renew, Checkmark } from '@carbon/icons-react';

const API = '';

// Steps reflecting real backend NL→SQL pipeline
const PIPELINE_STEPS = [
  { label: '解析問題語意', detail: '理解查詢意圖與關鍵詞' },
  { label: '載入 Maximo 欄位定義', detail: '讀取 maximo_zz_maxattribute（45,625 筆屬性）' },
  { label: '比對值域對應', detail: '從 alndomain 展開欄位可用值' },
  { label: '查詢實際狀態值', detail: 'DISTINCT 查詢工單、故障通報現有狀態' },
  { label: 'AI 產生 SQL', detail: '呼叫 LLM 將問題轉換為 PostgreSQL 語句' },
  { label: '驗證 SQL 安全性', detail: '確認為 SELECT 查詢、無禁止關鍵字' },
  { label: '執行資料庫查詢', detail: '對 Maximo 資料表執行查詢並取回結果' },
];

// Each step's auto-advance delay (ms). Step 4 stays until response arrives.
const STEP_DELAYS = [0, 350, 700, 1050, 1400, null, null] as (number | null)[];

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
  const [activeStep, setActiveStep] = useState(0);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  };

  const runQuery = async (q: string) => {
    const q2 = q.trim();
    if (!q2) return;
    setQuestion(q2);
    setLoading(true);
    setResult(null);
    setShowSQL(false);
    setActiveStep(0);
    clearTimers();

    // Auto-advance through steps 0-4 on fixed delays
    STEP_DELAYS.forEach((delay, idx) => {
      if (delay !== null) {
        const t = setTimeout(() => setActiveStep(idx), delay);
        timersRef.current.push(t);
      }
    });

    try {
      const res = await fetch(`${API}/api/maximo/nl2sql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q2 }),
      });
      const data = await res.json();
      // Quickly complete remaining steps
      setActiveStep(5);
      await new Promise(r => setTimeout(r, 200));
      setActiveStep(6);
      await new Promise(r => setTimeout(r, 200));
      setResult(data);
    } finally {
      clearTimers();
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

      {/* Loading — step-by-step pipeline */}
      {loading && (
        <div style={{
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)', padding: '1.25rem 1.5rem',
          display: 'flex', flexDirection: 'column', gap: '0.625rem',
        }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.25rem', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            NL → SQL 處理流程
          </div>
          {PIPELINE_STEPS.map((step, i) => {
            const done = i < activeStep;
            const active = i === activeStep;
            const pending = i > activeStep;
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: '0.625rem',
                opacity: pending ? 0.35 : 1,
                transition: 'opacity 0.3s',
              }}>
                {/* Icon */}
                <div style={{
                  width: 20, height: 20, flexShrink: 0, marginTop: 1,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {done ? (
                    <Checkmark size={16} style={{ color: '#42be65' }} />
                  ) : active ? (
                    <Renew size={16} style={{ color: 'var(--primary)', animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--border)' }} />
                  )}
                </div>
                {/* Text */}
                <div>
                  <div style={{
                    fontSize: '0.875rem', fontWeight: active ? 600 : 400,
                    color: done ? 'var(--text-secondary)' : active ? 'var(--text-primary)' : 'var(--text-muted)',
                    transition: 'color 0.2s',
                  }}>
                    {step.label}
                  </div>
                  {(active || done) && (
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 1 }}>
                      {step.detail}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
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
