'use client';

import { useState, useEffect } from 'react';
import {
  Dashboard,
  Document,
  Chat,
  User,
  Activity,
  CheckmarkFilled,
  WarningFilled,
  Upload,
  Settings,
  Time,
  Vehicle,
  Warning,
  Tool,
  Money,
  Inventory,
  Renew,
} from '@carbon/icons-react';
import { Button } from '@carbon/react';

import { StatCard, TrendChart, CostDistributionChart, InventoryAlert } from '@/components/dashboard';
import { useDashboard } from '@/hooks/useDashboard';

interface RecentActivity {
  id: string;
  type: 'upload' | 'chat' | 'user' | 'setting';
  message: string;
  time: string;
  user: string;
}

export default function DashboardPage() {
  const {
    summary,
    faultTrends,
    costDistribution,
    vehicleRanking,
    inventoryAlerts,
    isLoading,
    error,
    refresh,
  } = useDashboard();

  const [activities] = useState<RecentActivity[]>([
    { id: '1', type: 'upload', message: '上傳了「引擎維修手冊.pdf」', time: '5 分鐘前', user: '管理員' },
    { id: '2', type: 'chat', message: '發起了新對話「引擎異響問題」', time: '10 分鐘前', user: '技師 A' },
    { id: '3', type: 'user', message: '新增了使用者「技師 C」', time: '1 小時前', user: '管理員' },
    { id: '4', type: 'setting', message: '更新了系統設定', time: '2 小時前', user: '管理員' },
  ]);

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'upload': return <Upload size={16} />;
      case 'chat': return <Chat size={16} />;
      case 'user': return <User size={16} />;
      case 'setting': return <Settings size={16} />;
      default: return <Activity size={16} />;
    }
  };

  // Fault type colors for trend chart
  const faultTypeColors: Record<string, string> = {
    '轉向架': '#0f62fe',
    '煞車系統': '#fa4d56',
    '電氣系統': '#8a3ffc',
    '空調系統': '#42be65',
    '門機系統': '#ff7eb6',
    '推進系統': '#f1c21b',
    '集電弓': '#00bab6',
  };

  const uniqueFaultTypes = [...new Set(faultTrends.map(t => t.fault_type))];
  const trendLines = uniqueFaultTypes.map(type => ({
    key: type,
    name: type,
    color: faultTypeColors[type] || '#6f6f6f',
  }));

  return (
    <div style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ 
          fontSize: '1.75rem', 
          fontWeight: 600, 
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <Dashboard size={28} />
          營運儀表板
        </h1>
        <Button
          kind="ghost"
          renderIcon={Renew}
          onClick={refresh}
          disabled={isLoading}
        >
          重新整理
        </Button>
      </div>

      {error && (
        <div className="p-4 mb-4 bg-red-50 text-red-700 rounded-lg">
          載入失敗：{error}
        </div>
      )}

      {/* Key Metrics */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '1rem',
        marginBottom: '2rem'
      }}>
        <StatCard
          title="營運車輛"
          value={summary?.active_vehicles || 0}
          unit={`/ ${summary?.total_vehicles || 0}`}
          icon={<Vehicle size={24} className="text-blue-600" />}
          color="default"
          isLoading={isLoading}
        />
        <StatCard
          title="待處理故障"
          value={summary?.open_faults || 0}
          icon={<Warning size={24} className="text-red-600" />}
          color={summary?.critical_faults && summary.critical_faults > 0 ? 'danger' : 'warning'}
          isLoading={isLoading}
        />
        <StatCard
          title="待排程檢修"
          value={summary?.pending_maintenance || 0}
          icon={<Tool size={24} className="text-yellow-600" />}
          color="warning"
          isLoading={isLoading}
        />
        <StatCard
          title="本月成本"
          value={summary ? `${Math.round(summary.total_cost_this_month / 10000)}萬` : 0}
          icon={<Money size={24} className="text-green-600" />}
          color="success"
          isLoading={isLoading}
        />
        <StatCard
          title="故障解決率"
          value={`${summary?.fault_resolution_rate || 0}%`}
          icon={<CheckmarkFilled size={24} className="text-green-600" />}
          color="success"
          isLoading={isLoading}
        />
        <StatCard
          title="低庫存警示"
          value={summary?.low_stock_items || 0}
          unit="項"
          icon={<Inventory size={24} className="text-orange-600" />}
          color={summary?.low_stock_items && summary.low_stock_items > 0 ? 'danger' : 'success'}
          isLoading={isLoading}
        />
      </div>

      {/* Charts Row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
        gap: '1.5rem',
        marginBottom: '2rem'
      }}>
        <TrendChart
          title="故障趨勢（近 30 天）"
          data={faultTrends}
          lines={trendLines}
          isLoading={isLoading}
          height={280}
        />
        <CostDistributionChart
          title="成本分布（近 3 個月）"
          data={costDistribution}
          isLoading={isLoading}
          height={280}
        />
      </div>

      {/* Bottom Row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
        gap: '1.5rem',
        marginBottom: '2rem'
      }}>
        {/* Inventory Alerts */}
        <InventoryAlert
          title="庫存警示"
          alerts={inventoryAlerts}
          isLoading={isLoading}
          maxItems={5}
        />

        {/* Vehicle Fault Ranking */}
        <div className="settings-section" style={{ padding: '1.5rem' }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Vehicle size={20} />
            故障排行（近 90 天）
          </h3>
          {isLoading ? (
            <p className="text-gray-500">載入中...</p>
          ) : vehicleRanking.length === 0 ? (
            <p className="text-gray-500 text-center py-4">暫無資料</p>
          ) : (
            <ul className="space-y-2">
              {vehicleRanking.slice(0, 5).map((v, i) => (
                <li key={v.vehicle_code} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                  <div className="flex items-center gap-3">
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      i === 0 ? 'bg-red-100 text-red-700' :
                      i === 1 ? 'bg-orange-100 text-orange-700' :
                      i === 2 ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {i + 1}
                    </span>
                    <div>
                      <p className="font-medium text-sm">{v.vehicle_code}</p>
                      <p className="text-xs text-gray-500">{v.vehicle_type}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-bold">{v.fault_count} 次</p>
                    {v.open_faults > 0 && (
                      <p className="text-xs text-red-500">{v.open_faults} 待處理</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Recent Activity */}
        <div className="settings-section" style={{ padding: '1.5rem' }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={20} />
            最近活動
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {activities.map(activity => (
              <div 
                key={activity.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                  padding: '0.75rem',
                  background: 'var(--bg-secondary)',
                  borderRadius: '8px'
                }}
              >
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'var(--bg-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--text-secondary)'
                }}>
                  {getActivityIcon(activity.type)}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '0.875rem' }}>
                    <strong>{activity.user}</strong> {activity.message}
                  </div>
                </div>
                <div style={{ 
                  fontSize: '0.75rem', 
                  color: 'var(--text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem'
                }}>
                  <Time size={12} />
                  {activity.time}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="settings-section" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem' }}>
          快速操作
        </h2>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <a href="/admin/knowledge-base" className="btn btn-primary" style={{ textDecoration: 'none' }}>
            <Upload size={16} />
            上傳文件
          </a>
          <a href="/chat" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
            <Chat size={16} />
            開始對話
          </a>
          <a href="/admin/users" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
            <User size={16} />
            管理使用者
          </a>
          <a href="/settings" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
            <Settings size={16} />
            系統設定
          </a>
        </div>
      </div>
    </div>
  );
}
