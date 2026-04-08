'use client';

import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts';

interface QueryTrendChartProps {
  data?: { date: string; count: number }[];
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
    data.push({
      date: `${date.getMonth() + 1}/${date.getDate()}`,
      count: Math.floor(Math.random() * 5) + 1,
    });
  }
  return data;
};

export default function QueryTrendChart({ data, loading, error, onRetry }: QueryTrendChartProps) {
  const chartData = data && data.length > 0 ? data : generateMockData();

  if (loading) {
    return (
      <div className="h-[180px] sm:h-[220px] flex items-center justify-center">
        <div className="animate-pulse" style={{ color: 'var(--text-muted)' }}>載入中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-[180px] sm:h-[220px] flex flex-col items-center justify-center gap-2">
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
    <div className="h-[180px] sm:h-[220px]" style={{ width: '100%', minWidth: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="colorCountAnthro" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#c96442" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#c96442" stopOpacity={0} />
            </linearGradient>
          </defs>
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
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#141413',
              border: 'none',
              borderRadius: '8px',
              color: '#b0aea5',
              boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
            }}
            formatter={(value: number) => [`${value} 次`, '查詢次數']}
          />
          <Area
            type="monotone"
            dataKey="count"
            stroke="#c96442"
            strokeWidth={2}
            fill="url(#colorCountAnthro)"
            dot={{ fill: '#c96442', strokeWidth: 2, stroke: '#faf9f5', r: 4 }}
            activeDot={{ r: 6, fill: '#c96442', stroke: '#faf9f5', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
