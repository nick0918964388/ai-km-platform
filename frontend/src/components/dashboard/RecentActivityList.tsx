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
      return { icon: Search, bgStyle: { background: '#f9ede8' }, iconStyle: { color: '#c96442' } };
    case 'document_upload':
      return { icon: DocumentAdd, bgStyle: { background: '#edf5ee' }, iconStyle: { color: '#3a7d44' } };
    default:
      return { icon: Settings, bgStyle: { background: 'var(--bg-tertiary)' }, iconStyle: { color: 'var(--text-secondary)' } };
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
            <div style={{ width: '2.5rem', height: '2.5rem', background: 'var(--border-light)', borderRadius: '10px' }} />
            <div className="flex-1">
              <div style={{ height: '1rem', background: 'var(--border-light)', borderRadius: '4px', width: '75%', marginBottom: '0.5rem' }} />
              <div style={{ height: '0.75rem', background: 'var(--border-light)', borderRadius: '4px', width: '25%' }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const displayActivities = activities.length > 0 ? activities.slice(0, 5) : mockActivities;

  if (displayActivities.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-muted)' }}>
        <p>尚無活動記錄</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {displayActivities.map((activity, index) => {
        const { icon: Icon, bgStyle, iconStyle } = getActivityIcon(activity.action_type);
        const label = getActivityLabel(activity as ActivityEntry);
        const time = formatTimestamp(activity.timestamp);

        return (
          <div key={index} className="flex items-center gap-4">
            <div style={{ width: '2.5rem', height: '2.5rem', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, ...bgStyle }}>
              <Icon size={20} style={iconStyle} />
            </div>
            <div className="flex-1 min-w-0">
              <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-primary)' }} className="truncate">{label}</p>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{time}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
