'use client';

import type { TopicEntry } from '@/types/dashboard';

interface TopTopicsProgressProps {
  topics: TopicEntry[];
  loading?: boolean;
}

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444'];

// Mock data
const mockTopics = [
  { query_text: 'API 整合', count: 234 },
  { query_text: '資料庫設計', count: 189 },
  { query_text: '安全性設定', count: 156 },
];

export default function TopTopicsProgress({ topics, loading }: TopTopicsProgressProps) {
  if (loading) {
    return (
      <div className="space-y-5">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse">
            <div className="flex justify-between mb-2">
              <div className="h-4 bg-gray-100 rounded w-1/3" />
              <div className="h-4 bg-gray-100 rounded w-12" />
            </div>
            <div className="h-2 bg-gray-100 rounded-full" />
          </div>
        ))}
      </div>
    );
  }

  const displayTopics = topics.length > 0 ? topics.slice(0, 5) : mockTopics;
  const maxCount = displayTopics.length > 0 ? Math.max(...displayTopics.map(t => t.count)) : 1;

  if (displayTopics.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        <p>尚無搜尋記錄</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {displayTopics.map((topic, index) => {
        const percentage = maxCount > 0 ? (topic.count / maxCount) * 100 : 0;
        const color = COLORS[index % COLORS.length];

        return (
          <div key={index}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700">{topic.query_text}</span>
              <span className="text-sm font-semibold text-gray-900">{topic.count} 次</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${percentage}%`,
                  backgroundColor: color,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
