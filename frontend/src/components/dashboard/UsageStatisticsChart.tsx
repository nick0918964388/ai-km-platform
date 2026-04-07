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
        <div className="animate-pulse text-gray-400">載入中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-[250px] flex flex-col items-center justify-center gap-2">
        <p className="text-red-600">{error}</p>
        {onRetry && (
          <button onClick={onRetry} className="text-blue-600 hover:underline">
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
            formatter={(value: number) => [`${value} 個`, '上傳檔案']}
            cursor={{ fill: 'rgba(59, 130, 246, 0.1)' }}
          />
          <Bar dataKey="uploads" radius={[6, 6, 0, 0]} maxBarSize={50}>
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.uploads === maxUploads ? '#3b82f6' : '#e5e7eb'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
