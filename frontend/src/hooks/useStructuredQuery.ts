'use client';

import { useState, useCallback } from 'react';
import type {
  QueryResult,
  QueryResponse,
  VehicleQueryParams,
  FaultQueryParams,
  MaintenanceQueryParams,
  CostQueryParams,
  InventoryQueryParams,
} from '@/types/structured';
import { API_URL, getApiHeaders, TIMEOUTS, fetchWithTimeout, getErrorMessage } from '@/lib/api';

const API_BASE = API_URL;

interface UseStructuredQueryOptions {
  onSuccess?: (data: any) => void;
  onError?: (error: string) => void;
}

interface UseStructuredQueryReturn {
  data: QueryResult | null;
  isLoading: boolean;
  error: string | null;
  execute: (url: string, params?: Record<string, any>) => Promise<QueryResult | null>;
}

export function useStructuredQuery(options?: UseStructuredQueryOptions): UseStructuredQueryReturn {
  const [data, setData] = useState<QueryResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(async (
    url: string,
    params?: Record<string, any>
  ): Promise<QueryResult | null> => {
    setIsLoading(true);
    setError(null);

    try {
      // Build URL with query params
      const queryString = params
        ? '?' + new URLSearchParams(
            Object.entries(params)
              .filter(([_, v]) => v !== undefined && v !== null)
              .map(([k, v]) => [k, String(v)])
          ).toString()
        : '';

      const response = await fetchWithTimeout(`${API_BASE}${url}${queryString}`, {
        method: 'GET',
        headers: getApiHeaders(),
        timeout: TIMEOUTS.DEFAULT,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result: QueryResult = await response.json();
      
      if (!result.success) {
        throw new Error(result.error || 'Query failed');
      }

      setData(result);
      options?.onSuccess?.(result);
      return result;

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      options?.onError?.(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [options]);

  return { data, isLoading, error, execute };
}

// Natural language query hook
export function useNaturalLanguageQuery(options?: UseStructuredQueryOptions) {
  const [data, setData] = useState<QueryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useCallback(async (
    queryText: string,
    context?: string
  ): Promise<QueryResponse | null> => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetchWithTimeout(`${API_BASE}/api/query`, {
        method: 'POST',
        headers: getApiHeaders(),
        body: JSON.stringify({
          query: queryText,
          context,
          include_sources: true,
        }),
        timeout: TIMEOUTS.DEFAULT,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result: QueryResponse = await response.json();
      
      setData(result);
      
      if (!result.success) {
        setError(result.error || 'Query failed');
        options?.onError?.(result.error || 'Query failed');
      } else {
        options?.onSuccess?.(result);
      }
      
      return result;

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      options?.onError?.(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [options]);

  return { data, isLoading, error, query };
}

// Convenience hooks for specific queries
export function useVehicles(options?: UseStructuredQueryOptions) {
  const { data, isLoading, error, execute } = useStructuredQuery(options);
  
  const fetchVehicles = useCallback((params?: VehicleQueryParams) => {
    return execute('/api/structured/vehicles', params);
  }, [execute]);

  return { vehicles: data?.data || [], isLoading, error, fetchVehicles, meta: data };
}

export function useVehicleFaults(vehicleCode: string, options?: UseStructuredQueryOptions) {
  const { data, isLoading, error, execute } = useStructuredQuery(options);
  
  const fetchFaults = useCallback((params?: FaultQueryParams) => {
    return execute(`/api/structured/vehicles/${vehicleCode}/faults`, params);
  }, [execute, vehicleCode]);

  return { faults: data?.data || [], isLoading, error, fetchFaults, meta: data };
}

export function useVehicleMaintenance(vehicleCode: string, options?: UseStructuredQueryOptions) {
  const { data, isLoading, error, execute } = useStructuredQuery(options);
  
  const fetchMaintenance = useCallback((params?: MaintenanceQueryParams) => {
    return execute(`/api/structured/vehicles/${vehicleCode}/maintenance`, params);
  }, [execute, vehicleCode]);

  return { maintenance: data?.data || [], isLoading, error, fetchMaintenance, meta: data };
}

export function useVehicleCosts(vehicleCode: string, options?: UseStructuredQueryOptions) {
  const { data, isLoading, error, execute } = useStructuredQuery(options);
  
  const fetchCosts = useCallback((params?: CostQueryParams) => {
    return execute(`/api/structured/vehicles/${vehicleCode}/costs`, params);
  }, [execute, vehicleCode]);

  return { costs: data?.data || [], isLoading, error, fetchCosts, meta: data };
}

export function useInventory(options?: UseStructuredQueryOptions) {
  const { data, isLoading, error, execute } = useStructuredQuery(options);
  
  const fetchInventory = useCallback((params?: InventoryQueryParams) => {
    return execute('/api/structured/inventory', params);
  }, [execute]);

  return { inventory: data?.data || [], isLoading, error, fetchInventory, meta: data };
}
