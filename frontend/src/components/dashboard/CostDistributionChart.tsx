'use client';

import React from 'react';
import { Tile, SkeletonText } from '@carbon/react';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface CostData {
  cost_type: string;
  amount: number;
  percentage: number;
}

interface CostDistributionChartProps {
  title: string;
  data: CostData[];
  isLoading?: boolean;
  height?: number;
}

const COLORS = ['#0f62fe', '#8a3ffc', '#ff7eb6', '#42be65', '#f1c21b', '#fa4d56'];

const COST_TYPE_LABELS: Record<string, string> = {
  labor: '人工',
  parts: '零件',
  external: '外包',
  other: '其他',
};

export default function CostDistributionChart({
  title,
  data,
  isLoading = false,
  height = 300,
}: CostDistributionChartProps) {
  if (isLoading) {
    return (
      <Tile className="p-4">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <SkeletonText paragraph lineCount={6} />
      </Tile>
    );
  }

  const chartData = data.map((item) => ({
    ...item,
    name: COST_TYPE_LABELS[item.cost_type] || item.cost_type,
  }));

  const total = data.reduce((sum, item) => sum + item.amount, 0);

  return (
    <Tile className="p-4">
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      {chartData.length === 0 ? (
        <p className="text-gray-500 text-center py-8">暫無資料</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={height}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="amount"
                label={({ name, percentage }) => `${name} ${percentage}%`}
                labelLine={false}
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => `NT$ ${value.toLocaleString()}`}
                contentStyle={{
                  backgroundColor: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: '4px',
                }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-4 text-center">
            <p className="text-sm text-gray-500">總計</p>
            <p className="text-xl font-bold text-blue-600">
              NT$ {total.toLocaleString()}
            </p>
          </div>
        </>
      )}
    </Tile>
  );
}
