'use client';

import { useState, useEffect, useCallback } from 'react';
import type { TableSummary } from '@/types/pgViewer';
import { FeatureDisabledError, ForbiddenError } from '@/types/pgViewer';
import { listTables } from '@/services/pgViewerService';

export function useTables() {
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [featureDisabled, setFeatureDisabled] = useState(false);
  const [forbidden, setForbidden] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFeatureDisabled(false);
    setForbidden(false);
    try {
      const data = await listTables();
      setTables(data);
    } catch (e) {
      if (e instanceof FeatureDisabledError) {
        setFeatureDisabled(true);
      } else if (e instanceof ForbiddenError) {
        setForbidden(true);
      } else {
        setError(e instanceof Error ? e.message : '載入失敗');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { tables, loading, error, featureDisabled, forbidden, refresh };
}
