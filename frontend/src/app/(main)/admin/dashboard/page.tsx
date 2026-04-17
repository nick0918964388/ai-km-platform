'use client';

import { useEffect, useState, useCallback } from 'react';
import { Button } from '@carbon/react';
import { Renew, WarningFilled, Activity, Asset, TaskComplete } from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import { apiGet, getErrorMessage } from '@/lib/api';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LineChart, Line,
  PieChart, Pie,
} from 'recharts';

const COLORS = ['#E07850', '#D4A574', '#8B9DC3', '#6B8F71', '#C9B99A', '#B07D62'];

interface DashboardStats {
  summary: {
    total_workorders: number;
    active_workorders: number;
    total_faults: number;
    total_assets: number;
    open_faults: number;
  };
  workorder_by_status: { status: string; count: number }[];
  fault_trend: { date: string; count: number }[];
  fault_by_status: { status: string; count: number }[];
  workorder_by_depot: { depot: string; count: number }[];
  recent_faults: { id: string; description: string; status: string; date: string }[];
}

function SummaryCard({ title, value, sub, icon, color }: {
  title: string; value: number | string; sub?: string;
  icon: React.ReactNode; color: string;
}) {
  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--border-light)',
      borderRadius: '16px', padding: '1.5rem',
      display: 'flex', flexDirection: 'column', gap: '0.75rem',
    }}>
      <div className="flex items-center justify-between">
        <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>{title}</span>
        <div style={{
          width: '3rem', height: '3rem', borderRadius: '10px',
          background: color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {icon}
        </div>
      </div>
      <p style={{ fontSize: '2.25rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </p>
      {sub && <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{sub}</span>}
    </div>
  );
}

function ChartCard({ title, badge, children }: {
  title: string; badge?: string; children: React.ReactNode;
}) {
  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--border-light)',
      borderRadius: '16px', padding: '1.5rem', minWidth: 0,
    }}>
      <div className="flex items-center justify-between mb-6">
        <h3 style={{ fontSize: '1.125rem', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif' }}>
          {title}
        </h3>
        {badge && (
          <span style={{
            padding: '0.2rem 0.75rem', background: 'var(--bg-tertiary)',
            color: 'var(--text-muted)', fontSize: '0.8125rem', borderRadius: '6px',
          }}>{badge}</span>
        )}
      </div>
      {children}
    </div>
  );
}

const tooltipStyle = {
  backgroundColor: '#141413', border: 'none', borderRadius: '8px',
  color: '#b0aea5', padding: '8px 12px',
};

