'use client';

import { useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getDashboardMetrics } from '@/services/dashboardService';

/**
 * Hook for managing user profile dashboard metrics state
 * Provides dashboard data, loading state, and refresh functions
 */
export function useProfileDashboard() {
  const dashboardMetrics = useStore((state) => state.dashboardMetrics);
  const dashboardLoading = useStore((state) => state.dashboardLoading);
  const dashboardError = useStore((state) => state.dashboardError);
  const setDashboardMetrics = useStore((state) => state.setDashboardMetrics);
  const clearDashboard = useStore((state) => state.clearDashboard);

  /**
   * Fetch dashboard metrics from API
   * @param refresh - Bypass cache and fetch fresh data
   */
  const fetchDashboard = useCallback(
    async (refresh: boolean = false) => {
      useStore.setState({ dashboardLoading: true, dashboardError: null });

      try {
        const metrics = await getDashboardMetrics(refresh);
        setDashboardMetrics(metrics);
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to fetch dashboard metrics';
        useStore.setState({ dashboardError: errorMessage });
        console.error('Error fetching dashboard:', error);
      } finally {
        useStore.setState({ dashboardLoading: false });
      }
    },
    [setDashboardMetrics]
  );

  /**
   * Refresh dashboard data (bypass cache)
   */
  const refreshDashboard = useCallback(async () => {
    await fetchDashboard(true);
  }, [fetchDashboard]);

  /**
   * Clear dashboard data from store
   */
  const clearDashboardData = useCallback(() => {
    clearDashboard();
  }, [clearDashboard]);

  return {
    dashboardMetrics,
    dashboardLoading,
    dashboardError,
    fetchDashboard,
    refreshDashboard,
    clearDashboardData,
  };
}
