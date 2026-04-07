'use client';

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
  /** Icon background color (default: bg-blue-100) */
  iconBgColor?: string;
  /** Loading state */
  loading?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * MetricsCard Component
 * Displays a single metric with icon, title, and value
 *
 * Features:
 * - Clean white card with shadow
 * - Icon with colored background
 * - Loading skeleton state
 * - Hover effect
 */
export default function MetricsCard({
  title,
  value,
  icon: Icon,
  iconColor = 'text-blue-600',
  iconBgColor = 'bg-blue-100',
  loading = false,
  className = '',
}: MetricsCardProps) {
  if (loading) {
    return (
      <div
        className={`bg-white rounded-xl p-6 shadow-sm hover:shadow-md transition-all ${className}`}
      >
        <div className="w-12 h-12 bg-gray-200 rounded-xl animate-pulse mb-4" />
        <div className="h-3 w-20 bg-gray-200 rounded animate-pulse mb-2" />
        <div className="h-8 w-16 bg-gray-200 rounded animate-pulse" />
      </div>
    );
  }

  return (
    <div
      className={`bg-white rounded-2xl p-6 shadow-lg border border-gray-200 hover:shadow-xl hover:-translate-y-1 transition-all duration-200 ${className}`}
      style={{ boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)' }}
    >
      {/* Icon */}
      {Icon && (
        <div
          className={`w-14 h-14 ${iconBgColor} rounded-2xl flex items-center justify-center mb-4`}
        >
          <Icon size={28} className={iconColor} />
        </div>
      )}

      {/* Content */}
      <p className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">{title}</p>
      <p className="text-3xl font-bold text-gray-900 truncate">
        {value}
      </p>
    </div>
  );
}
