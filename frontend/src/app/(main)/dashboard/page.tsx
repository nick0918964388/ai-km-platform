'use client';

import { useEffect } from 'react';
import { Button } from '@carbon/react';
import { Renew, DocumentBlank, Search, Star, Calendar, ArrowUpRight, ArrowDownRight } from '@carbon/icons-react';
import { useProfileDashboard } from '@/hooks/useProfileDashboard';
import { useStore } from '@/store/useStore';

// Components
import QueryBarChart from '@/components/dashboard/QueryBarChart';
import QueryTrendChart from '@/components/dashboard/QueryTrendChart';
import UsageStatisticsChart from '@/components/dashboard/UsageStatisticsChart';
import FileTypePieChart from '@/components/dashboard/FileTypePieChart';
import RecentActivityList from '@/components/dashboard/RecentActivityList';
import TopTopicsProgress from '@/components/dashboard/TopTopicsProgress';

export default function DashboardPage() {
  const user = useStore((state) => state.user);
  const {
    dashboardMetrics,
    dashboardLoading,
    dashboardError,
    fetchDashboard,
    refreshDashboard,
  } = useProfileDashboard();

  useEffect(() => {
    fetchDashboard();
  }, []);

  const formatAccountLevel = (level?: string) => {
    if (!level) return 'Free';
    return level === 'pro' ? '專業版' : level.charAt(0).toUpperCase() + level.slice(1);
  };

  // Calculate days since joined
  const getDaysSinceJoined = (createdAt?: string) => {
    if (!createdAt) return 'N/A';
    const created = new Date(createdAt);
    const now = new Date();
    const diffTime = Math.abs(now.getTime() - created.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return `${diffDays} 天`;
  };

  const formatJoinDate = (createdAt?: string) => {
    if (!createdAt) return '';
    return new Date(createdAt).toLocaleDateString('zh-TW', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <div className="p-4 sm:p-6 lg:p-10">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-10">
          <div>
            <h1 style={{ fontSize: 'clamp(1.25rem, 4vw, 1.75rem)', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif', marginBottom: '0.25rem' }}>
              儀表板
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9375rem' }}>
              {`歡迎回來，${user?.name ?? dashboardMetrics?.display_name ?? 'User'}`}
            </p>
          </div>
          <Button
            kind="ghost"
            size="sm"
            renderIcon={Renew}
            onClick={refreshDashboard}
            disabled={dashboardLoading}
            hasIconOnly
            iconDescription="重新整理"
            className="!rounded-full"
          />
        </div>

        {/* Error State */}
        {dashboardError && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', background: 'var(--error-light)', border: '1px solid var(--error)', borderRadius: '12px' }}>
            <p style={{ color: 'var(--error)', fontWeight: 500 }}>載入儀表板失敗</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--error)', marginTop: '0.25rem', opacity: 0.8 }}>{dashboardError}</p>
          </div>
        )}

        {/* Metrics Grid - 4 Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-0 mb-10 overflow-hidden"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-light)', borderRadius: '16px', boxShadow: 'rgba(0,0,0,0.05) 0px 4px 24px' }}>
          {/* Documents — top-left */}
          <div style={{ background: 'var(--bg-secondary)', borderRight: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)', padding: '1.5rem' }}
            className="hover:bg-[#f0eee6] transition-all lg:[border-bottom:none]">
            <div className="flex items-center justify-between mb-4">
              <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>文件數據</span>
              <div style={{ width: '3rem', height: '3rem', background: 'var(--primary-light)', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <DocumentBlank size={24} style={{ color: 'var(--primary)' }} />
              </div>
            </div>
            <p style={{ fontSize: '2.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', lineHeight: 1 }}>
              {dashboardMetrics?.document_count?.toLocaleString() ?? '1,234'}
            </p>
            <div className="flex items-center gap-1" style={{ fontSize: '0.875rem', color: 'var(--success)' }}>
              <ArrowUpRight size={16} />
              <span>+12% 較上月</span>
            </div>
          </div>

          {/* Queries — top-right on mobile, 2nd on desktop */}
          <div style={{ background: 'var(--bg-secondary)', borderRight: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)', padding: '1.5rem' }}
            className="hover:bg-[#f0eee6] transition-all lg:[border-bottom:none]">
            <div className="flex items-center justify-between mb-4">
              <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>查詢次數</span>
              <div style={{ width: '3rem', height: '3rem', background: 'var(--primary-light)', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Search size={24} style={{ color: 'var(--primary)' }} />
              </div>
            </div>
            <p style={{ fontSize: '2.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', lineHeight: 1 }}>
              {dashboardMetrics?.query_count?.toLocaleString() ?? '5,678'}
            </p>
            <div className="flex items-center gap-1" style={{ fontSize: '0.875rem', color: 'var(--success)' }}>
              <ArrowUpRight size={16} />
              <span>+23% 較上月</span>
            </div>
          </div>

          {/* Account Level — bottom-left on mobile, 3rd on desktop */}
          <div style={{ background: 'var(--bg-secondary)', borderRight: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)', padding: '1.5rem' }}
            className="hover:bg-[#f0eee6] transition-all lg:[border-bottom:none]">
            <div className="flex items-center justify-between mb-4">
              <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>帳戶等級</span>
              <div style={{ width: '3rem', height: '3rem', background: '#f5ede8', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Star size={24} style={{ color: '#a34d30' }} />
              </div>
            </div>
            <p style={{ fontSize: '2.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', lineHeight: 1 }}>
              {formatAccountLevel(dashboardMetrics?.account_level)}
            </p>
            <span style={{ display: 'inline-block', padding: '0.2rem 0.75rem', background: 'var(--primary-light)', color: 'var(--primary)', fontSize: '0.75rem', fontWeight: 600, borderRadius: '6px' }}>
              PRO
            </span>
          </div>

          {/* Member Since — bottom-right on mobile, 4th on desktop */}
          <div style={{ background: 'var(--bg-secondary)', padding: '1.5rem' }}
            className="hover:bg-[#f0eee6] transition-all">
            <div className="flex items-center justify-between mb-4">
              <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>加入時間</span>
              <div style={{ width: '3rem', height: '3rem', background: 'var(--bg-tertiary)', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Calendar size={24} style={{ color: 'var(--text-secondary)' }} />
              </div>
            </div>
            <p style={{ fontSize: '2.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', lineHeight: 1 }}>
              {getDaysSinceJoined(dashboardMetrics?.created_at)}
            </p>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              {formatJoinDate(dashboardMetrics?.created_at)}
            </span>
          </div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 mb-10 overflow-hidden"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-light)', borderRadius: '16px', boxShadow: 'rgba(0,0,0,0.05) 0px 4px 24px' }}>
          {/* Query Bar Chart - 2 columns */}
          <div className="lg:col-span-2 p-4 sm:p-6 lg:p-8" style={{ borderBottom: '1px solid var(--border-light)', minWidth: 0 }}>
            <div className="flex items-center justify-between mb-8">
              <h3 style={{ fontSize: '1.125rem', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif' }}>查詢趨勢</h3>
              <span style={{ padding: '0.2rem 0.75rem', background: 'var(--bg-tertiary)', color: 'var(--text-muted)', fontSize: '0.875rem', borderRadius: '6px' }}>近 7 天</span>
            </div>
            <QueryBarChart
              data={dashboardMetrics?.query_trend}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>

          {/* File Type Pie Chart */}
          <div className="p-4 sm:p-6 lg:p-8" style={{ borderBottom: '1px solid var(--border-light)', minWidth: 0 }}>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif', marginBottom: '2rem' }}>文件類型分佈</h3>
            <FileTypePieChart
              data={dashboardMetrics?.file_type_distribution}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>
        </div>

        {/* Analytics Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 mb-10 overflow-hidden"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-light)', borderRadius: '16px', boxShadow: 'rgba(0,0,0,0.05) 0px 4px 24px' }}>
          {/* Query Trend Chart */}
          <div className="p-4 sm:p-6 lg:p-8" style={{ borderBottom: '1px solid var(--border-light)', minWidth: 0 }}>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif', marginBottom: '2rem' }}>查詢趨勢分析</h3>
            <QueryTrendChart
              data={dashboardMetrics?.query_trend}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>

          {/* Usage Statistics Chart */}
          <div className="p-4 sm:p-6 lg:p-8" style={{ borderBottom: '1px solid var(--border-light)', minWidth: 0 }}>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif', marginBottom: '2rem' }}>文件上傳統計</h3>
            <UsageStatisticsChart
              data={dashboardMetrics?.upload_stats}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>
        </div>

        {/* Bottom Row: Activity & Topics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 overflow-hidden"
          style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-light)', borderRadius: '16px', boxShadow: 'rgba(0,0,0,0.05) 0px 4px 24px' }}>
          {/* Recent Activity */}
          <div className="p-4 sm:p-6 lg:p-8" style={{ borderBottom: '1px solid var(--border-light)', minWidth: 0 }}>
            <div className="flex items-center justify-between mb-8">
              <h3 style={{ fontSize: '1.125rem', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif' }}>最近活動</h3>
              <button style={{ fontSize: '0.875rem', color: 'var(--primary)', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer' }}
                className="hover:underline">
                查看全部
              </button>
            </div>
            <RecentActivityList
              activities={dashboardMetrics?.recent_activity ?? []}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>

          {/* Top Topics */}
          <div className="p-4 sm:p-6 lg:p-8" style={{ minWidth: 0 }}>
            <div className="flex items-center justify-between mb-8">
              <h3 style={{ fontSize: '1.125rem', fontWeight: 500, color: 'var(--text-primary)', fontFamily: 'Georgia, serif' }}>熱門主題</h3>
              <ArrowUpRight size={20} style={{ color: 'var(--text-muted)' }} />
            </div>
            <TopTopicsProgress
              topics={dashboardMetrics?.top_topics ?? []}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
