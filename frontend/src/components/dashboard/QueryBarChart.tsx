'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface QueryBarChartProps {
  data?: { date: string; count: number }[];
  loading?: boolean;
}

const generateMockData = () => {
  const days = ['週一', '週二', '週三', '週四', '週五', '週六', '週日'];
  return days.map((day, i) => ({
    date: day,
    count: Math.floor(Math.random() * 800) + 200,
  }));
};

export default function QueryBarChart({ data, loading }: QueryBarChartProps) {
  const chartData = data && data.length > 0 
    ? data.map((d, i) => ({ ...d, date: ['週一', '週二', '週三', '週四', '週五', '週六', '週日'][i] || d.date }))
    : generateMockData();

  // Find the max value to highlight
  const maxCount = Math.max(...chartData.map(d => d.count));

  if (loading) {
    return (
      <div className="h-[250px] flex items-center justify-center">
        <div className="animate-pulse text-gray-400">載入中...</div>
      </div>
    );
  }

  return (
    <div className="h-[250px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} barCategoryGap="20%">
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: '#9ca3af' }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: 'none',
              borderRadius: '8px',
              color: '#fff',
              padding: '8px 12px',
            }}
            formatter={(value: number) => [`${value} 次`, '查詢']}
            cursor={{ fill: 'rgba(59, 130, 246, 0.1)' }}
          />
          <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={50}>
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.count === maxCount ? '#3b82f6' : '#e5e7eb'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
