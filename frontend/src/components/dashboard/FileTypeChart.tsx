'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface FileTypeChartProps {
  data?: { name: string; value: number }[];
  loading?: boolean;
}

const COLORS = ['#0f62fe', '#8a3ffc', '#24a148', '#eb6200', '#009d9a'];

// Mock data if no data provided
const defaultData = [
  { name: 'PDF', value: 2 },
  { name: 'Word', value: 1 },
  { name: 'Excel', value: 0 },
];

export default function FileTypeChart({ data, loading }: FileTypeChartProps) {
  const chartData = data && data.length > 0 ? data : defaultData;
  const filteredData = chartData.filter((item) => item.value > 0);

  if (loading) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">📁</span>
          <h3 className="text-lg font-semibold text-gray-900">文件類型分佈</h3>
        </div>
        <div className="h-[220px] flex items-center justify-center">
          <div className="animate-pulse text-gray-400">Loading...</div>
        </div>
      </div>
    );
  }

  if (filteredData.length === 0) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <span className="text-lg">📁</span>
          <h3 className="text-lg font-semibold text-gray-900">文件類型分佈</h3>
        </div>
        <div className="h-[220px] flex items-center justify-center text-gray-400">
          暫無文件資料
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl p-6 shadow-sm">
      <div className="flex items-center gap-2 mb-6">
        <span className="text-lg">📁</span>
        <h3 className="text-lg font-semibold text-gray-900">文件類型分佈</h3>
      </div>
      <div className="h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={filteredData}
              cx="50%"
              cy="45%"
              innerRadius={50}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
            >
              {filteredData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              }}
              formatter={(value: number) => [`${value} 個`, '文件數量']}
            />
            <Legend
              verticalAlign="bottom"
              height={36}
              iconType="circle"
              formatter={(value) => <span className="text-sm text-gray-600">{value}</span>}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
