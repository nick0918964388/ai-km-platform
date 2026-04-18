'use client';

import { useCallback, useEffect, useState } from 'react';
import { Renew, InProgress, Terminal, ChartNetwork } from '@carbon/icons-react';
import { STREAM_API_URL, getApiHeaders } from '@/lib/api';

interface SparseEntity {
  type: string;
  code?: string | null;
  id?: string | null;
  edges: number;
}

interface KGStats {
  node_counts: Record<string, number>;
  edge_counts: Record<string, number>;
  clean_coverage: number;
  sparse_entities: SparseEntity[];
  last_etl_time: string | null;
  last_etl_status: 'success' | 'failed' | 'running' | 'never';
  source: 'real' | 'mock';
}

interface ETLLogResponse {
  lines: string[];
  source: 'real' | 'mock';
}

function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div
      style={{
        padding: '1rem',
        background: 'var(--bg-secondary, #f9fafb)',
        borderRadius: 8,
        border: '1px solid var(--border, #e5e7eb)',
      }}
    >
      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted, #6b7280)' }}>{label}</div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem' }}>{value}</div>
      {hint && (
        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted, #9ca3af)', marginTop: '0.25rem' }}>
          {hint}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: KGStats['last_etl_status'] }) {
  const map: Record<KGStats['last_etl_status'], { bg: string; color: string; label: string }> = {
    success: { bg: '#d1fae5', color: '#065f46', label: '成功' },
    failed: { bg: '#fee2e2', color: '#991b1b', label: '失敗' },
    running: { bg: '#dbeafe', color: '#1e40af', label: '執行中' },
    never: { bg: '#f3f4f6', color: '#6b7280', label: '尚未執行' },
  };
  const m = map[status];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.125rem 0.5rem',
        borderRadius: 4,
        fontSize: '0.75rem',
        background: m.bg,
        color: m.color,
      }}
    >
      {m.label}
    </span>
  );
}

