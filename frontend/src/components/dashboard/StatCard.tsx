'use client';

import React from 'react';
import { Tile, SkeletonText } from '@carbon/react';
import { ArrowUp, ArrowDown, Subtract } from '@carbon/icons-react';

interface StatCardProps {
  title: string;
  value: number | string;
  unit?: string;
  trend?: number;
  trendLabel?: string;
  icon?: React.ReactNode;
  color?: 'default' | 'success' | 'warning' | 'danger';
  isLoading?: boolean;
  onClick?: () => void;
}

const iconBgStyles = {
  default: { background: '#f9ede8' },
  success: { background: 'var(--success-light)' },
  warning: { background: 'var(--warning-light)' },
  danger: { background: 'var(--error-light)' },
};

const valueStyles = {
  default: { color: '#c96442' },
  success: { color: 'var(--success)' },
  warning: { color: 'var(--warning)' },
  danger: { color: 'var(--error)' },
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
  const trendStyle = trend && trend > 0 ? { color: 'var(--error)' } : trend && trend < 0 ? { color: 'var(--success)' } : { color: 'var(--text-muted)' };

  return (
    <Tile
      className={`p-4 ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>{title}</p>
          <div className="flex items-baseline gap-1">
            <span style={{ fontSize: '1.5rem', fontWeight: 700, ...valueStyles[color] }}>
              {typeof value === 'number' ? value.toLocaleString() : value}
            </span>
            {unit && <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>{unit}</span>}
          </div>
          {trend !== undefined && (
            <div className="flex items-center gap-1 mt-1" style={{ fontSize: '0.875rem', ...trendStyle }}>
              <TrendIcon size={12} />
              <span>{Math.abs(trend)}%</span>
              {trendLabel && <span style={{ color: 'var(--text-muted)' }}>{trendLabel}</span>}
            </div>
          )}
        </div>
        {icon && (
          <div style={{ padding: '0.5rem', borderRadius: '8px', ...iconBgStyles[color] }}>
            {icon}
          </div>
        )}
      </div>
    </Tile>
  );
}
