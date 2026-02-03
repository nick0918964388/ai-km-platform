/**
 * Dashboard-related TypeScript type definitions
 */

/**
 * Activity log entry
 */
export interface ActivityEntry {
  action_type: 'document_upload' | 'query' | 'profile_update';
  timestamp: string; // ISO 8601 format
  metadata?: Record<string, any>;
}

/**
 * Top searched topic entry
 */
export interface TopicEntry {
  query_text: string;
  count: number;
}

/**
 * Complete dashboard metrics
 */
export interface DashboardMetrics {
  user_id: string;
  display_name: string;
  account_level: string;
  created_at: string; // ISO 8601 format
  document_count: number;
  query_count: number;
  recent_activity: ActivityEntry[];
  top_topics: TopicEntry[];
}

/**
 * Activity timeline response with pagination
 */
export interface ActivityTimelineResponse {
  activities: ActivityEntry[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Top topics response
 */
export interface TopTopicsResponse {
  topics: TopicEntry[];
  total: number;
}

/**
 * Dashboard API error response
 */
export interface DashboardError {
  error: string;
  message: string;
  details?: Record<string, any>;
}
