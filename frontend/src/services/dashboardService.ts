/**
 * Dashboard Service
 * Handles dashboard metrics and analytics API calls
 */

import {
  DashboardMetrics,
  ActivityTimelineResponse,
  TopTopicsResponse,
} from '@/types/dashboard';
import { apiGet } from '@/lib/api';

/**
 * Get complete dashboard metrics for the current user
 * @param refresh - Bypass cache and fetch fresh data
 * @returns DashboardMetrics object
 * @throws Error if request fails
 */
export async function getDashboardMetrics(refresh: boolean = false): Promise<DashboardMetrics> {
  const qs = refresh ? '?refresh=true' : '';
  return apiGet<DashboardMetrics>(`/api/profile/dashboard/metrics${qs}`);
}

/**
 * Get recent activity entries with pagination
 * @param limit - Number of entries to return (default: 20)
 * @param offset - Number of entries to skip (default: 0)
 * @returns ActivityTimelineResponse with entries and pagination info
 * @throws Error if request fails
 */
export async function getRecentActivity(
  limit: number = 20,
  offset: number = 0
): Promise<ActivityTimelineResponse> {
  const qs = `?limit=${limit}&offset=${offset}`;
  return apiGet<ActivityTimelineResponse>(`/api/profile/dashboard/activity${qs}`);
}

/**
 * Get top searched topics
 * @param limit - Number of topics to return (default: 5)
 * @returns TopTopicsResponse with topic entries
 * @throws Error if request fails
 */
export async function getTopTopics(limit: number = 5): Promise<TopTopicsResponse> {
  return apiGet<TopTopicsResponse>(`/api/profile/dashboard/topics?limit=${limit}`);
}
