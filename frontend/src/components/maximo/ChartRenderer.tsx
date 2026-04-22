'use client';
import { useState } from 'react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export const CHART_COLORS = ['#0f62fe', '#42be65', '#f1c21b', '#da1e28', '#a56eff', '#ff832b', '#08bdba', '#ba4e00'];

export interface ChartSuggestion {
  type?: 'bar' | 'line' | 'pie' | 'none';
  x_key?: string;
  y_key?: string;
  name_key?: string;
  value_key?: string;
  title?: string;
  warning?: string;
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
  const hasValidChart = chartSuggestion && chartSuggestion.type !== 'none';
  const [internalViewMode, setInternalViewMode] = useState<'table' | 'chart'>(hasValidChart ? 'chart' : 'table');
  const [internalChartType, setInternalChartType] = useState<'bar' | 'line' | 'pie'>(
    (hasValidChart && chartSuggestion.type) ? (chartSuggestion.type as 'bar' | 'line' | 'pie') : 'bar'
  );

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
    if (chartSuggestion?.type === 'none') {
      return (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          padding: '0.75rem 1rem', borderRadius: 6,
          background: 'rgba(15,98,254,0.07)', border: '1px solid rgba(15,98,254,0.25)',
          fontSize: '0.8125rem', color: 'var(--text-secondary)',
        }}>
          <span style={{ color: '#0f62fe', flexShrink: 0 }}>ℹ</span>
          <span><strong>資料不適合圖表呈現</strong>{chartSuggestion.warning ? `：${chartSuggestion.warning}` : ''}</span>
        </div>
      );
    }

    if (chartType === 'bar') {
      return (
        <BarChart data={data} margin={{ top: 5, right: 5, left: -10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={xKey} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} interval={0} angle={-30} textAnchor="end" height={50} />
          <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} width={40} />
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Bar dataKey={yKey} fill="#0f62fe" radius={[4, 4, 0, 0]} />
        </BarChart>
      );
    }

    if (chartType === 'line') {
      return (
        <LineChart data={data} margin={{ top: 5, right: 5, left: -10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={xKey} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} interval={0} angle={-30} textAnchor="end" height={50} />
          <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} width={40} />
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Line type="monotone" dataKey={yKey} stroke="#0f62fe" strokeWidth={2} dot={{ fill: '#0f62fe' }} />
        </LineChart>
      );
    }

    if (chartType === 'pie') {
      return (
        <PieChart>
          <Pie data={data} dataKey={yKey} nameKey={xKey} cx="50%" cy="45%" outerRadius={70} label={({ name, value }: { name: string; value: number }) => `${String(name).slice(0, 8)}: ${value}`} labelLine={true} fontSize={10}>
            {data.map((_: any, i: number) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
          </Pie>
          <Tooltip contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }} />
          <Legend verticalAlign="bottom" height={36} />
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
      <div style={{ display: 'flex', gap: '0.375rem', fontSize: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
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
