'use client';

import React, { useState, useEffect } from 'react';
import {
  SidePanel,
  Tabs,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  Button,
  Tag,
  SkeletonText,
} from '@carbon/react';
import { 
  DataBase, 
  Vehicle, 
  Warning, 
  Tool, 
  Money,
  Inventory,
  Close,
} from '@carbon/icons-react';

import DataCard from './DataCard';
import DataTable from './DataTable';
import FilterPanel, { DEFAULT_FILTER_OPTIONS } from './FilterPanel';
import ExportButton from './ExportButton';
import { useVehicles, useInventory } from '@/hooks/useStructuredQuery';

interface DataBrowserPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function DataBrowserPanel({ isOpen, onClose }: DataBrowserPanelProps) {
  const [activeTab, setActiveTab] = useState(0);
  const [filters, setFilters] = useState<Record<string, string>>({});
  
  // Fetch vehicles
  const { vehicles, isLoading: vehiclesLoading, fetchVehicles, meta: vehiclesMeta } = useVehicles();
  
  // Fetch inventory
  const { inventory, isLoading: inventoryLoading, fetchInventory, meta: inventoryMeta } = useInventory();
  
  // Fetch data on mount and filter change
  useEffect(() => {
    if (isOpen) {
      fetchVehicles({
        depot: filters.depot,
        vehicle_type: filters.vehicleType,
        status: filters.status,
      });
    }
  }, [isOpen, filters.depot, filters.vehicleType, filters.status]);
  
  useEffect(() => {
    if (isOpen && activeTab === 4) {
      fetchInventory({
        category: filters.category,
        low_stock_only: filters.lowStockOnly === 'true',
      });
    }
  }, [isOpen, activeTab, filters.category, filters.lowStockOnly]);

  const vehicleColumns = [
    { key: 'vehicle_code', header: '車輛編號' },
    { key: 'vehicle_type', header: '車型' },
    { key: 'depot', header: '機務段' },
    { key: 'status', header: '狀態' },
    { key: 'open_faults', header: '未處理故障' },
  ];

  const inventoryColumns = [
    { key: 'part_number', header: '零件編號' },
    { key: 'part_name', header: '零件名稱' },
    { key: 'category', header: '類別' },
    { key: 'quantity_on_hand', header: '庫存量' },
    { key: 'minimum_quantity', header: '最低庫存' },
    { key: 'is_low_stock', header: '庫存警示' },
  ];

  return (
    <SidePanel
      open={isOpen}
      onRequestClose={onClose}
      title="資料瀏覽"
      subtitle="查看車輛、故障、檢修、成本與庫存資料"
      size="lg"
      includeOverlay={false}
      slideIn
    >
      <div className="p-4">
        <Tabs selectedIndex={activeTab} onChange={({ selectedIndex }) => setActiveTab(selectedIndex)}>
          <TabList aria-label="資料類別">
            <Tab renderIcon={Vehicle}>車輛</Tab>
            <Tab renderIcon={Warning}>故障</Tab>
            <Tab renderIcon={Tool}>檢修</Tab>
            <Tab renderIcon={Money}>成本</Tab>
            <Tab renderIcon={Inventory}>庫存</Tab>
          </TabList>
          
          <TabPanels>
            {/* 車輛 Tab */}
            <TabPanel>
              <div className="space-y-4 mt-4">
                <FilterPanel
                  config={{
                    depot: DEFAULT_FILTER_OPTIONS.depot,
                    vehicleType: DEFAULT_FILTER_OPTIONS.vehicleType,
                    status: DEFAULT_FILTER_OPTIONS.status,
                  }}
                  values={filters}
                  onChange={setFilters}
                />
                
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-500">
                    共 {vehiclesMeta?.row_count || 0} 筆資料
                  </span>
                  <ExportButton
                    exportUrl={`/api/export/vehicles?${new URLSearchParams(filters).toString()}`}
                    label="匯出車輛清單"
                  />
                </div>
                
                {vehiclesLoading ? (
                  <SkeletonText paragraph lineCount={5} />
                ) : (
                  <DataTable
                    data={vehicles}
                    columns={vehicleColumns}
                  />
                )}
              </div>
            </TabPanel>
            
            {/* 故障 Tab */}
            <TabPanel>
              <div className="space-y-4 mt-4">
                <FilterPanel
                  config={{
                    faultType: DEFAULT_FILTER_OPTIONS.faultType,
                    severity: DEFAULT_FILTER_OPTIONS.severity,
                    status: [
                      { id: 'open', label: '待處理' },
                      { id: 'in_progress', label: '處理中' },
                      { id: 'resolved', label: '已解決' },
                    ],
                  }}
                  values={filters}
                  onChange={setFilters}
                  showDateRange
                />
                <p className="text-sm text-gray-500">
                  請先選擇車輛，或使用查詢功能搜尋故障記錄。
                </p>
              </div>
            </TabPanel>
            
            {/* 檢修 Tab */}
            <TabPanel>
              <div className="space-y-4 mt-4">
                <FilterPanel
                  config={{
                    maintenanceType: DEFAULT_FILTER_OPTIONS.maintenanceType,
                    status: [
                      { id: 'pending', label: '待排程' },
                      { id: 'in_progress', label: '進行中' },
                      { id: 'completed', label: '已完成' },
                    ],
                  }}
                  values={filters}
                  onChange={setFilters}
                  showDateRange
                />
                <p className="text-sm text-gray-500">
                  請先選擇車輛，或使用查詢功能搜尋檢修記錄。
                </p>
              </div>
            </TabPanel>
            
            {/* 成本 Tab */}
            <TabPanel>
              <div className="space-y-4 mt-4">
                <FilterPanel
                  config={{
                    costType: DEFAULT_FILTER_OPTIONS.costType,
                  }}
                  values={filters}
                  onChange={setFilters}
                  showDateRange
                />
                <p className="text-sm text-gray-500">
                  請先選擇車輛，或使用查詢功能搜尋成本記錄。
                </p>
              </div>
            </TabPanel>
            
            {/* 庫存 Tab */}
            <TabPanel>
              <div className="space-y-4 mt-4">
                <FilterPanel
                  config={{
                    faultType: DEFAULT_FILTER_OPTIONS.faultType?.map(f => ({
                      ...f,
                      id: f.label, // category uses label as id
                    })),
                  }}
                  values={filters}
                  onChange={setFilters}
                />
                
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-500">
                    共 {inventoryMeta?.row_count || 0} 項零件
                  </span>
                  <ExportButton
                    exportUrl="/api/export/inventory"
                    label="匯出庫存清單"
                  />
                </div>
                
                {inventoryLoading ? (
                  <SkeletonText paragraph lineCount={5} />
                ) : (
                  <DataTable
                    data={inventory}
                    columns={inventoryColumns}
                  />
                )}
              </div>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </div>
    </SidePanel>
  );
}
