'use client';

import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface FileTypePieChartProps {
  data?: { name: string; value: number }[];
  loading?: boolean;
}

const COLORS = ['#c96442', '#d97757', '#87867f', '#4d4c48'];

const defaultData = [
  { name: 'PDF', value: 40, color: '#c96442' },
  { name: 'Word', value: 25, color: '#d97757' },
  { name: 'PPT', value: 20, color: '#87867f' },
  { name: '其他', value: 15, color: '#4d4c48' },
];

export default function FileTypePieChart({ data, loading }: FileTypePieChartProps) {
  const chartData = data && data.length > 0 
    ? data.map((d, i) => ({ ...d, color: COLORS[i % COLORS.length] }))
    : defaultData;

  const total = chartData.reduce((sum, d) => sum + d.value, 0);

  if (loading) {
    return (
      <div className="h-[220px] flex items-center justify-center">
        <div className="animate-pulse" style={{ color: 'var(--text-muted)' }}>載入中...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6" style={{ minWidth: 0 }}>
      {/* Chart */}
      <div className="w-[140px] h-[140px] relative flex-shrink-0 mx-auto sm:mx-0">
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
              <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>{item.name}</span>
              <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>{percentage}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
