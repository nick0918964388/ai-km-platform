'use client';

import React, { useState } from 'react';
import {
  DataTable as CarbonDataTable,
  Table,
  TableHead,
  TableRow,
  TableHeader,
  TableBody,
  TableCell,
  TableContainer,
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
  Pagination,
  Tag,
  Button,
  Loading,
} from '@carbon/react';
import { Download, Filter } from '@carbon/icons-react';

interface Column {
  key: string;
  header: string;
}

interface DataTableProps {
  title?: string;
  description?: string;
  data: Record<string, any>[];
  columns: Column[];
  isLoading?: boolean;
  pageSize?: number;
  onExport?: () => void;
  onRowClick?: (row: Record<string, any>) => void;
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
  part_number: '零件編號',
  part_name: '零件名稱',
  quantity_on_hand: '庫存量',
  minimum_quantity: '最低庫存',
  unit_price: '單價',
  supplier: '供應商',
  is_low_stock: '庫存警示',
};

// Status tag colors
const STATUS_COLORS: Record<string, 'red' | 'green' | 'blue' | 'gray' | 'orange'> = {
  critical: 'red',
  major: 'orange',
  minor: 'blue',
  active: 'green',
  maintenance: 'blue',
  retired: 'gray',
  open: 'red',
  in_progress: 'blue',
  resolved: 'green',
  completed: 'green',
  pending: 'gray',
};

const formatCellValue = (value: any, key: string): React.ReactNode => {
  if (value === null || value === undefined) return '-';
  
  // Boolean values
  if (typeof value === 'boolean') {
    if (key === 'is_low_stock') {
      return value ? <Tag type="red" size="sm">低庫存</Tag> : <Tag type="green" size="sm">正常</Tag>;
    }
    return value ? '是' : '否';
  }
  
  // Date formatting
  if (key.includes('date') || key.includes('_at')) {
    if (typeof value === 'string') {
      const date = new Date(value);
      if (!isNaN(date.getTime())) {
        return date.toLocaleString('zh-TW', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
        });
      }
    }
    return value;
  }
  
  // Severity/Status as tag
  if (key === 'severity' || key === 'status') {
    const color = STATUS_COLORS[value] || 'gray';
    const labels: Record<string, string> = {
      critical: '嚴重',
      major: '主要',
      minor: '次要',
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
  if (key === 'amount' || key === 'labor_cost' || key.includes('cost') || key === 'unit_price') {
    return `NT$ ${Number(value).toLocaleString('zh-TW')}`;
  }
  
  // Hours formatting
  if (key === 'labor_hours') {
    return `${value} 小時`;
  }
  
  // Truncate long text
  if (typeof value === 'string' && value.length > 50) {
    return value.substring(0, 50) + '...';
  }
  
  return String(value);
};

export default function DataTable({
  title,
  description,
  data,
  columns,
  isLoading = false,
  pageSize = 10,
  onExport,
  onRowClick,
}: DataTableProps) {
  const [page, setPage] = useState(1);
  const [currentPageSize, setCurrentPageSize] = useState(pageSize);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Filter data by search term
  const filteredData = searchTerm
    ? data.filter(row =>
        Object.values(row).some(val =>
          String(val).toLowerCase().includes(searchTerm.toLowerCase())
        )
      )
    : data;
  
  // Paginate
  const startIndex = (page - 1) * currentPageSize;
  const paginatedData = filteredData.slice(startIndex, startIndex + currentPageSize);
  
  // Prepare headers with labels
  const headers = columns.map(col => ({
    key: col.key,
    header: COLUMN_LABELS[col.key] || col.header,
  }));
  
  // Prepare rows with id
  const rows = paginatedData.map((row, index) => ({
    id: row.id || `row-${startIndex + index}`,
    ...row,
  }));
  
  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loading withOverlay={false} description="載入中..." />
      </div>
    );
  }
  
  return (
    <div className="table-container data-table-container">
      <CarbonDataTable rows={rows} headers={headers}>
        {({
          rows: tableRows,
          headers: tableHeaders,
          getHeaderProps,
          getRowProps,
          getTableProps,
          getTableContainerProps,
        }) => (
          <TableContainer
            title={title}
            description={description}
            {...getTableContainerProps()}
          >
            <TableToolbar>
              <TableToolbarContent>
                <TableToolbarSearch
                  placeholder="搜尋..."
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                    setSearchTerm(e.target.value);
                    setPage(1);
                  }}
                />
                {onExport && (
                  <Button
                    kind="ghost"
                    renderIcon={Download}
                    iconDescription="匯出"
                    onClick={onExport}
                  >
                    匯出
                  </Button>
                )}
              </TableToolbarContent>
            </TableToolbar>
            <Table {...getTableProps()}>
              <TableHead>
                <TableRow>
                  {tableHeaders.map(header => (
                    <TableHeader key={header.key} {...getHeaderProps({ header })}>
                      {header.header}
                    </TableHeader>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {tableRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={tableHeaders.length}>
                      <div className="text-center py-4 text-gray-500">
                        查無資料
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  tableRows.map(row => (
                    <TableRow
                      key={row.id}
                      {...getRowProps({ row })}
                      onClick={() => onRowClick?.(data.find(d => d.id === row.id) || {})}
                      style={{ cursor: onRowClick ? 'pointer' : 'default' }}
                    >
                      {row.cells.map(cell => (
                        <TableCell key={cell.id}>
                          {formatCellValue(cell.value, cell.info.header)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CarbonDataTable>
      
      {filteredData.length > currentPageSize && (
        <Pagination
          backwardText="上一頁"
          forwardText="下一頁"
          itemsPerPageText="每頁筆數"
          page={page}
          pageNumberText="頁碼"
          pageSize={currentPageSize}
          pageSizes={[10, 20, 50, 100]}
          totalItems={filteredData.length}
          onChange={({ page: newPage, pageSize: newPageSize }) => {
            setPage(newPage);
            setCurrentPageSize(newPageSize);
          }}
        />
      )}
    </div>
  );
}
