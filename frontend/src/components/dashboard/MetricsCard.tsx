'use client';

import { Tile, SkeletonText } from '@carbon/react';
import type { CarbonIconType } from '@carbon/icons-react';

interface MetricsCardProps {
  /** Card title */
  title: string;
  /** Metric value to display */
  value: string | number;
  /** Optional Carbon icon component */
  icon?: CarbonIconType;
  /** Icon color (default: text-blue-600) */
  iconColor?: string;
  /** Loading state */
  loading?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * MetricsCard Component
 * Displays a single metric with icon, title, and value using Carbon Tile
 *
 * Features:
 * - Carbon Tile for consistent styling
 * - Optional icon with customizable color
 * - Loading skeleton state
 * - Responsive typography
 */
export default function MetricsCard({
  title,
  value,
  icon: Icon,
  iconColor = 'text-blue-600',
  loading = false,
  className = '',
}: MetricsCardProps) {
  if (loading) {
    return (
      <Tile className={`p-6 ${className}`}>
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0">
            <div className="w-10 h-10 bg-gray-200 rounded animate-pulse" />
          </div>
          <div className="flex-1">
            <SkeletonText heading className="mb-2" />
            <SkeletonText width="60%" />
          </div>
        </div>
      </Tile>
    );
  }

  return (
    <Tile className={`p-6 hover:shadow-md transition-shadow ${className}`}>
      <div className="flex items-start gap-4">
        {/* Icon */}
        {Icon && (
          <div className="flex-shrink-0">
            <Icon size={40} className={iconColor} />
          </div>
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium text-gray-600 mb-1">{title}</h3>
          <p className="text-3xl font-semibold text-gray-900 truncate">
            {value}
          </p>
        </div>
      </div>
    </Tile>
  );
}
