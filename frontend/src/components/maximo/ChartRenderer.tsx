'use client';
import { useState } from 'react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export const CHART_COLORS = ['#0f62fe', '#42be65', '#f1c21b', '#da1e28', '#a56eff', '#ff832b', '#08bdba', '#ba4e00'];

export interface ChartSuggestion {
  type?: 'bar' | 'line' | 'pie';
  x_key?: string;
  y_key?: string;
  name_key?: string;
  value_key?: string;
  title?: string;
}

interface ChartRendererProps {
  data: Record<string, unknown>[];
  columns: string[];
  chartSuggestion?: ChartSuggestion | null;
  /** If true, show table/chart toggle + chart type selector. Default true. */
  showControls?: boolean;
  /** Height of chart area. Default 300. */
  height?: number;
  /** External view mode control */
  viewMode?: 'table' | 'chart';
  /** Callback when view mode changes */
  onViewModeChange?: (mode: 'table' | 'chart') => void;
  /** External chart type control */
  chartType?: 'bar' | 'line' | 'pie';
  /** Callback when chart type changes */
  onChartTypeChange?: (type: 'bar' | 'line' | 'pie') => void;
}

export default function ChartRenderer({
  data,
  columns,
  chartSuggestion,
  showControls = true,
  height = 300,
  viewMode: externalViewMode,
  onViewModeChange,
  chartType: externalChartType,
  onChartTypeChange,
}: ChartRendererProps) {
  const [internalViewMode, setInternalViewMode] = useState<'table' | 'chart'>(chartSuggestion ? 'chart' : 'table');
  const [internalChartType, setInternalChartType] = useState<'bar' | 'line' | 'pie'>(chartSuggestion?.type || 'bar');

  const viewMode = externalViewMode ?? internalViewMode;
  const chartType = externalChartType ?? internalChartType;

  const setViewMode = (mode: 'table' | 'chart') => {
    setInternalViewMode(mode);
    onViewModeChange?.(mode);
  };

  const setChartType = (type: 'bar' | 'line' | 'pie') => {
    setInternalChartType(type);
    onChartTypeChange?.(type);
  };

  const xKey = chartSuggestion?.x_key || chartSuggestion?.name_key || columns[0] || 'x';
  const yKey = chartSuggestion?.y_key || chartSuggestion?.value_key || columns[1] || 'y';

  const renderChart = () => {
    if (chartType === 'bar') {
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={xKey} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Bar dataKey={yKey} fill="#0f62fe" radius={[4, 4, 0, 0]} />
        </BarChart>
      );
    }

    if (chartType === 'line') {
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={xKey} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Line type="monotone" dataKey={yKey} stroke="#0f62fe" strokeWidth={2} dot={{ fill: '#0f62fe' }} />
        </LineChart>
      );
    }

    if (chartType === 'pie') {
      return (
        <PieChart>
          <Pie data={data} dataKey={yKey} nameKey={xKey} cx="50%" cy="50%" outerRadius={100} label={({ name, percent }: { name: string; percent: number }) => `${name} ${(percent * 100).toFixed(0)}%`}>
            {data.map((_: any, i: number) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
          </Pie>
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Legend />
        </PieChart>
      );
    }

    return <div>不支援的圖表類型</div>;
  };

  if (!showControls) {
    return (
      <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 8, padding: '1rem' }}>
        {chartSuggestion?.title && <div style={{ fontSize: '0.8125rem', fontWeight: 600, textAlign: 'center', marginBottom: '0.5rem', color: 'var(--text-primary)' }}>{chartSuggestion.title}</div>}
        <ResponsiveContainer width="100%" height={height}>{renderChart()}</ResponsiveContainer>
      </div>
    );
  }

  return (
    <>
      <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8125rem', alignItems: 'center' }}>
        <button
          onClick={() => setViewMode('table')}
          style={{
            padding: '0.25rem 0.75rem', borderRadius: 99,
            border: `1px solid ${viewMode === 'table' ? 'var(--primary)' : 'var(--border)'}`,
            background: viewMode === 'table' ? 'var(--primary)' : 'transparent',
            color: viewMode === 'table' ? 'white' : 'var(--text-muted)',
            cursor: 'pointer', fontWeight: 500,
          }}
        >
          表格
        </button>
        <button
          onClick={() => setViewMode('chart')}
          style={{
            padding: '0.25rem 0.75rem', borderRadius: 99,
            border: `1px solid ${viewMode === 'chart' ? 'var(--accent)' : 'var(--border)'}`,
            background: viewMode === 'chart' ? 'var(--accent)' : 'transparent',
            color: viewMode === 'chart' ? 'white' : 'var(--text-muted)',
            cursor: 'pointer', fontWeight: 500,
          }}
        >
          圖表
        </button>
        {viewMode === 'chart' && (
          <>
            <span style={{ color: 'var(--border)', margin: '0 0.25rem' }}>|</span>
            {(['bar', 'line', 'pie'] as const).map(t => (
              <button
                key={t}
                onClick={() => setChartType(t)}
                style={{
                  padding: '0.2rem 0.5rem', borderRadius: 4,
                  border: `1px solid ${chartType === t ? 'var(--accent)' : 'var(--border)'}`,
                  background: chartType === t ? 'rgba(80,144,211,0.15)' : 'transparent',
                  color: chartType === t ? 'var(--accent)' : 'var(--text-muted)',
                  cursor: 'pointer', fontSize: '0.75rem',
                }}
              >
                {t === 'bar' ? '長條圖' : t === 'line' ? '折線圖' : '圓餅圖'}
              </button>
            ))}
          </>
        )}
      </div>

      {viewMode === 'chart' && (
        <div style={{
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)', padding: '1.25rem',
        }}>
          {chartSuggestion?.title && (
            <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.75rem', textAlign: 'center' }}>
              {chartSuggestion.title}
            </div>
          )}
          <ResponsiveContainer width="100%" height={height}>{renderChart()}</ResponsiveContainer>
        </div>
      )}
    </>
  );
}
