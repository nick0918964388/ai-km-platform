'use client';

import React, { useState } from 'react';
import {
  Accordion,
  AccordionItem,
  Dropdown,
  DatePicker,
  DatePickerInput,
  Button,
  Tag,
} from '@carbon/react';
import { Filter, Close, Reset } from '@carbon/icons-react';

interface FilterOption {
  id: string;
  label: string;
}

interface FilterConfig {
  depot?: FilterOption[];
  vehicleType?: FilterOption[];
  status?: FilterOption[];
  faultType?: FilterOption[];
  maintenanceType?: FilterOption[];
  costType?: FilterOption[];
  severity?: FilterOption[];
}

interface FilterValues {
  depot?: string;
  vehicleType?: string;
  status?: string;
  faultType?: string;
  maintenanceType?: string;
  costType?: string;
  severity?: string;
  startDate?: string;
  endDate?: string;
}

interface FilterPanelProps {
  config: FilterConfig;
  values: FilterValues;
  onChange: (values: FilterValues) => void;
  onReset?: () => void;
  showDateRange?: boolean;
}

// Default filter options
export const DEFAULT_FILTER_OPTIONS: FilterConfig = {
  depot: [
    { id: '新竹機務段', label: '新竹機務段' },
    { id: '台中機務段', label: '台中機務段' },
    { id: '高雄機務段', label: '高雄機務段' },
    { id: '花蓮機務段', label: '花蓮機務段' },
  ],
  vehicleType: [
    { id: 'EMU800系列', label: 'EMU800系列' },
    { id: 'TEMU2000型', label: 'TEMU2000型' },
    { id: 'EMC300型', label: 'EMC300型' },
  ],
  status: [
    { id: 'active', label: '運行中' },
    { id: 'maintenance', label: '維修中' },
    { id: 'retired', label: '已退役' },
  ],
  faultType: [
    { id: '轉向架', label: '轉向架' },
    { id: '煞車系統', label: '煞車系統' },
    { id: '電氣系統', label: '電氣系統' },
    { id: '空調系統', label: '空調系統' },
    { id: '門機系統', label: '門機系統' },
    { id: '推進系統', label: '推進系統' },
    { id: '集電弓', label: '集電弓' },
  ],
  maintenanceType: [
    { id: 'scheduled', label: '定期保養' },
    { id: 'unscheduled', label: '臨時檢修' },
    { id: 'emergency', label: '緊急搶修' },
  ],
  costType: [
    { id: 'labor', label: '人工' },
    { id: 'parts', label: '零件' },
    { id: 'external', label: '外包' },
    { id: 'other', label: '其他' },
  ],
  severity: [
    { id: 'critical', label: '嚴重' },
    { id: 'major', label: '主要' },
    { id: 'minor', label: '次要' },
  ],
};

