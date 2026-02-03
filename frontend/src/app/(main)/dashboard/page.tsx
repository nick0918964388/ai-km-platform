'use client';

import { useEffect } from 'react';
import { Button } from '@carbon/react';
import { Renew, DocumentBlank, Search, Star, Calendar } from '@carbon/icons-react';
import { useProfileDashboard } from '@/hooks/useProfileDashboard';
import MetricsCard from '@/components/dashboard/MetricsCard';
import ActivityTimeline from '@/components/dashboard/ActivityTimeline';
import TopTopics from '@/components/dashboard/TopTopics';

export default function DashboardPage() {
  const {
    dashboardMetrics,
    dashboardLoading,
    dashboardError,
    fetchDashboard,
    refreshDashboard,
  } = useProfileDashboard();

  // Fetch dashboard on mount
  useEffect(() => {
    if (!dashboardMetrics) {
      fetchDashboard();
    }
  }, [dashboardMetrics, fetchDashboard]);

  // Format account creation date
  const formatCreatedAt = (dateString?: string) => {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  // Format account level
  const formatAccountLevel = (level?: string) => {
    if (!level) return 'Free';
    return level.charAt(0).toUpperCase() + level.slice(1);
  };

  return (
    <div className="p-6 md:p-8">
      {/* Page Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold mb-2">Dashboard</h1>
          <p className="text-gray-600">
            {dashboardMetrics
              ? `Welcome back, ${dashboardMetrics.display_name}!`
              : 'Overview of your activity and metrics'}
          </p>
        </div>

        {/* Refresh Button */}
        <Button
          kind="ghost"
          size="md"
          renderIcon={Renew}
          onClick={refreshDashboard}
          disabled={dashboardLoading}
          iconDescription="Refresh dashboard"
        >
          {dashboardLoading ? 'Refreshing...' : 'Refresh'}
        </Button>
      </div>

      {/* Error State */}
      {dashboardError && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-800 font-medium">Failed to load dashboard</p>
          <p className="text-sm text-red-600 mt-1">{dashboardError}</p>
          <Button
            kind="danger--tertiary"
            size="sm"
            onClick={() => fetchDashboard()}
            className="mt-3"
          >
            Try Again
          </Button>
        </div>
      )}

      {/* Metrics Grid - 4 Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricsCard
          title="Documents"
          value={dashboardMetrics?.document_count ?? 0}
          icon={DocumentBlank}
          iconColor="text-blue-600"
          loading={dashboardLoading && !dashboardMetrics}
        />
        <MetricsCard
          title="Queries"
          value={dashboardMetrics?.query_count ?? 0}
          icon={Search}
          iconColor="text-green-600"
          loading={dashboardLoading && !dashboardMetrics}
        />
        <MetricsCard
          title="Account Level"
          value={formatAccountLevel(dashboardMetrics?.account_level)}
          icon={Star}
          iconColor="text-purple-600"
          loading={dashboardLoading && !dashboardMetrics}
        />
        <MetricsCard
          title="Member Since"
          value={
            dashboardMetrics?.created_at
              ? new Date(dashboardMetrics.created_at).toLocaleDateString('en-US', {
                  month: 'short',
                  year: 'numeric',
                })
              : 'N/A'
          }
          icon={Calendar}
          iconColor="text-orange-600"
          loading={dashboardLoading && !dashboardMetrics}
        />
      </div>

      {/* Activity & Topics Grid - 2 Tiles */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Activity */}
        <ActivityTimeline
          activities={dashboardMetrics?.recent_activity ?? []}
          loading={dashboardLoading && !dashboardMetrics}
        />

        {/* Top Topics */}
        <TopTopics
          topics={dashboardMetrics?.top_topics ?? []}
          loading={dashboardLoading && !dashboardMetrics}
        />
      </div>
    </div>
  );
}
