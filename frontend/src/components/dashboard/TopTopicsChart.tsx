'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Search } from '@carbon/icons-react';
import type { TopicEntry } from '@/types/dashboard';

interface TopTopicsChartProps {
  topics: TopicEntry[];
  loading?: boolean;
}

const COLORS = [
  'rgba(15, 98, 254, 0.85)',
  'rgba(138, 63, 252, 0.85)',
  'rgba(36, 161, 72, 0.85)',
  'rgba(235, 98, 0, 0.85)',
  'rgba(0, 157, 154, 0.85)',
];

export default function TopTopicsChart({ topics, loading }: TopTopicsChartProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm h-full">
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">🔥</span>
          <h3 className="text-lg font-semibold text-gray-900">熱門主題排行</h3>
          <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
            Top 5
          </span>
        </div>
        <div className="h-[280px] flex items-center justify-center">
          <div className="animate-pulse text-gray-400">Loading...</div>
        </div>
      </div>
    );
  }

  if (!topics || topics.length === 0) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm h-full">
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">🔥</span>
          <h3 className="text-lg font-semibold text-gray-900">熱門主題排行</h3>
          <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
            Top 5
          </span>
        </div>
        <div className="h-[280px] flex flex-col items-center justify-center text-gray-400">
          <Search size={48} className="mb-4 opacity-50" />
          <p className="font-medium mb-1">尚無搜尋記錄</p>
          <p className="text-sm">您的熱門搜尋主題將顯示在這裡</p>
        </div>
      </div>
    );
  }

  // Format data for chart - truncate long text
  const chartData = topics.slice(0, 5).map((topic) => ({
    name: topic.query_text.length > 15 
      ? topic.query_text.slice(0, 15) + '...' 
      : topic.query_text,
    fullName: topic.query_text,
    count: topic.count,
  }));

  return (
    <div className="bg-white rounded-xl p-6 shadow-sm h-full">
      <div className="flex items-center gap-2 mb-6">
        <span className="text-lg">🔥</span>
        <h3 className="text-lg font-semibold text-gray-900">熱門主題排行</h3>
        <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
          Top {chartData.length}
        </span>
      </div>
      <div className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 12, fill: '#6b7280' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fontSize: 12, fill: '#374151' }}
              axisLine={false}
              tickLine={false}
              width={100}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              }}
              formatter={(value: number, name: string, props: any) => [
                `${value} 次`,
                props.payload.fullName,
              ]}
              labelFormatter={() => '查詢次數'}
            />
            <Bar dataKey="count" radius={[0, 8, 8, 0]} barSize={28}>
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
