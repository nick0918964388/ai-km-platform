'use client';

import { useState, useEffect, useCallback } from 'react';
import type { AuditEntry } from '@/types/pgViewer';
import { getAudit } from '@/services/pgViewerService';

export interface UsePgViewerAuditParams {
  limit: number;
  offset: number;
  user_id?: string;
  query_type?: string;
  status?: string;
  since?: string;
  until?: string;
}

export interface UsePgViewerAuditResult {
  items: AuditEntry[];
  total: number;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function usePgViewerAudit(params: UsePgViewerAuditParams): UsePgViewerAuditResult {
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAudit(params);
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : '載入失敗');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    params.limit,
    params.offset,
    params.user_id,
    params.query_type,
    params.status,
    params.since,
    params.until,
  ]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { items, total, loading, error, refresh: fetch };
}
