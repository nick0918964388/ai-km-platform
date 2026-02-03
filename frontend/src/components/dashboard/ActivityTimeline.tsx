'use client';

import { Tile, SkeletonText } from '@carbon/react';
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
      return DocumentAdd;
    case 'query':
      return Search;
    case 'profile_update':
      return UserAvatar;
    default:
      return Renew;
  }
}

/**
 * Get human-readable label for activity type
 */
function getActivityLabel(actionType: string): string {
  switch (actionType) {
    case 'document_upload':
      return 'Document Uploaded';
    case 'query':
      return 'Query Performed';
    case 'profile_update':
      return 'Profile Updated';
    default:
      return 'Activity';
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

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-US', {
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
 *
 * Features:
 * - Timeline layout with icons
 * - Relative timestamps (e.g., "2h ago")
 * - Action type icons and labels
 * - Empty state for new users
 * - Loading skeleton state
 */
export default function ActivityTimeline({
  activities,
  loading = false,
  className = '',
}: ActivityTimelineProps) {
  // Loading skeleton
  if (loading) {
    return (
      <Tile className={`p-6 ${className}`}>
        <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="w-8 h-8 bg-gray-200 rounded-full animate-pulse flex-shrink-0" />
              <div className="flex-1">
                <SkeletonText width="80%" />
                <SkeletonText width="40%" />
              </div>
            </div>
          ))}
        </div>
      </Tile>
    );
  }

  // Empty state
  if (!activities || activities.length === 0) {
    return (
      <Tile className={`p-6 ${className}`}>
        <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
        <div className="text-center py-8">
          <Renew size={48} className="mx-auto text-gray-400 mb-4" />
          <p className="text-gray-600 font-medium mb-2">No Activity Yet</p>
          <p className="text-sm text-gray-500">
            Your recent actions will appear here once you start using the platform
          </p>
        </div>
      </Tile>
    );
  }

  return (
    <Tile className={`p-6 ${className}`}>
      <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>

      {/* Timeline */}
      <div className="space-y-4">
        {activities.map((activity, index) => {
          const Icon = getActivityIcon(activity.action_type);
          const label = getActivityLabel(activity.action_type);
          const timestamp = formatTimestamp(activity.timestamp);

          return (
            <div key={index} className="flex items-start gap-3">
              {/* Icon */}
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                <Icon size={16} className="text-blue-600" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900">{label}</p>
                <p className="text-xs text-gray-500">{timestamp}</p>
                {activity.metadata && Object.keys(activity.metadata).length > 0 && (
                  <p className="text-xs text-gray-600 mt-1 truncate">
                    {JSON.stringify(activity.metadata)}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Tile>
  );
}
