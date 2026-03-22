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
    <div className="min-h-screen bg-gray-50/50">
      <div className="p-8 md:p-12 lg:p-16">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-10">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-1">
              儀表板
            </h1>
            <p className="text-gray-500">
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
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl">
            <p className="text-red-800 font-medium">載入儀表板失敗</p>
            <p className="text-sm text-red-600 mt-1">{dashboardError}</p>
          </div>
        )}

        {/* Metrics Grid - 4 Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-0 mb-10 bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
          {/* Documents */}
          <div className="bg-white border-r border-gray-200 p-6 hover:bg-gray-50 transition-all">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-gray-500">文件數據</span>
              <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center">
                <DocumentBlank size={24} className="text-blue-600" />
              </div>
            </div>
            <p className="text-4xl font-bold text-gray-900 mb-2">
              {dashboardMetrics?.document_count?.toLocaleString() ?? '1,234'}
            </p>
            <div className="flex items-center gap-1 text-sm text-green-600">
              <ArrowUpRight size={16} />
              <span>+12% 較上月</span>
            </div>
          </div>

          {/* Queries */}
          <div className="bg-white border-r border-gray-200 p-6 hover:bg-gray-50 transition-all sm:border-b lg:border-b-0">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-gray-500">查詢次數</span>
              <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center">
                <Search size={24} className="text-blue-600" />
              </div>
            </div>
            <p className="text-4xl font-bold text-gray-900 mb-2">
              {dashboardMetrics?.query_count?.toLocaleString() ?? '5,678'}
            </p>
            <div className="flex items-center gap-1 text-sm text-green-600">
              <ArrowUpRight size={16} />
              <span>+23% 較上月</span>
            </div>
          </div>

          {/* Account Level */}
          <div className="bg-white border-r border-gray-200 p-6 hover:bg-gray-50 transition-all sm:border-t lg:border-t-0">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-gray-500">帳戶等級</span>
              <div className="w-12 h-12 bg-purple-50 rounded-xl flex items-center justify-center">
                <Star size={24} className="text-purple-600" />
              </div>
            </div>
            <p className="text-4xl font-bold text-gray-900 mb-2">
              {formatAccountLevel(dashboardMetrics?.account_level)}
            </p>
            <span className="inline-block px-3 py-1 bg-purple-100 text-purple-700 text-xs font-semibold rounded-lg">
              PRO
            </span>
          </div>

          {/* Member Since */}
          <div className="bg-white p-6 hover:bg-gray-50 transition-all sm:border-t lg:border-t-0">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-gray-500">加入時間</span>
              <div className="w-12 h-12 bg-orange-50 rounded-xl flex items-center justify-center">
                <Calendar size={24} className="text-orange-600" />
              </div>
            </div>
            <p className="text-4xl font-bold text-gray-900 mb-2">
              {getDaysSinceJoined(dashboardMetrics?.created_at)}
            </p>
            <span className="text-sm text-gray-400">
              {formatJoinDate(dashboardMetrics?.created_at)}
            </span>
          </div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 mb-10 bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
          {/* Query Bar Chart - 2 columns */}
          <div className="lg:col-span-2 border-b lg:border-b-0 lg:border-r border-gray-200 p-8">
            <div className="flex items-center justify-between mb-8">
              <h3 className="text-xl font-semibold text-gray-900">查詢趨勢</h3>
              <span className="px-3 py-1 bg-gray-100 text-gray-500 text-sm rounded-lg">近 7 天</span>
            </div>
            <QueryBarChart
              data={dashboardMetrics?.query_trend}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>

          {/* File Type Pie Chart */}
          <div className="p-8">
            <h3 className="text-xl font-semibold text-gray-900 mb-8">文件類型分佈</h3>
            <FileTypePieChart
              data={dashboardMetrics?.file_type_distribution}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>
        </div>

        {/* Analytics Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 mb-10 bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
          {/* Query Trend Chart */}
          <div className="border-b lg:border-b-0 lg:border-r border-gray-200 p-8">
            <h3 className="text-xl font-semibold text-gray-900 mb-8">查詢趨勢分析</h3>
            <QueryTrendChart
              data={dashboardMetrics?.query_trend}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>

          {/* Usage Statistics Chart */}
          <div className="p-8">
            <h3 className="text-xl font-semibold text-gray-900 mb-8">文件上傳統計</h3>
            <UsageStatisticsChart
              data={dashboardMetrics?.upload_stats}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>
        </div>

        {/* Bottom Row: Activity & Topics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
          {/* Recent Activity */}
          <div className="border-b lg:border-b-0 lg:border-r border-gray-200 p-8">
            <div className="flex items-center justify-between mb-8">
              <h3 className="text-xl font-semibold text-gray-900">最近活動</h3>
              <button className="text-sm text-blue-600 hover:text-blue-700 font-medium hover:underline">
                查看全部
              </button>
            </div>
            <RecentActivityList
              activities={dashboardMetrics?.recent_activity ?? []}
              loading={dashboardLoading && !dashboardMetrics}
            />
          </div>

          {/* Top Topics */}
          <div className="p-8">
            <div className="flex items-center justify-between mb-8">
              <h3 className="text-xl font-semibold text-gray-900">熱門主題</h3>
              <ArrowUpRight size={20} className="text-gray-400" />
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
