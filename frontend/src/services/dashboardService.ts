/**
 * Dashboard Service
 * Handles dashboard metrics and analytics API calls
 */

import {
  DashboardMetrics,
  ActivityTimelineResponse,
  TopTopicsResponse,
} from '@/types/dashboard';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

/**
 * Get complete dashboard metrics for the current user
 * @param refresh - Bypass cache and fetch fresh data
 * @returns DashboardMetrics object
 * @throws Error if request fails
 */
export async function getDashboardMetrics(refresh: boolean = false): Promise<DashboardMetrics> {
  try {
    const url = new URL(`${API_URL}/api/profile/dashboard/metrics`);
    if (refresh) {
      url.searchParams.append('refresh', 'true');
    }

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY && { 'X-API-Key': API_KEY }),
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || `Failed to fetch dashboard metrics: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error('Dashboard metrics fetch error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to fetch dashboard metrics'
    );
  }
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
  try {
    const url = new URL(`${API_URL}/api/profile/dashboard/activity`);
    url.searchParams.append('limit', limit.toString());
    url.searchParams.append('offset', offset.toString());

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY && { 'X-API-Key': API_KEY }),
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || `Failed to fetch activity: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error('Activity fetch error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to fetch activity'
    );
  }
}

/**
 * Get top searched topics
 * @param limit - Number of topics to return (default: 5)
 * @returns TopTopicsResponse with topic entries
 * @throws Error if request fails
 */
export async function getTopTopics(limit: number = 5): Promise<TopTopicsResponse> {
  try {
    const url = new URL(`${API_URL}/api/profile/dashboard/topics`);
    url.searchParams.append('limit', limit.toString());

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY && { 'X-API-Key': API_KEY }),
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || `Failed to fetch top topics: ${response.status} ${response.statusText}`
      );
    }

    return await response.json();
  } catch (error) {
    console.error('Top topics fetch error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to fetch top topics'
    );
  }
}
