'use client';

import { useState, useEffect, useCallback } from 'react';
import type { TableSchema } from '@/types/pgViewer';
import { FeatureDisabledError, ForbiddenError } from '@/types/pgViewer';
import { getTableSchema } from '@/services/pgViewerService';

export function useTableSchema(tableName: string | null) {
  const [schema, setSchema] = useState<TableSchema | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [featureDisabled, setFeatureDisabled] = useState(false);
  const [forbidden, setForbidden] = useState(false);

  const refresh = useCallback(async () => {
    if (!tableName) return;
    setLoading(true);
    setError(null);
    setFeatureDisabled(false);
    setForbidden(false);
    try {
      const data = await getTableSchema(tableName);
      setSchema(data);
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
  }, [tableName]);

  useEffect(() => {
    setSchema(null);
    refresh();
  }, [refresh]);

  return { schema, loading, error, featureDisabled, forbidden, refresh };
}