export default function AdminDashboardPage() {
  const user = useStore((s) => s.user);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<DashboardStats>('/api/dashboard/stats');
      setStats(data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const s = stats?.summary;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <div style={{ padding: '1.5rem 2rem' }}>
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 style={{ fontSize: 'clamp(1.25rem, 4vw, 1.75rem)', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif', marginBottom: '0.25rem' }}>
              營運儀表板
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9375rem' }}>
              {`歡迎回來，${user?.name ?? 'User'}`}
            </p>
          </div>
          <Button kind="ghost" size="sm" renderIcon={Renew} onClick={fetchData}
            disabled={loading} hasIconOnly iconDescription="重新整理" className="!rounded-full" />
        </div>

        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', background: 'var(--error-light)', border: '1px solid var(--error)', borderRadius: '12px' }}>
            <p style={{ color: 'var(--error)', fontWeight: 500 }}>{error}</p>
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <SummaryCard title="工單總數" value={s?.total_workorders ?? '...'} sub="全部工單"
            icon={<TaskComplete size={24} style={{ color: '#E07850' }} />} color="#E07850" />
          <SummaryCard title="執行中工單" value={s?.active_workorders ?? '...'} sub="未完成"
            icon={<Activity size={24} style={{ color: '#8B9DC3' }} />} color="#8B9DC3" />
          <SummaryCard title="故障通報" value={s?.total_faults ?? '...'} sub={`未結案 ${s?.open_faults ?? '...'}`}
            icon={<WarningFilled size={24} style={{ color: '#D4A574' }} />} color="#D4A574" />
          <SummaryCard title="車輛資產" value={s?.total_assets ?? '...'} sub="列管數"
            icon={<Asset size={24} style={{ color: '#6B8F71' }} />} color="#6B8F71" />
        </div>

        {/* Charts Row 1 */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
          <div className="lg:col-span-2">
            <ChartCard title="工單狀態分布">
              <div style={{ height: 280 }}>
                {loading ? (
                  <div className="h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>載入中...</div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={stats?.workorder_by_status?.slice(0, 8)} layout="vertical" margin={{ left: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e8e6dc" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 12, fill: '#87867f' }} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="status" width={100}
                        tick={{ fontSize: 11, fill: '#87867f' }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle}
                        formatter={(v: number) => [`${v.toLocaleString()} 筆`, '工單']} />
                      <Bar dataKey="count" radius={[0, 6, 6, 0]} maxBarSize={28}>
                        {stats?.workorder_by_status?.slice(0, 8).map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>
          </div>

          <ChartCard title="故障狀態">
            <div className="flex flex-col items-center gap-4">
              <div style={{ width: 180, height: 180 }}>
                {loading ? (
                  <div className="h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>載入中...</div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={stats?.fault_by_status} cx="50%" cy="50%"
                        innerRadius={50} outerRadius={80} paddingAngle={2}
                        dataKey="count" nameKey="status" strokeWidth={0}>
                        {stats?.fault_by_status?.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={tooltipStyle}
                        formatter={(v: number) => [`${v} 筆`, '通報']} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-2 justify-center">
                {stats?.fault_by_status?.map((item, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS[i % COLORS.length] }} />
                    <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                      {item.status} ({item.count})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </ChartCard>
        </div>

        {/* Charts Row 2 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
          <ChartCard title="故障趨勢" badge="近 30 天">
            <div style={{ height: 250 }}>
              {loading ? (
                <div className="h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>載入中...</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={stats?.fault_trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e8e6dc" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#87867f' }} axisLine={false} tickLine={false}
                      tickFormatter={(v) => v ? v.slice(5) : ''} />
                    <YAxis tick={{ fontSize: 12, fill: '#87867f' }} axisLine={false} tickLine={false} width={35} />
                    <Tooltip contentStyle={tooltipStyle}
                      formatter={(v: number) => [`${v} 件`, '故障']}
                      labelFormatter={(l) => `日期: ${l}`} />
                    <Line type="monotone" dataKey="count" stroke="#E07850" strokeWidth={2.5}
                      dot={{ r: 3, fill: '#E07850' }} activeDot={{ r: 5 }} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </ChartCard>

          <ChartCard title="工單配屬段分布">
            <div style={{ height: 250 }}>
              {loading ? (
                <div className="h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>載入中...</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats?.workorder_by_depot?.slice(0, 10)}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e8e6dc" vertical={false} />
                    <XAxis dataKey="depot" tick={{ fontSize: 11, fill: '#87867f' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 12, fill: '#87867f' }} axisLine={false} tickLine={false} width={45} />
                    <Tooltip contentStyle={tooltipStyle}
                      formatter={(v: number) => [`${v.toLocaleString()} 筆`, '工單']} />
                    <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={40}>
                      {stats?.workorder_by_depot?.slice(0, 10).map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </ChartCard>
        </div>

        {/* Recent Faults Table */}
        <ChartCard title="最新故障通報" badge="最近 5 筆">
          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>載入中...</div>
          ) : !stats?.recent_faults?.length ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>無資料</div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-light)' }}>
                    {['單號', '描述', '狀態', '日期'].map((h) => (
                      <th key={h} style={{
                        textAlign: 'left', padding: '0.75rem', fontWeight: 600,
                        color: 'var(--text-secondary)', fontSize: '0.8125rem',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_faults.map((f) => (
                    <tr key={f.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: '0.75rem', fontWeight: 500, color: 'var(--text-primary)' }}>{f.id}</td>
                      <td style={{ padding: '0.75rem', color: 'var(--text-secondary)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {f.description || '-'}
                      </td>
                      <td style={{ padding: '0.75rem' }}>
                        <span style={{
                          display: 'inline-block', padding: '0.15rem 0.6rem', borderRadius: '6px',
                          fontSize: '0.75rem', fontWeight: 600,
                          background: f.status === '結案' ? '#6B8F7120' : f.status === '取消' ? '#87867f20' : '#E0785020',
                          color: f.status === '結案' ? '#6B8F71' : f.status === '取消' ? '#87867f' : '#E07850',
                        }}>{f.status}</span>
                      </td>
                      <td style={{ padding: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                        {f.date ? f.date.slice(0, 10) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
