export interface WorkOrderItem {
  wonum: string;
  description: string;
  status: string;
  reportdate: string;
  confidence?: number;
  similarityScore?: number;
}

export interface SopItem {
  sopId: string;
  title: string;
  version: string;
  successRate?: number;
}

export interface PartItem {
  partId: string;
  name: string;
  frequency?: number;
  manufacturer?: string;
}

export interface GraphExpansionData {
  similarWorkOrders: WorkOrderItem[];
  recommendedSops: SopItem[];
  commonParts: PartItem[];
}

export const MOCK_GRAPH_EXPANSION: GraphExpansionData = {
  similarWorkOrders: [
    { wonum: 'WO123456', description: 'EMU01 煞車異響更換', status: 'COMP', reportdate: '2026-03-15', similarityScore: 0.92 },
    { wonum: 'WO123457', description: 'EMU02 煞車系統檢修', status: 'COMP', reportdate: '2026-02-28', similarityScore: 0.88 },
    { wonum: 'WO123458', description: 'EMU01 煞車油更換保養', status: 'COMP', reportdate: '2026-01-10', similarityScore: 0.85 },
  ],
  recommendedSops: [
    { sopId: 'SOP-BRK-001', title: '煞車系統異響診斷流程', version: 'v3.2', successRate: 0.94 },
    { sopId: 'SOP-BRK-002', title: '煞車盤更換標準作業', version: 'v2.1', successRate: 0.89 },
    { sopId: 'SOP-BRK-003', title: '煞車油液壓測試', version: 'v1.5', successRate: 0.82 },
  ],
  commonParts: [
    { partId: 'P-BRK-PAD-01', name: '煞車來令片（前）', frequency: 47, manufacturer: '永冠' },
    { partId: 'P-BRK-OIL-02', name: 'DOT4 煞車油', frequency: 32, manufacturer: 'Shell' },
    { partId: 'P-BRK-DISC-03', name: '煞車盤（後）', frequency: 18, manufacturer: '永冠' },
  ],
};
