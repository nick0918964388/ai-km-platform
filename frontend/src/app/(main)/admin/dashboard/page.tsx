'use client';

import { useState, useEffect } from 'react';
import {
  Dashboard,
  Document,
  Chat,
  User,
  Activity,
  CheckmarkFilled,
  WarningFilled,
  Upload,
  Settings,
  Time
} from '@carbon/icons-react';

interface SystemStats {
  documents: number;
  conversations: number;
  users: number;
  status: 'healthy' | 'warning' | 'error';
}

interface RecentActivity {
  id: string;
  type: 'upload' | 'chat' | 'user' | 'setting';
  message: string;
  time: string;
  user: string;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<SystemStats>({
    documents: 0,
    conversations: 0,
    users: 4,
    status: 'healthy'
  });

  const [activities, setActivities] = useState<RecentActivity[]>([
    { id: '1', type: 'upload', message: '上傳了「引擎維修手冊.pdf」', time: '5 分鐘前', user: '管理員' },
    { id: '2', type: 'chat', message: '發起了新對話「引擎異響問題」', time: '10 分鐘前', user: '技師 A' },
    { id: '3', type: 'user', message: '新增了使用者「技師 C」', time: '1 小時前', user: '管理員' },
    { id: '4', type: 'setting', message: '更新了系統設定', time: '2 小時前', user: '管理員' },
    { id: '5', type: 'chat', message: '完成了對話「煞車異音診斷」', time: '3 小時前', user: '技師 B' },
  ]);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch stats from API
    const fetchStats = async () => {
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/kb/documents`);
        if (res.ok) {
          const data = await res.json();
          setStats(prev => ({
            ...prev,
            documents: data.documents?.length || 0
          }));
        }
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'upload': return <Upload size={16} />;
      case 'chat': return <Chat size={16} />;
      case 'user': return <User size={16} />;
      case 'setting': return <Settings size={16} />;
      default: return <Activity size={16} />;
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ 
        fontSize: '1.75rem', 
        fontWeight: 600, 
        marginBottom: '2rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem'
      }}>
        <Dashboard size={28} />
        儀表板
      </h1>

      {/* Stats Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '1.5rem',
        marginBottom: '2rem'
      }}>
        {/* Documents */}
        <div className="settings-section" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: 'var(--primary-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--primary)'
            }}>
              <Document size={24} />
            </div>
            <div>
              <div style={{ fontSize: '2rem', fontWeight: 600 }}>
                {loading ? '...' : stats.documents}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                知識庫文件
              </div>
            </div>
          </div>
        </div>

        {/* Conversations */}
        <div className="settings-section" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: '#e8f5e9',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#4caf50'
            }}>
              <Chat size={24} />
            </div>
            <div>
              <div style={{ fontSize: '2rem', fontWeight: 600 }}>
                {stats.conversations}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                總對話數
              </div>
            </div>
          </div>
        </div>

        {/* Users */}
        <div className="settings-section" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: '#fff3e0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ff9800'
            }}>
              <User size={24} />
            </div>
            <div>
              <div style={{ fontSize: '2rem', fontWeight: 600 }}>
                {stats.users}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                使用者數
              </div>
            </div>
          </div>
        </div>

        {/* System Status */}
        <div className="settings-section" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: stats.status === 'healthy' ? '#e8f5e9' : '#ffebee',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: stats.status === 'healthy' ? '#4caf50' : '#f44336'
            }}>
              {stats.status === 'healthy' ? <CheckmarkFilled size={24} /> : <WarningFilled size={24} />}
            </div>
            <div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600, color: stats.status === 'healthy' ? '#4caf50' : '#f44336' }}>
                {stats.status === 'healthy' ? '運作正常' : '需要注意'}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                系統狀態
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="settings-section" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem' }}>
          快速操作
        </h2>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <a href="/admin/knowledge-base" className="btn btn-primary" style={{ textDecoration: 'none' }}>
            <Upload size={16} />
            上傳文件
          </a>
          <a href="/chat" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
            <Chat size={16} />
            開始對話
          </a>
          <a href="/admin/users" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
            <User size={16} />
            管理使用者
          </a>
          <a href="/settings" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
            <Settings size={16} />
            系統設定
          </a>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="settings-section" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={20} />
          最近活動
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {activities.map(activity => (
            <div 
              key={activity.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '1rem',
                padding: '0.75rem',
                background: 'var(--bg-secondary)',
                borderRadius: '8px'
              }}
            >
              <div style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'var(--bg-primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-secondary)'
              }}>
                {getActivityIcon(activity.type)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '0.875rem' }}>
                  <strong>{activity.user}</strong> {activity.message}
                </div>
              </div>
              <div style={{ 
                fontSize: '0.75rem', 
                color: 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem'
              }}>
                <Time size={12} />
                {activity.time}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
