/**
 * Structured data types for vehicle maintenance system
 */

// Query result from backend
export interface QueryResult {
  success: boolean;
  data: Record<string, any>[];
  row_count: number;
  columns: string[];
  execution_time_ms: number;
  error?: string;
}

// Unified query response
export interface QueryResponse {
  success: boolean;
  query: string;
  query_type: 'structured' | 'knowledge' | 'hybrid' | 'clarification' | 'error';
  structured_result?: {
    type: 'structured';
    sql: string;
    data: Record<string, any>[];
    row_count: number;
    columns: string[];
    execution_time_ms: number;
  };
  knowledge_result?: {
    answer: string;
    sources: any[];
  };
  message?: string;
  error?: string;
  timestamp: string;
}

// Vehicle data
export interface Vehicle {
  id: string;
  vehicle_code: string;
  vehicle_type: string;
  manufacturer?: string;
  manufacture_year?: number;
  status: 'active' | 'maintenance' | 'retired';
  depot?: string;
  last_maintenance_date?: string;
  open_faults?: number;
}

// Fault record
export interface FaultRecord {
  id: string;
  vehicle_id: string;
  fault_code: string;
  fault_date: string;
  fault_type: string;
  severity: 'critical' | 'major' | 'minor';
  status: 'open' | 'in_progress' | 'resolved';
  description?: string;
  resolution?: string;
  resolved_at?: string;
  reported_by?: string;
  vehicle_code?: string;
  vehicle_type?: string;
}

// Maintenance record
export interface MaintenanceRecord {
  id: string;
  vehicle_id: string;
  maintenance_code: string;
  maintenance_type: 'scheduled' | 'unscheduled' | 'emergency';
  maintenance_date: string;
  completed_date?: string;
  status: 'pending' | 'in_progress' | 'completed';
  description?: string;
  work_performed?: string;
  labor_hours?: number;
  labor_cost?: number;
  technician?: string;
  supervisor?: string;
  vehicle_code?: string;
  vehicle_type?: string;
}

// Usage record
export interface UsageRecord {
  id: string;
  vehicle_id: string;
  record_date: string;
  mileage?: number;
  operating_hours?: number;
  trips_count?: number;
  route?: string;
  electricity_consumption?: number;
}

// Parts inventory
export interface PartsInventory {
  id: string;
  part_number: string;
  part_name: string;
  category: string;
  quantity_on_hand: number;
  minimum_quantity: number;
  unit_price?: number;
  supplier?: string;
  location?: string;
  is_low_stock?: boolean;
}

// Cost record
export interface CostRecord {
  id: string;
  vehicle_id: string;
  record_date: string;
  cost_type: 'labor' | 'parts' | 'external' | 'other';
  category?: string;
  description?: string;
  amount: number;
  currency: string;
  vendor?: string;
  vehicle_code?: string;
  vehicle_type?: string;
}

// API query parameters
export interface VehicleQueryParams {
  depot?: string;
  vehicle_type?: string;
  status?: string;
  limit?: number;
}

export interface FaultQueryParams {
  status?: string;
  fault_type?: string;
  limit?: number;
}

export interface MaintenanceQueryParams {
  status?: string;
  maintenance_type?: string;
  limit?: number;
}

export interface CostQueryParams {
  cost_type?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
}

export interface InventoryQueryParams {
  category?: string;
  low_stock_only?: boolean;
  limit?: number;
}
