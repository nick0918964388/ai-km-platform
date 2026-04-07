'use client';

import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface FileTypePieChartProps {
  data?: { name: string; value: number }[];
  loading?: boolean;
}

const COLORS = ['#3b82f6', '#8b5cf6', '#f59e0b', '#10b981'];

const defaultData = [
  { name: 'PDF', value: 40, color: '#3b82f6' },
  { name: 'Word', value: 25, color: '#8b5cf6' },
  { name: 'PPT', value: 20, color: '#f59e0b' },
  { name: '其他', value: 15, color: '#10b981' },
];

export default function FileTypePieChart({ data, loading }: FileTypePieChartProps) {
  const chartData = data && data.length > 0 
    ? data.map((d, i) => ({ ...d, color: COLORS[i % COLORS.length] }))
    : defaultData;

  const total = chartData.reduce((sum, d) => sum + d.value, 0);

  if (loading) {
    return (
      <div className="h-[220px] flex items-center justify-center">
        <div className="animate-pulse text-gray-400">載入中...</div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-6">
      {/* Chart */}
      <div className="w-[140px] h-[140px] relative">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={45}
              outerRadius={65}
              paddingAngle={2}
              dataKey="value"
              strokeWidth={0}
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color || COLORS[index % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-col gap-3">
        {chartData.map((item, index) => {
          const percentage = total > 0 ? Math.round((item.value / total) * 100) : 0;
          return (
            <div key={index} className="flex items-center gap-3">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: item.color || COLORS[index % COLORS.length] }}
              />
              <span className="text-sm text-gray-600">{item.name}</span>
              <span className="text-sm font-semibold text-gray-900">{percentage}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
