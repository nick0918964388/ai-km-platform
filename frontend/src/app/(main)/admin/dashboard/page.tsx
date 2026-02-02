'use client';

import Link from 'next/link';
import {
  Chat,
  Search,
  Upload,
  Document,
  ArrowUp,
  Notification,
  Bot,
  DataBase,
  CheckmarkFilled,
  Time,
} from '@carbon/icons-react';

interface StatCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: React.ReactNode;
  iconBg: string;
}

function StatCard({ title, value, change, changeType = 'neutral', icon, iconBg }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-card-header">
        <span className="stat-card-title">{title}</span>
        <div className="stat-card-icon" style={{ background: iconBg }}>
          {icon}
        </div>
      </div>
      <div className="stat-card-value">{value}</div>
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
          marginBottom: '0.125rem'
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

export default function DashboardPage() {
  const recentQueries = [
    {
      icon: <Chat size={18} />,
      title: 'EMU900 引擎維修手冊查詢',
      subtitle: '找到 3 份相關文件',
      time: '5 分鐘前'
    },
    {
      icon: <Document size={18} />,
      title: '柴電機車 R100 保養紀錄查詢',
      subtitle: '已匯出 PDF 報表',
      time: '1 小時前'
    },
    {
      icon: <Search size={18} />,
      title: '普悠瑪號轉向架維修作業流程',
      subtitle: '檢視完整作業程序',
      time: '2 小時前'
    },
  ];

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
            歡迎回來，王小明
          </p>
        </div>
        <button className="btn-icon">
          <Notification size={20} />
        </button>
      </div>

      {/* Stats Grid */}
      <div className="dashboard-grid" style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.25rem',
        marginBottom: '1.5rem'
      }}>
        <StatCard
          title="今日查詢次數"
          value="128"
          change="↑ 12% 較昨日"
          changeType="positive"
          icon={<Chat size={20} style={{ color: 'var(--accent)' }} />}
          iconBg="var(--primary-light)"
        />
        <StatCard
          title="回覆滿意度"
          value="1,456"
          change="本月累計"
          changeType="neutral"
          icon={<CheckmarkFilled size={20} style={{ color: 'var(--success)' }} />}
          iconBg="var(--success-light)"
        />
        <StatCard
          title="知識庫文件"
          value="3,892"
          change="↑ 23 本週新增"
          changeType="positive"
          icon={<DataBase size={20} style={{ color: 'var(--accent)' }} />}
          iconBg="var(--primary-light)"
        />
        <StatCard
          title="系統準確率"
          value="96.8%"
          change="優於目標 95%"
          changeType="positive"
          icon={<Bot size={20} style={{ color: 'var(--accent)' }} />}
          iconBg="var(--primary-light)"
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
            {recentQueries.map((query, index) => (
              <QueryItem key={index} {...query} />
            ))}
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
