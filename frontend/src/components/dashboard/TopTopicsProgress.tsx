'use client';

import type { TopicEntry } from '@/types/dashboard';

interface TopTopicsProgressProps {
  topics: TopicEntry[];
  loading?: boolean;
}

const COLORS = ['#c96442', '#d97757', '#87867f', '#4d4c48', '#b0aea5'];

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
              <div style={{ height: '1rem', background: 'var(--border-light)', borderRadius: '4px', width: '33%' }} />
              <div style={{ height: '1rem', background: 'var(--border-light)', borderRadius: '4px', width: '3rem' }} />
            </div>
            <div style={{ height: '0.5rem', background: 'var(--border-light)', borderRadius: '9999px' }} />
          </div>
        ))}
      </div>
    );
  }

  const displayTopics = topics.length > 0 ? topics.slice(0, 5) : mockTopics;
  const maxCount = displayTopics.length > 0 ? Math.max(...displayTopics.map(t => t.count)) : 1;

  if (displayTopics.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-muted)' }}>
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
              <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>{topic.query_text}</span>
              <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>{topic.count} 次</span>
            </div>
            <div style={{ height: '0.5rem', background: 'var(--border-light)', borderRadius: '9999px', overflow: 'hidden' }}>
              <div
                className="transition-all duration-500"
                style={{
                  height: '100%',
                  borderRadius: '9999px',
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
