'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface UsageStatisticsChartProps {
  data?: { date: string; uploads: number }[];
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
}

const generateMockData = () => {
  const data = [];
  const today = new Date();
  for (let i = 6; i >= 0; i--) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);
    const isWeekend = date.getDay() === 0 || date.getDay() === 6;
    data.push({
      date: `${date.getMonth() + 1}/${date.getDate()}`,
      uploads: Math.floor(Math.random() * (isWeekend ? 5 : 20)) + (isWeekend ? 1 : 10),
    });
  }
  return data;
};

export default function UsageStatisticsChart({ data, loading, error, onRetry }: UsageStatisticsChartProps) {
  const chartData = data && data.length > 0 ? data : generateMockData();
  const maxUploads = Math.max(...chartData.map(d => d.uploads));

  if (loading) {
    return (
      <div className="h-[250px] flex items-center justify-center">
        <div className="animate-pulse" style={{ color: 'var(--text-muted)' }}>載入中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-[250px] flex flex-col items-center justify-center gap-2">
        <p style={{ color: 'var(--error)' }}>{error}</p>
        {onRetry && (
          <button onClick={onRetry} style={{ color: 'var(--primary)' }} className="hover:underline">
            重試
          </button>
        )}
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
            formatter={(value: number) => [`${value} 個`, '上傳檔案']}
            cursor={{ fill: 'rgba(201, 100, 66, 0.08)' }}
          />
          <Bar dataKey="uploads" radius={[6, 6, 0, 0]} maxBarSize={50}>
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.uploads === maxUploads ? '#c96442' : '#e8e6dc'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
