'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  fetchWithTimeout,
  TimeoutError,
  ApiError,
  getErrorMessage,
  TIMEOUTS,
  type FetchWithTimeoutOptions,
  type RetryConfig,
} from '@/lib/api';

export interface UseApiRequestOptions<T> {
  /** Timeout in milliseconds */
  timeout?: number;
  /** Retry configuration */
  retry?: RetryConfig | boolean;
  /** Called when request succeeds */
  onSuccess?: (data: T) => void;
  /** Called when request fails */
  onError?: (error: Error) => void;
  /** Called on each retry attempt */
  onRetry?: (attempt: number, error: Error, delayMs: number) => void;
}

export interface UseApiRequestReturn<T> {
  /** Response data */
  data: T | null;
  /** Loading state */
  isLoading: boolean;
  /** Error state */
  error: Error | null;
  /** User-friendly error message */
  errorMessage: string | null;
  /** Current retry attempt (0 if not retrying) */
  retryAttempt: number;
  /** Execute the request */
  execute: (url: string, options?: FetchWithTimeoutOptions) => Promise<T | null>;
  /** Manually retry the last request */
  retry: () => Promise<T | null>;
  /** Cancel the current request */
  cancel: () => void;
  /** Reset state */
  reset: () => void;
}

/**
 * Hook for making API requests with timeout, retry, and cancellation support
 */
export function useApiRequest<T = any>(
  options: UseApiRequestOptions<T> = {}
): UseApiRequestReturn<T> {
  const {
    timeout = TIMEOUTS.DEFAULT,
    retry: retryConfig = false,
    onSuccess,
    onError,
    onRetry,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [retryAttempt, setRetryAttempt] = useState(0);

  const abortControllerRef = useRef<AbortController | null>(null);
  const lastRequestRef = useRef<{ url: string; options?: FetchWithTimeoutOptions } | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
  }, []);

  const reset = useCallback(() => {
    cancel();
    setData(null);
    setError(null);
    setIsLoading(false);
    setRetryAttempt(0);
  }, [cancel]);

  const execute = useCallback(async (
    url: string,
    fetchOptions?: FetchWithTimeoutOptions
  ): Promise<T | null> => {
    // Cancel any ongoing request
    cancel();

    // Store for potential retry
    lastRequestRef.current = { url, options: fetchOptions };

    // Create new abort controller
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setError(null);
    setRetryAttempt(0);

    try {
      const response = await fetchWithTimeout(url, {
        ...fetchOptions,
        timeout: fetchOptions?.timeout ?? timeout,
        retry: fetchOptions?.retry ?? retryConfig,
        signal: abortControllerRef.current.signal,
        onRetry: (attempt, err, delayMs) => {
          setRetryAttempt(attempt);
          onRetry?.(attempt, err, delayMs);
          fetchOptions?.onRetry?.(attempt, err, delayMs);
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ApiError(
          errorData.detail || `Request failed: ${response.status}`,
          response.status,
          errorData
        );
      }

      const result: T = await response.json();
      setData(result);
      setRetryAttempt(0);
      onSuccess?.(result);
      return result;
    } catch (err) {
      // Don't set error state if request was cancelled
      if (err instanceof Error && err.name === 'AbortError') {
        return null;
      }

      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      setRetryAttempt(0);
      onError?.(error);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [timeout, retryConfig, cancel, onSuccess, onError, onRetry]);

  const retry = useCallback(async (): Promise<T | null> => {
    if (!lastRequestRef.current) {
      return null;
    }
    return execute(lastRequestRef.current.url, lastRequestRef.current.options);
  }, [execute]);

  return {
    data,
    isLoading,
    error,
    errorMessage: error ? getErrorMessage(error) : null,
    retryAttempt,
    execute,
    retry,
    cancel,
    reset,
  };
}

/**
 * Hook for making JSON API requests (auto-parses response)
 */
export function useJsonRequest<T = any>(options: UseApiRequestOptions<T> = {}) {
  const request = useApiRequest<T>(options);
  
  const executeJson = useCallback(async (
    url: string,
    fetchOptions?: Omit<FetchWithTimeoutOptions, 'headers'> & { headers?: Record<string, string> }
  ): Promise<T | null> => {
    const headers = new Headers(fetchOptions?.headers);
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    
    return request.execute(url, {
      ...fetchOptions,
      headers,
    });
  }, [request]);

  return {
    ...request,
    execute: executeJson,
  };
}

// Re-export types and utilities
export { TimeoutError, ApiError, getErrorMessage, TIMEOUTS };
