/**
 * Dashboard Types
 * Type definitions for dashboard metrics and analytics
 */

export interface ActivityEntry {
  action_type: string;
  timestamp: string;
  metadata?: {
    query_text?: string;
    filename?: string;
    [key: string]: unknown;
  };
}

export interface TopicEntry {
  query_text: string;
  count: number;
}

export interface DashboardMetrics {
  total_documents: number;
  total_queries: number;
  recent_activities?: ActivityEntry[];
  recent_activity?: ActivityEntry[];
  top_topics?: TopicEntry[];
  account_level?: string;
  created_at?: string;
  display_name?: string;
  document_count?: number;
  query_count?: number;
  query_trend?: { date: string; count: number }[];
  file_type_distribution?: { name: string; value: number }[];
  upload_stats?: { date: string; uploads: number }[];
}

export interface ActivityTimelineResponse {
  entries: ActivityEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface TopTopicsResponse {
  topics: TopicEntry[];
  total: number;
}
