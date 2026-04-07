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
        <div className="animate-pulse" style={{ color: 'var(--text-muted)' }}>載入中...</div>
      </div>
    );
  }

  return (
    <div className="h-[250px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} barCategoryGap="20%">
          <CartesianGrid strokeDasharray="3 3" stroke="#e8e6dc" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: '#87867f' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: '#87867f' }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#141413',
              border: 'none',
              borderRadius: '8px',
              color: '#b0aea5',
              padding: '8px 12px',
            }}
            formatter={(value: number) => [`${value} 次`, '查詢']}
            cursor={{ fill: 'rgba(201, 100, 66, 0.08)' }}
          />
          <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={50}>
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.count === maxCount ? '#c96442' : '#e8e6dc'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
