'use client';

import {
  LineChart,
  Line,
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

// Generate mock data for the last 7 days if no data provided
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
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">📈</span>
          <h3 className="text-lg font-semibold text-gray-900">查詢趨勢</h3>
          <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
            近 7 天
          </span>
        </div>
        <div className="h-[220px] flex items-center justify-center">
          <div className="animate-pulse text-gray-400">Loading...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">📈</span>
          <h3 className="text-lg font-semibold text-gray-900">查詢趨勢</h3>
          <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
            近 7 天
          </span>
        </div>
        <div className="h-[220px] flex flex-col items-center justify-center gap-2">
          <p className="text-red-600">{error}</p>
          {onRetry && (
            <button onClick={onRetry} className="text-blue-600 hover:underline">
              重試
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl p-6 shadow-sm">
      <div className="flex items-center gap-2 mb-6">
        <span className="text-lg">📈</span>
        <h3 className="text-lg font-semibold text-gray-900">查詢趨勢</h3>
        <span className="bg-blue-100 text-blue-600 text-xs px-2 py-1 rounded-full font-medium">
          近 7 天
        </span>
      </div>
      <div className="h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#0f62fe" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#0f62fe" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#6b7280' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#6b7280' }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              }}
              formatter={(value: number) => [`${value} 次`, '查詢次數']}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#0f62fe"
              strokeWidth={2}
              fill="url(#colorCount)"
              dot={{ fill: '#0f62fe', strokeWidth: 2, stroke: '#fff', r: 4 }}
              activeDot={{ r: 6, fill: '#0f62fe', stroke: '#fff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
