'use client';

import { useState, useCallback, useEffect } from 'react';
import { API_URL, API_KEY, TIMEOUTS, fetchWithTimeout, getErrorMessage } from '@/lib/api';

const API_BASE = API_URL;
const API_HEADERS: Record<string, string> = API_KEY ? { 'X-API-Key': API_KEY } : {};

interface DashboardSummary {
  total_vehicles: number;
  active_vehicles: number;
  open_faults: number;
  critical_faults: number;
  fault_resolution_rate: number;
  pending_maintenance: number;
  low_stock_items: number;
  total_cost_this_month: number;
}

interface FaultTrend {
  date: string;
  fault_type: string;
  count: number;
}

interface CostDistribution {
  cost_type: string;
  amount: number;
  percentage: number;
}

interface VehicleFaultRank {
  vehicle_code: string;
  vehicle_type: string;
  fault_count: number;
  open_faults: number;
}

interface InventoryAlert {
  part_number: string;
  part_name: string;
  category: string;
  quantity_on_hand: number;
  minimum_quantity: number;
  shortage: number;
}

export function useDashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [faultTrends, setFaultTrends] = useState<FaultTrend[]>([]);
  const [costDistribution, setCostDistribution] = useState<CostDistribution[]>([]);
  const [vehicleRanking, setVehicleRanking] = useState<VehicleFaultRank[]>([]);
  const [inventoryAlerts, setInventoryAlerts] = useState<InventoryAlert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [summaryRes, trendsRes, costRes, rankRes, alertsRes] = await Promise.all([
        fetchWithTimeout(`${API_BASE}/api/dashboard/summary`, { headers: API_HEADERS, timeout: TIMEOUTS.DEFAULT }),
        fetchWithTimeout(`${API_BASE}/api/dashboard/fault-trends?days=30`, { headers: API_HEADERS, timeout: TIMEOUTS.DEFAULT }),
        fetchWithTimeout(`${API_BASE}/api/dashboard/cost-distribution?months=3`, { headers: API_HEADERS, timeout: TIMEOUTS.DEFAULT }),
        fetchWithTimeout(`${API_BASE}/api/dashboard/vehicle-fault-ranking?limit=10`, { headers: API_HEADERS, timeout: TIMEOUTS.DEFAULT }),
        fetchWithTimeout(`${API_BASE}/api/dashboard/inventory-alerts`, { headers: API_HEADERS, timeout: TIMEOUTS.DEFAULT }),
      ]);

      if (!summaryRes.ok || !trendsRes.ok || !costRes.ok || !rankRes.ok || !alertsRes.ok) {
        throw new Error('Failed to fetch dashboard data');
      }

      const [summaryData, trendsData, costData, rankData, alertsData] = await Promise.all([
        summaryRes.json(),
        trendsRes.json(),
        costRes.json(),
        rankRes.json(),
        alertsRes.json(),
      ]);

      setSummary(summaryData);
      setFaultTrends(trendsData);
      setCostDistribution(costData);
      setVehicleRanking(rankData);
      setInventoryAlerts(alertsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refresh = useCallback(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    summary,
    faultTrends,
    costDistribution,
    vehicleRanking,
    inventoryAlerts,
    isLoading,
    error,
    refresh,
  };
}

// Individual hooks for specific data
export function useDashboardSummary() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/dashboard/summary`, {
        headers: API_HEADERS,
        timeout: TIMEOUTS.DEFAULT,
      });
      if (!res.ok) throw new Error('Failed to fetch');
      setData(await res.json());
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  return { data, isLoading, error, refresh: fetchSummary };
}
