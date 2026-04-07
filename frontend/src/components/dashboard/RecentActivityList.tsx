'use client';

import { Search, DocumentAdd, Settings } from '@carbon/icons-react';
import type { ActivityEntry } from '@/types/dashboard';

interface RecentActivityListProps {
  activities: ActivityEntry[];
  loading?: boolean;
}

function getActivityIcon(actionType: string) {
  switch (actionType) {
    case 'query':
      return { icon: Search, bgColor: 'bg-blue-50', iconColor: 'text-blue-600' };
    case 'document_upload':
      return { icon: DocumentAdd, bgColor: 'bg-green-50', iconColor: 'text-green-600' };
    default:
      return { icon: Settings, bgColor: 'bg-gray-50', iconColor: 'text-gray-600' };
  }
}

function getActivityLabel(activity: ActivityEntry): string {
  switch (activity.action_type) {
    case 'query':
      return activity.metadata?.query_text
        ? `搜尋「${activity.metadata.query_text.slice(0, 20)}${activity.metadata.query_text.length > 20 ? '...' : ''}」`
        : '執行搜尋';
    case 'document_upload':
      return activity.metadata?.filename
        ? `上傳「${activity.metadata.filename}」`
        : '上傳文件';
    default:
      return 'AI 回答';
  }
}

function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);

    if (diffMins < 1) return '剛剛';
    if (diffMins < 60) return `${diffMins} 分鐘前`;
    if (diffHours < 24) return `${diffHours} 小時前`;
    return date.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' });
  } catch {
    return timestamp;
  }
}

// Mock data
const mockActivities = [
  { action_type: 'query', timestamp: new Date(Date.now() - 5 * 60000).toISOString(), metadata: { query_text: 'API 整合指南' } },
  { action_type: 'document_upload', timestamp: new Date(Date.now() - 60 * 60000).toISOString(), metadata: { filename: 'Q4 財務報表.pdf' } },
  { action_type: 'query', timestamp: new Date(Date.now() - 3 * 3600000).toISOString(), metadata: { query_text: '如何設定權限？' } },
];

export default function RecentActivityList({ activities, loading }: RecentActivityListProps) {
  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-4 animate-pulse">
            <div className="w-10 h-10 bg-gray-100 rounded-xl" />
            <div className="flex-1">
              <div className="h-4 bg-gray-100 rounded w-3/4 mb-2" />
              <div className="h-3 bg-gray-100 rounded w-1/4" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const displayActivities = activities.length > 0 ? activities.slice(0, 5) : mockActivities;

  if (displayActivities.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        <p>尚無活動記錄</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {displayActivities.map((activity, index) => {
        const { icon: Icon, bgColor, iconColor } = getActivityIcon(activity.action_type);
        const label = getActivityLabel(activity as ActivityEntry);
        const time = formatTimestamp(activity.timestamp);

        return (
          <div key={index} className="flex items-center gap-4">
            <div className={`w-10 h-10 ${bgColor} rounded-xl flex items-center justify-center flex-shrink-0`}>
              <Icon size={20} className={iconColor} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{label}</p>
              <p className="text-xs text-gray-400">{time}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
