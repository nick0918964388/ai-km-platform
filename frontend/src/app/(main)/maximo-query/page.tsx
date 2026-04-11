'use client';

import { useState, useRef } from 'react';
import { Send, DataBase, Code, TableSplit, Renew, Checkmark, Chat } from '@carbon/icons-react';
import { ThumbsUp, ThumbsDown } from '@carbon/icons-react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const API = '';

// Steps reflecting real backend NL→SQL pipeline
const STEPS_FAST = [
  { label: '解析問題語意', detail: '理解查詢意圖與關鍵詞' },
  { label: '載入 Maximo 欄位定義', detail: '讀取 maximo_zz_maxattribute' },
  { label: '比對值域對應', detail: '從 alndomain 展開欄位可用值' },
  { label: '查詢實際狀態值', detail: 'DISTINCT 查詢現有狀態' },
  { label: 'AI 產生 SQL', detail: '呼叫 LLM 將問題轉換為 SQL' },
  { label: '驗證 SQL 安全性', detail: '確認為 SELECT 查詢、無禁止關鍵字' },
  { label: '執行資料庫查詢', detail: '對 Maximo 資料表執行查詢' },
];

const STEPS_ACCURATE = [
  { label: '解析問題語意', detail: '理解查詢意圖與關鍵詞' },
  { label: '載入 Maximo 欄位定義', detail: '讀取 maximo_zz_maxattribute' },
  { label: '比對值域對應', detail: '從 alndomain 展開欄位可用值' },
  { label: '查詢實際狀態值', detail: 'DISTINCT 查詢現有狀態' },
  { label: 'AI 產生 SQL', detail: '呼叫 LLM 將問題轉換為 SQL' },
  { label: '規則驗證', detail: '檢查結果合理性（數量、日期、排序）' },
  { label: 'AI 驗證答案', detail: '由 AI 確認查詢邏輯與結果正確性' },
  { label: '執行資料庫查詢', detail: '對 Maximo 資料表執行查詢' },
];

const DELAYS_FAST = [0, 350, 700, 1050, 1400, null, null] as (number | null)[];
const DELAYS_ACCURATE = [0, 350, 700, 1050, 1400, null, null, null] as (number | null)[];

const EXAMPLES = [
  '最近立案未結的故障通報有哪些？列出 10 筆',
  'EMU900 資產有幾筆？',
  '核簽中的工單有哪些？',
  'maximo_mxsr 故障通報各種 status 各有幾筆？',
  '最近 10 筆工單是哪些車？',
];

const CHART_COLORS = ['#0f62fe', '#42be65', '#f1c21b', '#da1e28', '#a56eff', '#ff832b', '#08bdba', '#ba4e00'];

interface QueryResult {
  success: boolean;
  sql?: string;
  explanation?: string;
  data?: Record<string, unknown>[];
  columns?: string[];
  row_count?: number;
  execution_ms?: number;
  llm_ms?: number;
  model?: string;
  error?: string;
  // New fields
  iterations?: number;
  confidence?: number;
  verification_history?: Array<{
    attempt: number;
    sql?: string;
    feedback?: string;
    issues?: string[];
  }>;
  cached?: boolean;
  mode?: string;
  chart_suggestion?: {
    type: 'bar' | 'line' | 'pie';
    x_key?: string;
    y_key?: string;
    name_key?: string;
    value_key?: string;
    title?: string;
  };
}