export default function FilterPanel({
  config,
  values,
  onChange,
  onReset,
  showDateRange = false,
}: FilterPanelProps) {
  const [isOpen, setIsOpen] = useState(true);

  const activeFiltersCount = Object.values(values).filter(v => v).length;

  const handleFilterChange = (key: keyof FilterValues, value: string | undefined) => {
    onChange({ ...values, [key]: value || undefined });
  };

  const handleReset = () => {
    onChange({});
    onReset?.();
  };

  return (
    <div className="filter-panel bg-white border border-gray-200 rounded-lg">
      <div 
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <Filter size={16} />
          <span className="font-medium">篩選條件</span>
          {activeFiltersCount > 0 && (
            <Tag type="blue" size="sm">{activeFiltersCount}</Tag>
          )}
        </div>
        {activeFiltersCount > 0 && (
          <Button
            kind="ghost"
            size="sm"
            renderIcon={Reset}
            iconDescription="重設"
            onClick={(e) => {
              e.stopPropagation();
              handleReset();
            }}
          >
            重設
          </Button>
        )}
      </div>

      {isOpen && (
        <div className="p-3 pt-0 space-y-3">
          {config.depot && (
            <Dropdown
              id="filter-depot"
              titleText="機務段"
              label="全部"
              items={[{ id: '', label: '全部' }, ...config.depot]}
              selectedItem={config.depot.find(d => d.id === values.depot) || { id: '', label: '全部' }}
              itemToString={(item) => item?.label || ''}
              onChange={({ selectedItem }) => handleFilterChange('depot', selectedItem?.id)}
            />
          )}

          {config.vehicleType && (
            <Dropdown
              id="filter-vehicle-type"
              titleText="車型"
              label="全部"
              items={[{ id: '', label: '全部' }, ...config.vehicleType]}
              selectedItem={config.vehicleType.find(d => d.id === values.vehicleType) || { id: '', label: '全部' }}
              itemToString={(item) => item?.label || ''}
              onChange={({ selectedItem }) => handleFilterChange('vehicleType', selectedItem?.id)}
            />
          )}

          {config.status && (
            <Dropdown
              id="filter-status"
              titleText="狀態"
              label="全部"
              items={[{ id: '', label: '全部' }, ...config.status]}
              selectedItem={config.status.find(d => d.id === values.status) || { id: '', label: '全部' }}
              itemToString={(item) => item?.label || ''}
              onChange={({ selectedItem }) => handleFilterChange('status', selectedItem?.id)}
            />
          )}

          {config.faultType && (
            <Dropdown
              id="filter-fault-type"
              titleText="故障類型"
              label="全部"
              items={[{ id: '', label: '全部' }, ...config.faultType]}
              selectedItem={config.faultType.find(d => d.id === values.faultType) || { id: '', label: '全部' }}
              itemToString={(item) => item?.label || ''}
              onChange={({ selectedItem }) => handleFilterChange('faultType', selectedItem?.id)}
            />
          )}

          {config.maintenanceType && (
            <Dropdown
              id="filter-maintenance-type"
              titleText="檢修類型"
              label="全部"
              items={[{ id: '', label: '全部' }, ...config.maintenanceType]}
              selectedItem={config.maintenanceType.find(d => d.id === values.maintenanceType) || { id: '', label: '全部' }}
              itemToString={(item) => item?.label || ''}
              onChange={({ selectedItem }) => handleFilterChange('maintenanceType', selectedItem?.id)}
            />
          )}

          {config.costType && (
            <Dropdown
              id="filter-cost-type"
              titleText="成本類型"
              label="全部"
              items={[{ id: '', label: '全部' }, ...config.costType]}
              selectedItem={config.costType.find(d => d.id === values.costType) || { id: '', label: '全部' }}
              itemToString={(item) => item?.label || ''}
              onChange={({ selectedItem }) => handleFilterChange('costType', selectedItem?.id)}
            />
          )}

          {config.severity && (
            <Dropdown
              id="filter-severity"
              titleText="嚴重程度"
              label="全部"
              items={[{ id: '', label: '全部' }, ...config.severity]}
              selectedItem={config.severity.find(d => d.id === values.severity) || { id: '', label: '全部' }}
              itemToString={(item) => item?.label || ''}
              onChange={({ selectedItem }) => handleFilterChange('severity', selectedItem?.id)}
            />
          )}

          {showDateRange && (
            <div className="grid grid-cols-2 gap-2">
              <DatePicker
                datePickerType="single"
                onChange={(dates) => handleFilterChange('startDate', dates[0]?.toISOString().split('T')[0])}
              >
                <DatePickerInput
                  id="filter-start-date"
                  labelText="開始日期"
                  placeholder="yyyy/mm/dd"
                />
              </DatePicker>
              <DatePicker
                datePickerType="single"
                onChange={(dates) => handleFilterChange('endDate', dates[0]?.toISOString().split('T')[0])}
              >
                <DatePickerInput
                  id="filter-end-date"
                  labelText="結束日期"
                  placeholder="yyyy/mm/dd"
                />
              </DatePicker>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
