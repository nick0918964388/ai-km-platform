'use client';

import { DocumentAdd, Search, UserAvatar, Renew } from '@carbon/icons-react';
import type { ActivityEntry } from '@/types/dashboard';

interface ActivityTimelineProps {
  /** Activity entries to display */
  activities: ActivityEntry[];
  /** Loading state */
  loading?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Get icon component for activity type
 */
function getActivityIcon(actionType: string) {
  switch (actionType) {
    case 'document_upload':
      return { icon: DocumentAdd, emoji: '📄', bgClass: 'bg-green-50' };
    case 'query':
      return { icon: Search, emoji: '💬', bgClass: 'bg-blue-50' };
    case 'profile_update':
      return { icon: UserAvatar, emoji: '🔧', bgClass: 'bg-orange-50' };
    default:
      return { icon: Renew, emoji: '🔄', bgClass: 'bg-gray-50' };
  }
}

/**
 * Get human-readable label for activity type
 */
function getActivityLabel(activity: ActivityEntry): string {
  switch (activity.action_type) {
    case 'document_upload':
      return activity.metadata?.filename
        ? `上傳「${activity.metadata.filename}」`
        : '上傳文件';
    case 'query':
      return activity.metadata?.query_text
        ? `查詢「${activity.metadata.query_text.slice(0, 20)}${activity.metadata.query_text.length > 20 ? '...' : ''}」`
        : '執行查詢';
    case 'profile_update':
      return '更新個人資料';
    default:
      return '活動';
  }
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return '剛剛';
    if (diffMins < 60) return `${diffMins} 分鐘前`;
    if (diffHours < 24) return `${diffHours} 小時前`;
    if (diffDays === 1) {
      return `昨天 ${date.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}`;
    }
    if (diffDays < 7) return `${diffDays} 天前`;

    return date.toLocaleDateString('zh-TW', {
      month: 'short',
      day: 'numeric',
    });
  } catch (error) {
    return timestamp;
  }
}

/**
 * ActivityTimeline Component
 * Displays chronological list of user activity entries
 */
export default function ActivityTimeline({
  activities,
  loading = false,
  className = '',
}: ActivityTimelineProps) {
  // Loading skeleton
  if (loading) {
    return (
      <div className={`bg-white rounded-xl p-6 shadow-sm ${className}`}>
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">⏱️</span>
          <h3 className="text-lg font-semibold text-gray-900">最近活動</h3>
          <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
            載入中
          </span>
        </div>
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center gap-3 py-3 border-b border-gray-100 last:border-0">
              <div className="w-9 h-9 bg-gray-100 rounded-full animate-pulse flex-shrink-0" />
              <div className="flex-1">
                <div className="h-4 bg-gray-100 rounded w-3/4 mb-2 animate-pulse" />
                <div className="h-3 bg-gray-100 rounded w-1/4 animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Empty state
  if (!activities || activities.length === 0) {
    return (
      <div className={`bg-white rounded-xl p-6 shadow-sm ${className}`}>
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">⏱️</span>
          <h3 className="text-lg font-semibold text-gray-900">最近活動</h3>
          <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
            0 筆
          </span>
        </div>
        <div className="text-center py-8">
          <Renew size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 font-medium mb-1">尚無活動記錄</p>
          <p className="text-sm text-gray-400">
            您的操作記錄將顯示在這裡
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`bg-white rounded-xl p-6 shadow-sm ${className}`}>
      <div className="flex items-center gap-2 mb-6">
        <span className="text-lg">⏱️</span>
        <h3 className="text-lg font-semibold text-gray-900">最近活動</h3>
        <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
          {activities.length} 筆
        </span>
      </div>

      {/* Timeline */}
      <div>
        {activities.slice(0, 5).map((activity, index) => {
          const { emoji, bgClass } = getActivityIcon(activity.action_type);
          const label = getActivityLabel(activity);
          const timestamp = formatTimestamp(activity.timestamp);

          return (
            <div
              key={index}
              className="flex items-center gap-3 py-3 border-b border-gray-100 last:border-0"
            >
              {/* Icon */}
              <div
                className={`flex-shrink-0 w-9 h-9 ${bgClass} rounded-full flex items-center justify-center text-base`}
              >
                {emoji}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{label}</p>
                <p className="text-xs text-gray-400">{timestamp}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