export default function MaximoQueryPage() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [showSQL, setShowSQL] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [llmInfo, setLlmInfo] = useState<{ model?: string; llm_ms?: number } | null>(null);
  const [mode, setMode] = useState<'fast' | 'accurate'>('accurate');
  const [viewMode, setViewMode] = useState<'table' | 'chart'>('table');
  const [feedbackSent, setFeedbackSent] = useState<string | null>(null);
  const [showCorrectionModal, setShowCorrectionModal] = useState(false);
  const [correctedSQL, setCorrectedSQL] = useState('');
  const [queryHistory, setQueryHistory] = useState<Array<{question: string; sql: string}>>([]);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  };

  const handleFeedback = async (rating: 'up' | 'down', corrected?: string) => {
    if (!result?.sql) return;
    const token = localStorage.getItem('auth_token');
    try {
      await fetch(`${API}/api/maximo/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question,
          sql: result.sql,
          rating,
          corrected_sql: corrected || undefined,
        }),
      });
      setFeedbackSent(rating);
      setShowCorrectionModal(false);
    } catch (e) {
      console.error('Feedback error:', e);
    }
  };

  const renderChart = (r: QueryResult) => {
    const cs = r.chart_suggestion!;
    const data = r.data || [];

    if (cs.type === 'bar') {
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={cs.x_key} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Bar dataKey={cs.y_key} fill="#0f62fe" radius={[4, 4, 0, 0]} />
        </BarChart>
      );
    }

    if (cs.type === 'line') {
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={cs.x_key} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Line type="monotone" dataKey={cs.y_key} stroke="#0f62fe" strokeWidth={2} dot={{ fill: '#0f62fe' }} />
        </LineChart>
      );
    }

    if (cs.type === 'pie') {
      return (
        <PieChart>
          <Pie data={data} dataKey={cs.value_key} nameKey={cs.name_key} cx="50%" cy="50%" outerRadius={100} label={({ name, percent }: { name: string; percent: number }) => `${name} ${(percent * 100).toFixed(0)}%`}>
            {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
          </Pie>
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Legend />
        </PieChart>
      );
    }

    return <div>不支援的圖表類型</div>;
  };

  const runQuery = async (q: string) => {
    const q2 = q.trim();
    if (!q2) return;
    setQuestion(q2);
    setLoading(true);
    setResult(null);
    setShowSQL(false);
    setActiveStep(0);
    setLlmInfo(null);
    clearTimers();

    const steps = mode === 'accurate' ? STEPS_ACCURATE : STEPS_FAST;
    const delays = mode === 'accurate' ? DELAYS_ACCURATE : DELAYS_FAST;

    // Auto-advance through steps on fixed delays
    delays.forEach((delay, idx) => {
      if (delay !== null) {
        const t = setTimeout(() => setActiveStep(idx), delay);
        timersRef.current.push(t);
      }
    });

    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`${API}/api/maximo/nl2sql`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question: q2, mode, history: queryHistory }),
      });
      const data = await res.json();
      if (data.model || data.llm_ms) setLlmInfo({ model: data.model, llm_ms: data.llm_ms });
      // Quickly complete remaining steps
      const lastStep = steps.length - 2;
      setActiveStep(lastStep);
      await new Promise(r => setTimeout(r, 200));
      setActiveStep(steps.length - 1);
      await new Promise(r => setTimeout(r, 200));
      setResult(data);
      if (data.success && data.sql) {
        setQueryHistory(prev => [...prev.slice(-4), { question: q2, sql: data.sql }]);
      }
      setFeedbackSent(null);
      setViewMode(data.chart_suggestion ? 'chart' : 'table');
    } finally {
      clearTimers();
      setLoading(false);
    }
  };

  const steps = mode === 'accurate' ? STEPS_ACCURATE : STEPS_FAST;
  const aiStepIndex = 4; // index of "AI 產生 SQL" step

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
          {queryHistory.length > 0 && (
            <button
              onClick={() => { setQueryHistory([]); setResult(null); setQuestion(''); }}
              title="新對話"
              style={{
                padding: '0.625rem', background: 'transparent', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', cursor: 'pointer', color: 'var(--text-muted)',
                display: 'flex', alignItems: 'center',
              }}
            >
              <Renew size={16} />
            </button>
          )}
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

        {queryHistory.length > 0 && (
          <div style={{ fontSize: '0.75rem', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4, marginTop: '0.25rem' }}>
            <Chat size={12} /> 對話模式（{queryHistory.length} 輪上下文）
          </div>
        )}

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

        {/* Mode toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem', fontSize: '0.8125rem' }}>
          <span style={{ color: 'var(--text-muted)' }}>查詢模式：</span>
          <button
            onClick={() => setMode(m => m === 'fast' ? 'accurate' : 'fast')}
            style={{
              padding: '0.25rem 0.75rem', borderRadius: 99,
              border: `1px solid ${mode === 'accurate' ? 'var(--primary)' : 'var(--border)'}`,
              background: mode === 'accurate' ? 'var(--primary)' : 'transparent',
              color: mode === 'accurate' ? 'white' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: '0.8125rem', fontWeight: 500,
            }}
          >
            🎯 精確模式
          </button>
          <button
            onClick={() => setMode(m => m === 'fast' ? 'accurate' : 'fast')}
            style={{
              padding: '0.25rem 0.75rem', borderRadius: 99,
              border: `1px solid ${mode === 'fast' ? 'var(--accent)' : 'var(--border)'}`,
              background: mode === 'fast' ? 'var(--accent)' : 'transparent',
              color: mode === 'fast' ? 'white' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: '0.8125rem', fontWeight: 500,
            }}
          >
            ⚡ 快速模式
          </button>
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
          {steps.map((step, i) => {
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
                    transition: 'color 0.2s', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap',
                  }}>
                    {step.label}
                    {i === aiStepIndex && llmInfo?.model && (
                      <span style={{ fontSize: '0.7rem', padding: '0.1rem 0.4rem', borderRadius: 4, background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--accent)', fontWeight: 500, fontFamily: 'monospace' }}>
                        {llmInfo.model}
                        {llmInfo.llm_ms && ` · ${(llmInfo.llm_ms / 1000).toFixed(1)}s`}
                      </span>
                    )}
                  </div>
                  {(active || done) && (
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 1 }}>
                      {i === aiStepIndex && active && !llmInfo?.model ? step.detail : i === aiStepIndex && llmInfo?.model ? `使用 ${llmInfo.model}` : step.detail}
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
            {result.confidence !== undefined && result.confidence !== null && (
              <span style={{
                padding: '0.125rem 0.5rem', borderRadius: 99,
                background: result.confidence >= 0.8 ? 'rgba(66, 190, 101, 0.15)' : result.confidence >= 0.5 ? 'rgba(241, 194, 50, 0.15)' : 'rgba(218, 30, 40, 0.15)',
                color: result.confidence >= 0.8 ? '#42be65' : result.confidence >= 0.5 ? '#f1c232' : '#da1e28',
                fontSize: '0.75rem', fontWeight: 600,
              }}>
                信心度 {Math.round(result.confidence * 100)}%
              </span>
            )}
            {result.iterations && result.iterations > 1 && (
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                經 {result.iterations} 次迭代
              </span>
            )}
            {result.cached && (
              <span style={{
                padding: '0.125rem 0.5rem', borderRadius: 99,
                background: 'rgba(80, 144, 211, 0.15)',
                color: 'var(--accent)', fontSize: '0.75rem', fontWeight: 500,
              }}>
                快取
              </span>
            )}
            {/* Feedback buttons */}
            {result.success && !feedbackSent && (
              <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.5rem' }}>
                <button onClick={() => handleFeedback('up')} title="查詢正確" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.125rem 0.375rem', borderRadius: 4, color: 'var(--text-muted)' }}>
                  <ThumbsUp size={14} />
                </button>
                <button onClick={() => { setShowCorrectionModal(true); setCorrectedSQL(result.sql || ''); }} title="查詢有誤" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.125rem 0.375rem', borderRadius: 4, color: 'var(--text-muted)' }}>
                  <ThumbsDown size={14} />
                </button>
              </div>
            )}
            {feedbackSent && (
              <span style={{ fontSize: '0.75rem', color: '#42be65', marginLeft: '0.5rem' }}>
                {feedbackSent === 'up' ? '✓ 已標記為正確' : '✓ 已提交回饋'}
              </span>
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

          {/* Verification history */}
          {result.verification_history && result.verification_history.length > 0 && (
            <details style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              <summary style={{ cursor: 'pointer', userSelect: 'none' }}>
                查詢迭代記錄（{result.verification_history.length} 次嘗試）
              </summary>
              <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {result.verification_history.map((h: any, i: number) => (
                  <div key={i} style={{
                    padding: '0.5rem 0.75rem',
                    background: 'var(--bg-primary)',
                    borderRadius: 'var(--radius-sm)',
                    borderLeft: '3px solid var(--border)',
                  }}>
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>第 {h.attempt} 次</div>
                    {h.sql && <div style={{ fontFamily: 'monospace', fontSize: '0.75rem', marginBottom: '0.25rem' }}>{h.sql}</div>}
                    {h.feedback && <div style={{ color: '#da1e28' }}>問題：{h.feedback}</div>}
                    {h.issues && h.issues.map((issue: string, j: number) => (
                      <div key={j} style={{ color: '#da1e28' }}>• {issue}</div>
                    ))}
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* View mode toggle + Chart */}
          {result.success && result.chart_suggestion && result.data && result.data.length > 0 && (
            <>
              <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8125rem' }}>
                <button
                  onClick={() => setViewMode('table')}
                  style={{
                    padding: '0.25rem 0.75rem', borderRadius: 99,
                    border: `1px solid ${viewMode === 'table' ? 'var(--primary)' : 'var(--border)'}`,
                    background: viewMode === 'table' ? 'var(--primary)' : 'transparent',
                    color: viewMode === 'table' ? 'white' : 'var(--text-muted)',
                    cursor: 'pointer', fontWeight: 500,
                  }}
                >
                  表格
                </button>
                <button
                  onClick={() => setViewMode('chart')}
                  style={{
                    padding: '0.25rem 0.75rem', borderRadius: 99,
                    border: `1px solid ${viewMode === 'chart' ? 'var(--accent)' : 'var(--border)'}`,
                    background: viewMode === 'chart' ? 'var(--accent)' : 'transparent',
                    color: viewMode === 'chart' ? 'white' : 'var(--text-muted)',
                    cursor: 'pointer', fontWeight: 500,
                  }}
                >
                  圖表
                </button>
              </div>

              {viewMode === 'chart' && (
                <div style={{
                  background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)', padding: '1.25rem',
                }}>
                  {result.chart_suggestion.title && (
                    <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.75rem', textAlign: 'center' }}>
                      {result.chart_suggestion.title}
                    </div>
                  )}
                  <ResponsiveContainer width="100%" height={300}>
                    {renderChart(result)}
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}

          {/* Table */}
          {viewMode === 'table' && result.success && result.data && result.data.length > 0 && (
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

      {/* SQL Correction Modal */}
      {showCorrectionModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => setShowCorrectionModal(false)}>
          <div style={{
            background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)',
            padding: '1.5rem', width: '90%', maxWidth: 600,
            border: '1px solid var(--border)',
          }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: 'var(--text-primary)' }}>修正 SQL</h3>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', margin: '0 0 0.75rem' }}>
              請修正下方 SQL，修正後會加入範例庫提升未來查詢品質：
            </p>
            <textarea
              value={correctedSQL}
              onChange={e => setCorrectedSQL(e.target.value)}
              style={{
                width: '100%', minHeight: 120, padding: '0.75rem',
                fontFamily: 'monospace', fontSize: '0.8125rem',
                background: 'var(--bg-primary)', color: 'var(--text-primary)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                resize: 'vertical',
                boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
              <button onClick={() => { handleFeedback('down'); }} style={{
                padding: '0.5rem 1rem', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', background: 'transparent',
                color: 'var(--text-muted)', cursor: 'pointer',
              }}>
                不修正，僅回報問題
              </button>
              <button onClick={() => { handleFeedback('down', correctedSQL); }} style={{
                padding: '0.5rem 1rem', background: 'var(--primary)', color: 'white',
                border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontWeight: 600,
              }}>
                提交修正
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
