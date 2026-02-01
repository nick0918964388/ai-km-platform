'use client';

import React from 'react';
import { Tile, SkeletonText } from '@carbon/react';
import { ArrowUp, ArrowDown, Subtract } from '@carbon/icons-react';

interface StatCardProps {
  title: string;
  value: number | string;
  unit?: string;
  trend?: number; // Percentage change
  trendLabel?: string;
  icon?: React.ReactNode;
  color?: 'default' | 'success' | 'warning' | 'danger';
  isLoading?: boolean;
  onClick?: () => void;
}

const colorClasses = {
  default: 'text-blue-600',
  success: 'text-green-600',
  warning: 'text-yellow-600',
  danger: 'text-red-600',
};

const bgClasses = {
  default: 'bg-blue-50',
  success: 'bg-green-50',
  warning: 'bg-yellow-50',
  danger: 'bg-red-50',
};

export default function StatCard({
  title,
  value,
  unit,
  trend,
  trendLabel,
  icon,
  color = 'default',
  isLoading = false,
  onClick,
}: StatCardProps) {
  if (isLoading) {
    return (
      <Tile className="p-4">
        <SkeletonText heading width="60%" />
        <SkeletonText width="40%" />
      </Tile>
    );
  }

  const TrendIcon = trend && trend > 0 ? ArrowUp : trend && trend < 0 ? ArrowDown : Subtract;
  const trendColor = trend && trend > 0 ? 'text-red-500' : trend && trend < 0 ? 'text-green-500' : 'text-gray-500';

  return (
    <Tile
      className={`p-4 ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 mb-1">{title}</p>
          <div className="flex items-baseline gap-1">
            <span className={`text-2xl font-bold ${colorClasses[color]}`}>
              {typeof value === 'number' ? value.toLocaleString() : value}
            </span>
            {unit && <span className="text-sm text-gray-500">{unit}</span>}
          </div>
          {trend !== undefined && (
            <div className={`flex items-center gap-1 mt-1 text-sm ${trendColor}`}>
              <TrendIcon size={12} />
              <span>{Math.abs(trend)}%</span>
              {trendLabel && <span className="text-gray-400">{trendLabel}</span>}
            </div>
          )}
        </div>
        {icon && (
          <div className={`p-2 rounded-lg ${bgClasses[color]}`}>
            {icon}
          </div>
        )}
      </div>
    </Tile>
  );
}
