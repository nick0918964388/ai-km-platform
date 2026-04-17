'use client';

import { Tile, SkeletonText } from '@carbon/react';
import { Search, ChartBar } from '@carbon/icons-react';
import type { TopicEntry } from '@/types/dashboard';

interface TopTopicsProps {
  /** Topic entries to display */
  topics: TopicEntry[];
  /** Loading state */
  loading?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * TopTopics Component
 * Displays list of most searched topics with counts
 *
 * Features:
 * - Ranked list of topics
 * - Query counts displayed prominently
 * - Visual bar indicators for relative popularity
 * - Empty state for users with no queries
 * - Loading skeleton state
 */
export default function TopTopics({
  topics,
  loading = false,
  className = '',
}: TopTopicsProps) {
  // Calculate max count for bar width scaling
  const maxCount = topics.length > 0 ? Math.max(...topics.map((t) => t.count)) : 1;

  // Loading skeleton
  if (loading) {
    return (
      <Tile className={`p-6 ${className}`}>
        <h3 className="text-lg font-semibold mb-4">Top Topics</h3>
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="w-6 h-6 bg-gray-200 rounded animate-pulse flex-shrink-0" />
              <div className="flex-1">
                <SkeletonText width="70%" />
                <div className="mt-2 h-2 bg-gray-200 rounded animate-pulse" />
              </div>
              <SkeletonText width="30px" />
            </div>
          ))}
        </div>
      </Tile>
    );
  }

  // Empty state
  if (!topics || topics.length === 0) {
    return (
      <Tile className={`p-6 ${className}`}>
        <h3 className="text-lg font-semibold mb-4">Top Topics</h3>
        <div className="text-center py-8">
          <Search size={48} className="mx-auto text-gray-400 mb-4" />
          <p className="text-gray-600 font-medium mb-2">No Search History</p>
          <p className="text-sm text-gray-500">
            Your most searched topics will appear here as you use the search feature
          </p>
        </div>
      </Tile>
    );
  }

  return (
    <Tile className={`p-6 ${className}`}>
      <h3 className="text-lg font-semibold mb-4">Top Topics</h3>

      {/* Topics List */}
      <div className="space-y-4">
        {topics.map((topic, index) => {
          const barWidth = maxCount > 0 ? (topic.count / maxCount) * 100 : 0;

          return (
            <div key={index} className="group">
              {/* Topic header */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className="text-xs font-semibold text-gray-500 flex-shrink-0">
                    #{index + 1}
                  </span>
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {topic.query_text}
                  </p>
                </div>
                <span className="text-sm font-semibold text-blue-600 ml-3">
                  {topic.count}
                </span>
              </div>

              {/* Visual bar indicator */}
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-300 group-hover:bg-blue-600"
                  style={{ width: `${barWidth}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      {topics.length > 0 && (
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <ChartBar size={16} />
            <span>Showing top {topics.length} most searched topics</span>
          </div>
        </div>
      )}
    </Tile>
  );
}
