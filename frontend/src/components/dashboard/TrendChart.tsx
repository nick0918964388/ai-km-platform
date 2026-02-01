'use client';

import React from 'react';
import { Tile, SkeletonText } from '@carbon/react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface TrendData {
  date: string;
  [key: string]: string | number;
}

interface TrendChartProps {
  title: string;
  data: TrendData[];
  lines: {
    key: string;
    name: string;
    color: string;
  }[];
  isLoading?: boolean;
  height?: number;
}

// Transform raw data to chart format (group by date)
function transformData(rawData: any[]): TrendData[] {
  const grouped: Record<string, Record<string, number>> = {};
  
  rawData.forEach(item => {
    const date = item.date;
    if (!date) return;
    
    if (!grouped[date]) {
      grouped[date] = {};
    }
    grouped[date][item.fault_type] = (grouped[date][item.fault_type] || 0) + item.count;
  });
  
  return Object.entries(grouped)
    .map(([date, types]) => ({
      date,
      ...types,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export default function TrendChart({
  title,
  data,
  lines,
  isLoading = false,
  height = 300,
}: TrendChartProps) {
  if (isLoading) {
    return (
      <Tile className="p-4">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <SkeletonText paragraph lineCount={6} />
      </Tile>
    );
  }

  const chartData = transformData(data);

  return (
    <Tile className="p-4">
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      {chartData.length === 0 ? (
        <p className="text-gray-500 text-center py-8">暫無資料</p>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => value.slice(5)} // Show MM-DD only
            />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '4px',
              }}
            />
            <Legend />
            {lines.map((line) => (
              <Line
                key={line.key}
                type="monotone"
                dataKey={line.key}
                name={line.name}
                stroke={line.color}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </Tile>
  );
}
