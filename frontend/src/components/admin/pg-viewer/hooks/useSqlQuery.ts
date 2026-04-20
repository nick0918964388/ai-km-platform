'use client';

/**
 * useSqlQuery — state machine for the SQL editor
 *
 * Wraps pgViewerService.runSql() and maps every documented error status to
 * an explicit UI-facing state bucket.  Callers never inspect raw Error objects.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { runSql } from '@/services/pgViewerService';
import {
  ForbiddenError,
  FeatureDisabledError,
  RateLimitError,
} from '@/types/pgViewer';
import type { SqlResult } from '@/types/pgViewer';
import { ApiError } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SqlQueryState {
  result: SqlResult | null;
  loading: boolean;
  error: string | null;
  elapsedMs: number | null;
  rateLimited: boolean;
  retryAfter: number | null;
  featureDisabled: boolean;
}

const INITIAL_STATE: SqlQueryState = {
  result: null,
  loading: false,
  error: null,
  elapsedMs: null,
  rateLimited: false,
  retryAfter: null,
  featureDisabled: false,
};

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSqlQuery() {
  const [state, setState] = useState<SqlQueryState>(INITIAL_STATE);

  // Countdown interval handle — cleared on unmount + new run
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clear the rate-limit countdown timer on unmount
  useEffect(() => {
    return () => {
      if (countdownRef.current !== null) {
        clearInterval(countdownRef.current);
      }
    };
  }, []);

  const run = useCallback(async (sql: string) => {
    // Clear any previous countdown
    if (countdownRef.current !== null) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }

    setState({
      result: null,
      loading: true,
      error: null,
      elapsedMs: null,
      rateLimited: false,
      retryAfter: null,
      featureDisabled: false,
    });

    try {
      const result = await runSql(sql);
      setState((prev) => ({
        ...prev,
        result,
        loading: false,
        elapsedMs: result.elapsed_ms ?? null,
      }));
    } catch (err) {
      if (err instanceof RateLimitError) {
        // Start countdown
        const initial = err.retryAfter;
        setState((prev) => ({
          ...prev,
          loading: false,
          rateLimited: true,
          retryAfter: initial,
        }));

        let remaining = initial;
        countdownRef.current = setInterval(() => {
          remaining -= 1;
          if (remaining <= 0) {
            clearInterval(countdownRef.current!);
            countdownRef.current = null;
            setState((prev) => ({
              ...prev,
              rateLimited: false,
              retryAfter: null,
            }));
          } else {
            setState((prev) => ({ ...prev, retryAfter: remaining }));
          }
        }, 1000);
        return;
      }

      if (err instanceof FeatureDisabledError) {
        setState((prev) => ({
          ...prev,
          loading: false,
          featureDisabled: true,
        }));
        return;
      }

      if (err instanceof ForbiddenError) {
        // Redirect to / per existing auth flow (non-admin landed here somehow)
        if (typeof window !== 'undefined') {
          window.location.replace('/');
        }
        return;
      }

      if (err instanceof ApiError) {
        let msg: string;
        if (err.status === 408) {
          msg = 'Query timed out (10s). Refine your query with narrower filters.';
        } else {
          // Try to surface the structured detail field from the backend
          const detail =
            err.data && typeof err.data === 'object' && 'detail' in err.data
              ? String((err.data as Record<string, unknown>).detail)
              : err.message;
          msg = detail;
        }
        setState((prev) => ({ ...prev, loading: false, error: msg }));
        return;
      }

      // Unexpected error
      setState((prev) => ({
        ...prev,
        loading: false,
        error: err instanceof Error ? err.message : 'Unexpected error',
      }));
    }
  }, []);

  const reset = useCallback(() => {
    if (countdownRef.current !== null) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    setState(INITIAL_STATE);
  }, []);

  return { ...state, run, reset };
}
