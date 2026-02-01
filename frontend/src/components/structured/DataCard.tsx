'use client';

import React from 'react';
import {
  Tile,
  Tag,
  Button,
  SkeletonText,
} from '@carbon/react';
import {
  ChevronDown,
  ChevronUp,
  DataTable as DataTableIcon,
  Download,
} from '@carbon/icons-react';

interface DataCardProps {
  title: string;
  subtitle?: string;
  data: Record<string, any>[];
  columns: string[];
  isLoading?: boolean;
  error?: string;
  onExport?: () => void;
  maxPreviewRows?: number;
}

// Column display name mapping
const COLUMN_LABELS: Record<string, string> = {
  id: 'ID',
  vehicle_code: '車輛編號',
  vehicle_type: '車型',
  fault_code: '故障編號',
  fault_date: '故障日期',
  fault_type: '故障類型',
  severity: '嚴重程度',
  status: '狀態',
  description: '描述',
  resolution: '處理方式',
  resolved_at: '解決時間',
  reported_by: '回報人',
  maintenance_code: '檢修編號',
  maintenance_type: '檢修類型',
  maintenance_date: '檢修日期',
  completed_date: '完成日期',
  technician: '技師',
  supervisor: '督導',
  labor_hours: '工時',
  labor_cost: '人工費用',
  amount: '金額',
  cost_type: '成本類型',
  category: '分類',
  record_date: '記錄日期',
  open_faults: '未處理故障',
};

// Severity tag colors
const SEVERITY_COLORS: Record<string, 'red' | 'orange' | 'blue' | 'gray'> = {
  critical: 'red',
  major: 'orange',
  minor: 'blue',
};

// Status tag colors
const STATUS_COLORS: Record<string, 'green' | 'blue' | 'gray' | 'red'> = {
  active: 'green',
  maintenance: 'blue',
  retired: 'gray',
  open: 'red',
  in_progress: 'blue',
  resolved: 'green',
  completed: 'green',
  pending: 'gray',
};

const getColumnLabel = (col: string): string => {
  return COLUMN_LABELS[col] || col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
};

const formatValue = (value: any, column: string): React.ReactNode => {
  if (value === null || value === undefined) return '-';
  
  // Date formatting
  if (column.includes('date') || column.includes('_at')) {
    if (typeof value === 'string') {
      const date = new Date(value);
      if (!isNaN(date.getTime())) {
        return date.toLocaleString('zh-TW', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        });
      }
    }
    return value;
  }
  
  // Severity as tag
  if (column === 'severity') {
    const color = SEVERITY_COLORS[value] || 'gray';
    const labels: Record<string, string> = {
      critical: '嚴重',
      major: '主要',
      minor: '次要',
    };
    return <Tag type={color} size="sm">{labels[value] || value}</Tag>;
  }
  
  // Status as tag
  if (column === 'status') {
    const color = STATUS_COLORS[value] || 'gray';
    const labels: Record<string, string> = {
      active: '運行中',
      maintenance: '維修中',
      retired: '已退役',
      open: '待處理',
      in_progress: '處理中',
      resolved: '已解決',
      completed: '已完成',
      pending: '待排程',
    };
    return <Tag type={color} size="sm">{labels[value] || value}</Tag>;
  }
  
  // Cost/amount formatting
  if (column === 'amount' || column === 'labor_cost' || column.includes('cost')) {
    return `NT$ ${Number(value).toLocaleString('zh-TW')}`;
  }
  
  // Hours formatting
  if (column === 'labor_hours') {
    return `${value} 小時`;
  }
  
  return String(value);
};

export default function DataCard({
  title,
  subtitle,
  data,
  columns,
  isLoading = false,
  error,
  onExport,
  maxPreviewRows = 5,
}: DataCardProps) {
  const [expanded, setExpanded] = React.useState(false);
  
  // Filter out ID columns for display
  const displayColumns = columns.filter(col => col !== 'id');
  const previewData = expanded ? data : data.slice(0, maxPreviewRows);
  const hasMore = data.length > maxPreviewRows;
  
  if (isLoading) {
    return (
      <Tile className="p-4 mb-4">
        <SkeletonText heading width="40%" />
        <SkeletonText paragraph lineCount={3} />
      </Tile>
    );
  }
  
  if (error) {
    return (
      <Tile className="p-4 mb-4 border-l-4 border-red-500">
        <h3 className="text-lg font-semibold text-red-600">{title}</h3>
        <p className="text-sm text-red-500 mt-2">{error}</p>
      </Tile>
    );
  }
  
  if (data.length === 0) {
    return (
      <Tile className="p-4 mb-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-gray-500 mt-2">查無資料</p>
      </Tile>
    );
  }
  
  return (
    <Tile className="p-4 mb-4">
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="flex items-center gap-2">
            <DataTableIcon size={20} />
            <h3 className="text-lg font-semibold">{title}</h3>
            <Tag type="blue" size="sm">{data.length} 筆</Tag>
          </div>
          {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
        </div>
        {onExport && (
          <Button
            kind="ghost"
            size="sm"
            renderIcon={Download}
            iconDescription="匯出"
            onClick={onExport}
          >
            匯出
          </Button>
        )}
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              {displayColumns.map(col => (
                <th
                  key={col}
                  className="py-2 px-3 text-left font-medium text-gray-600"
                >
                  {getColumnLabel(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {previewData.map((row, i) => (
              <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                {displayColumns.map(col => (
                  <td key={col} className="py-2 px-3">
                    {formatValue(row[col], col)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {hasMore && (
        <div className="mt-3 text-center">
          <Button
            kind="ghost"
            size="sm"
            renderIcon={expanded ? ChevronUp : ChevronDown}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? '收合' : `顯示更多 (${data.length - maxPreviewRows} 筆)`}
          </Button>
        </div>
      )}
    </Tile>
  );
}