export default function KnowledgeGraphAdminPage() {
  const [stats, setStats] = useState<KGStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [etlLog, setEtlLog] = useState<string[]>([]);
  const [logSource, setLogSource] = useState<'real' | 'mock'>('mock');
  const [rebuildMsg, setRebuildMsg] = useState('');
  const [rebuilding, setRebuilding] = useState(false);

  const loadStats = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/kg/stats`, {
        headers: getApiHeaders(),
      });
      if (!res.ok) throw new Error(`載入失敗 (${res.status})`);
      setStats(await res.json());
    } catch (e: any) {
      setError(e.message || '載入失敗');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLog = useCallback(async () => {
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/kg/etl-log?lines=50`, {
        headers: getApiHeaders(),
      });
      if (res.ok) {
        const data: ETLLogResponse = await res.json();
        setEtlLog(data.lines || []);
        setLogSource(data.source);
      }
    } catch {
      // 靜默失敗；log 非關鍵
    }
  }, []);

  const triggerRebuild = useCallback(async () => {
    setRebuilding(true);
    setRebuildMsg('啟動中…');
    try {
      const res = await fetch(`${STREAM_API_URL}/api/admin/kg/rebuild`, {
        method: 'POST',
        headers: getApiHeaders(),
      });
      if (!res.ok) throw new Error(`失敗 (${res.status})`);
      const data = await res.json();
      setRebuildMsg(`${data.status}: ${data.message} (job=${data.job_id})`);
    } catch (e: any) {
      setRebuildMsg(e.message || '觸發失敗');
    } finally {
      setRebuilding(false);
      loadLog();
    }
  }, [loadLog]);

  useEffect(() => {
    loadStats();
    loadLog();
  }, [loadStats, loadLog]);

  if (loading) {
    return (
      <div style={{ padding: '2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <InProgress size={18} /> 載入中…
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div style={{ padding: '2rem' }}>
        <div style={{ color: 'var(--danger, #dc2626)' }}>{error || '無法載入統計資料'}</div>
        <button
          onClick={loadStats}
          style={{
            marginTop: '0.5rem',
            padding: '0.375rem 0.75rem',
            background: 'var(--primary, #3B82F6)',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          重試
        </button>
      </div>
    );
  }

  const totalNodes = Object.values(stats.node_counts).reduce((a, b) => a + b, 0);
  const totalEdges = Object.values(stats.edge_counts).reduce((a, b) => a + b, 0);

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1200 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <ChartNetwork size={24} />
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>知識圖譜監控</h1>
        {stats.source === 'mock' && (
          <span
            style={{
              marginLeft: '0.5rem',
              padding: '0.125rem 0.5rem',
              background: '#fef3c7',
              color: '#92400e',
              borderRadius: 4,
              fontSize: '0.75rem',
            }}
            title="W1-T3 ETL 尚未完成，顯示的是 mock 數據"
          >
            MOCK 資料
          </span>
        )}
      </div>

      {/* 總覽 */}
      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>總覽</h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '0.75rem',
          }}
        >
          <StatCard label="總節點數" value={totalNodes.toLocaleString()} />
          <StatCard label="總關係數" value={totalEdges.toLocaleString()} />
          <StatCard
            label="Clean 覆蓋率"
            value={`${(stats.clean_coverage * 100).toFixed(1)}%`}
            hint="clean subset / 總 WorkOrder"
          />
          <StatCard
            label="最近 ETL"
            value={
              stats.last_etl_time
                ? new Date(stats.last_etl_time).toLocaleString('zh-TW')
                : '—'
            }
            hint={stats.last_etl_status}
          />
        </div>
      </section>

      {/* 節點分佈 */}
      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
          節點分佈（依 Label）
        </h2>
        <div style={{ border: '1px solid var(--border, #e5e7eb)', borderRadius: 8, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead style={{ background: 'var(--bg-secondary, #f9fafb)' }}>
              <tr>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Label</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>節點數</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats.node_counts).map(([k, v]) => (
                <tr key={k} style={{ borderTop: '1px solid var(--border, #e5e7eb)' }}>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{k}</td>
                  <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {v.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 關係分佈 */}
      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
          關係分佈（依 Relationship Type）
        </h2>
        <div style={{ border: '1px solid var(--border, #e5e7eb)', borderRadius: 8, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead style={{ background: 'var(--bg-secondary, #f9fafb)' }}>
              <tr>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Relationship</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'right' }}>邊數</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats.edge_counts).map(([k, v]) => (
                <tr key={k} style={{ borderTop: '1px solid var(--border, #e5e7eb)' }}>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{k}</td>
                  <td style={{ padding: '0.5rem 0.75rem', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {v.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 稀疏實體 */}
      {stats.sparse_entities.length > 0 && (
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            稀疏實體（邊數過少，建議補資料）
          </h2>
          <ul style={{ paddingLeft: '1.25rem', fontSize: '0.875rem', color: 'var(--text-secondary, #4b5563)' }}>
            {stats.sparse_entities.map((e, i) => (
              <li key={i} style={{ marginBottom: '0.25rem' }}>
                <strong>{e.type}</strong>: {e.code || e.id} · <span style={{ color: 'var(--text-muted, #9ca3af)' }}>{e.edges} 邊</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 操作 */}
      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>操作</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            onClick={triggerRebuild}
            disabled={rebuilding}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.375rem',
              padding: '0.5rem 1rem',
              background: rebuilding ? 'var(--text-muted, #9ca3af)' : 'var(--primary, #3B82F6)',
              color: '#fff',
              border: 'none',
              borderRadius: 4,
              cursor: rebuilding ? 'not-allowed' : 'pointer',
              fontSize: '0.875rem',
            }}
          >
            <Renew size={16} /> {rebuilding ? '啟動中…' : '觸發 ETL Rebuild'}
          </button>
          <button
            onClick={() => { loadStats(); loadLog(); }}
            style={{
              padding: '0.5rem 1rem',
              background: 'transparent',
              color: 'var(--text-primary, #1f2937)',
              border: '1px solid var(--border, #d1d5db)',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            重新整理
          </button>
          <StatusBadge status={stats.last_etl_status} />
        </div>
        {rebuildMsg && (
          <p style={{ marginTop: '0.5rem', fontSize: '0.8125rem', color: 'var(--text-muted, #6b7280)' }}>
            {rebuildMsg}
          </p>
        )}
      </section>

      {/* ETL Log */}
      <section>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
          <Terminal size={16} /> ETL Log（最近 50 行）
          {logSource === 'mock' && (
            <span style={{ fontSize: '0.6875rem', padding: '0.125rem 0.375rem', background: '#fef3c7', color: '#92400e', borderRadius: 3 }}>
              MOCK
            </span>
          )}
        </h2>
        <pre
          style={{
            background: '#1F2937',
            color: '#E5E7EB',
            padding: '0.75rem',
            borderRadius: 6,
            fontSize: '0.75rem',
            maxHeight: 320,
            overflow: 'auto',
            margin: 0,
          }}
        >
          {etlLog.join('\n') || '（無 log）'}
        </pre>
      </section>
    </div>
  );
}
