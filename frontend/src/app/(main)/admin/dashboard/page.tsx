'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Chat,
  Search,
  Upload,
  Document,
  Notification,
  Bot,
  DataBase,
  WarningFilled,
  TaskComplete,
  Van,
} from '@carbon/icons-react';
import { useStore } from '@/store/useStore';
import { apiGet, getErrorMessage } from '@/lib/api';

interface DashboardSummary {
  total_documents: number;
  total_queries_today: number;
  total_vehicles: number;
  open_faults: number;
  pending_workorders: number;
}

interface RecentQuery {
  id: string;
  user_id: string | null;
  question: string | null;
  created_at: string | null;
}

interface StatCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: React.ReactNode;
  iconBg: string;
  loading?: boolean;
}

function StatCard({ title, value, change, changeType = 'neutral', icon, iconBg, loading }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-card-header">
        <span className="stat-card-title">{title}</span>
        <div className="stat-card-icon" style={{ background: iconBg }}>
          {icon}
        </div>
      </div>
      <div className="stat-card-value">
        {loading ? '...' : value}
      </div>
      {change && (
        <div className={`stat-card-change ${changeType}`}>
          {change}
        </div>
      )}
    </div>
  );
}

interface QueryItemProps {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  time: string;
}

function QueryItem({ icon, title, subtitle, time }: QueryItemProps) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: '0.75rem',
      padding: '0.75rem',
      background: 'var(--bg-primary)',
      borderRadius: 'var(--radius-md)',
    }}>
      <div style={{
        width: 40,
        height: 40,
        borderRadius: 'var(--radius-md)',
        background: 'var(--primary-light)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--accent)',
        flexShrink: 0,
      }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 500,
          color: 'var(--text-primary)',
          fontSize: '0.875rem',
          marginBottom: '0.125rem',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {title}
        </div>
        <div style={{
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
        }}>
          {subtitle}
        </div>
      </div>
      <div style={{
        fontSize: '0.75rem',
        color: 'var(--text-muted)',
        flexShrink: 0,
      }}>
        {time}
      </div>
    </div>
  );
}

interface QuickActionProps {
  icon: React.ReactNode;
  label: string;
  href: string;
  primary?: boolean;
}

function QuickAction({ icon, label, href, primary }: QuickActionProps) {
  return (
    <Link
      href={href}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.75rem',
        padding: '0.75rem 1rem',
        background: primary ? 'var(--primary)' : 'var(--bg-primary)',
        border: primary ? 'none' : '1px solid var(--border)',
        borderRadius: primary ? '10px' : 'var(--radius-md)',
        color: primary ? 'white' : 'var(--text-primary)',
        textDecoration: 'none',
        fontSize: '0.875rem',
        fontWeight: 500,
        height: primary ? 52 : 48,
        transition: 'all var(--transition-fast)',
      }}
    >
      {icon}
      {label}
    </Link>
  );
}

function formatTimeAgo(isoString: string): string {
  const now = new Date();
  const date = new Date(isoString);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '剛剛';
  if (diffMin < 60) return `${diffMin} 分鐘前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小時前`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay} 天前`;
}

export default function DashboardPage() {
  const user = useStore((s) => s.user);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [recentQueries, setRecentQueries] = useState<RecentQuery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError(null);
      try {
        const [summaryData, queriesData] = await Promise.all([
          apiGet<DashboardSummary>('/api/dashboard/summary'),
          apiGet<RecentQuery[]>('/api/dashboard/recent-queries?limit=5'),
        ]);
        if (!cancelled) {
          setSummary(summaryData);
          setRecentQueries(queriesData);
        }
      } catch (e) {
        if (!cancelled) {
          setError(getErrorMessage(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, []);

  const userName = user?.name || '使用者';

  return (
    <div style={{
      padding: '2rem',
      height: '100%',
      overflow: 'auto',
      background: 'var(--bg-primary)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '1.5rem'
      }}>
        <div>
          <h1 style={{
            fontSize: '1.75rem',
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginBottom: '0.25rem'
          }}>
            儀表板
          </h1>
          <p style={{
            fontSize: '0.875rem',
            color: 'var(--accent)'
          }}>
            歡迎回來，{userName}
          </p>
        </div>
        <button className="btn-icon">
          <Notification size={20} />
        </button>
      </div>

      {error && (
        <div style={{
          padding: '0.75rem 1rem',
          marginBottom: '1rem',
          background: 'var(--danger-light, #fff1f0)',
          border: '1px solid var(--danger, #da1e28)',
          borderRadius: 'var(--radius-md)',
          color: 'var(--danger, #da1e28)',
          fontSize: '0.875rem',
        }}>
          載入失敗：{error}
        </div>
      )}

      {/* Stats Grid */}
      <div className="dashboard-grid" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.25rem',
        marginBottom: '1.5rem'
      }}>
        <StatCard
          title="知識庫文件"
          value={summary?.total_documents ?? 0}
          icon={<DataBase size={20} style={{ color: 'var(--accent)' }} />}
          iconBg="var(--primary-light)"
          loading={loading}
        />
        <StatCard
          title="今日查詢"
          value={summary?.total_queries_today ?? 0}
          icon={<Chat size={20} style={{ color: 'var(--accent)' }} />}
          iconBg="var(--primary-light)"
          loading={loading}
        />
        <StatCard
          title="車輛資產"
          value={summary?.total_vehicles ?? 0}
          icon={<Van size={20} style={{ color: 'var(--accent)' }} />}
          iconBg="var(--primary-light)"
          loading={loading}
        />
        <StatCard
          title="故障通報"
          value={summary?.open_faults ?? 0}
          change={summary ? '未關閉' : undefined}
          changeType="neutral"
          icon={<WarningFilled size={20} style={{ color: 'var(--warning, #f1c21b)' }} />}
          iconBg="var(--warning-light, #fff8e1)"
          loading={loading}
        />
      </div>

      {/* Content Row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '1.25rem',
        minHeight: '400px'
      }}>
        {/* Recent Queries */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '1rem'
          }}>
            <h2 style={{
              fontSize: '1.125rem',
              fontWeight: 600,
              color: 'var(--text-primary)'
            }}>
              最近查詢
            </h2>
            <Link href="/history" style={{
              fontSize: '0.875rem',
              color: 'var(--accent)',
              textDecoration: 'none'
            }}>
              查看全部
            </Link>
          </div>
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
            flex: 1,
          }}>
            {loading ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: '1rem 0' }}>
                載入中...
              </div>
            ) : recentQueries.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: '1rem 0' }}>
                尚無查詢紀錄
              </div>
            ) : (
              recentQueries.map((q) => (
                <QueryItem
                  key={q.id}
                  icon={<Chat size={18} />}
                  title={q.question || '(無問題內容)'}
                  subtitle={q.user_id || ''}
                  time={q.created_at ? formatTimeAgo(q.created_at) : ''}
                />
              ))
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <h2 style={{
            fontSize: '1.125rem',
            fontWeight: 600,
            color: 'var(--text-primary)',
            marginBottom: '1rem'
          }}>
            快速操作
          </h2>
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem'
          }}>
            <QuickAction
              icon={<Bot size={20} />}
              label="開始 AI 問答"
              href="/chat"
              primary
            />
            <QuickAction
              icon={<Search size={18} />}
              label="搜尋知識庫"
              href="/admin/knowledge-base"
            />
            <QuickAction
              icon={<Upload size={18} />}
              label="上傳技術文件"
              href="/admin/knowledge-base"
            />
            <QuickAction
              icon={<Document size={18} />}
              label="匯出報表"
              href="/history"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
