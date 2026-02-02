/**
 * API utility for making authenticated requests to the backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

/**
 * Timeout configuration for different types of requests
 */
export const TIMEOUTS = {
  DEFAULT: 30000, // 30 seconds for general API calls
  UPLOAD: 120000, // 120 seconds for file uploads
  STREAMING: 60000, // 60 seconds for chat/streaming
  EXPORT: 90000, // 90 seconds for exports
} as const;

/**
 * Retry configuration
 */
export interface RetryConfig {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  retryOn?: (error: Error, attempt: number) => boolean;
}

const DEFAULT_RETRY_CONFIG: Required<RetryConfig> = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 10000,
  retryOn: (error, _attempt) => {
    // Don't retry on timeout or client errors (4xx)
    if (error instanceof TimeoutError) return false;
    if (error instanceof ApiError && error.status && error.status >= 400 && error.status < 500) {
      return false;
    }
    return true;
  },
};

/**
 * Custom error class for timeout errors
 */
export class TimeoutError extends Error {
  constructor(message = '請求逾時', public timeoutMs?: number) {
    super(message);
    this.name = 'TimeoutError';
  }

  get userMessage(): string {
    return `請求逾時（${this.timeoutMs ? Math.round(this.timeoutMs / 1000) : '?'}秒），請稍後再試`;
  }
}

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public data?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }

  get userMessage(): string {
    if (this.status === 401) return '認證失敗，請重新登入';
    if (this.status === 403) return '您沒有權限執行此操作';
    if (this.status === 404) return '找不到請求的資源';
    if (this.status === 429) return '請求過於頻繁，請稍後再試';
    if (this.status && this.status >= 500) return '伺服器錯誤，請稍後再試';
    return this.message || '發生未知錯誤';
  }
}

/**
 * Calculate exponential backoff delay
 */
function getRetryDelay(attempt: number, baseDelayMs: number, maxDelayMs: number): number {
  const delay = baseDelayMs * Math.pow(2, attempt - 1);
  const jitter = Math.random() * 0.3 * delay; // Add 0-30% jitter
  return Math.min(delay + jitter, maxDelayMs);
}

/**
 * Sleep for a specified duration
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Options for fetchWithTimeout
 */
export interface FetchWithTimeoutOptions extends RequestInit {
  timeout?: number;
  retry?: RetryConfig | boolean;
  onRetry?: (attempt: number, error: Error, delayMs: number) => void;
}

/**
 * Fetch with timeout using AbortController and optional retry
 */
export async function fetchWithTimeout(
  url: string,
  options: FetchWithTimeoutOptions = {}
): Promise<Response> {
  const { 
    timeout = TIMEOUTS.DEFAULT, 
    retry = false,
    onRetry,
    ...fetchOptions 
  } = options;

  const retryConfig = retry === true 
    ? DEFAULT_RETRY_CONFIG 
    : retry === false 
      ? { ...DEFAULT_RETRY_CONFIG, maxRetries: 0 }
      : { ...DEFAULT_RETRY_CONFIG, ...retry };

  let lastError: Error = new Error('Unknown error');
  
  for (let attempt = 1; attempt <= retryConfig.maxRetries + 1; attempt++) {
    const controller = new AbortController();
    
    // Merge abort signals if one was provided
    const externalSignal = fetchOptions.signal;
    if (externalSignal?.aborted) {
      throw new DOMException('Request aborted', 'AbortError');
    }
    
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    // Listen for external abort
    const abortHandler = () => controller.abort();
    externalSignal?.addEventListener('abort', abortHandler);

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      externalSignal?.removeEventListener('abort', abortHandler);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      externalSignal?.removeEventListener('abort', abortHandler);

      // Handle abort from external signal
      if (externalSignal?.aborted) {
        throw new DOMException('Request aborted', 'AbortError');
      }

      if (error instanceof Error && error.name === 'AbortError') {
        lastError = new TimeoutError(`請求逾時（${Math.round(timeout / 1000)}秒）`, timeout);
      } else {
        lastError = error instanceof Error ? error : new Error(String(error));
      }

      // Check if we should retry
      const shouldRetry = attempt < retryConfig.maxRetries + 1 && 
        retryConfig.retryOn(lastError, attempt);

      if (shouldRetry) {
        const delayMs = getRetryDelay(attempt, retryConfig.baseDelayMs, retryConfig.maxDelayMs);
        onRetry?.(attempt, lastError, delayMs);
        await sleep(delayMs);
      } else {
        throw lastError;
      }
    }
  }

  throw lastError;
}

/**
 * Options for API requests
 */
export interface ApiRequestOptions extends Omit<FetchWithTimeoutOptions, 'body'> {
  timeout?: number;
  retry?: RetryConfig | boolean;
  signal?: AbortSignal;
}

/**
 * Make an authenticated API request with timeout support
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit & ApiRequestOptions = {}
): Promise<T> {
  const { timeout = TIMEOUTS.DEFAULT, retry, signal, onRetry, ...fetchOptions } = options;
  
  const headers = new Headers(fetchOptions.headers);
  headers.set('Content-Type', 'application/json');

  if (API_KEY) {
    headers.set('X-API-Key', API_KEY);
  }

  const response = await fetchWithTimeout(`${API_URL}${endpoint}`, {
    ...fetchOptions,
    headers,
    timeout,
    retry,
    signal,
    onRetry,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(
      errorData.detail || `API request failed: ${response.status}`,
      response.status,
      errorData
    );
  }

  return response.json();
}

/**
 * GET request helper
 */
export async function apiGet<T>(
  endpoint: string, 
  options?: ApiRequestOptions
): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'GET', ...options });
}

/**
 * POST request helper
 */
export async function apiPost<T>(
  endpoint: string,
  data: unknown,
  options?: ApiRequestOptions
): Promise<T> {
  return apiRequest<T>(endpoint, {
    method: 'POST',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * PUT request helper
 */
export async function apiPut<T>(
  endpoint: string,
  data: unknown,
  options?: ApiRequestOptions
): Promise<T> {
  return apiRequest<T>(endpoint, {
    method: 'PUT',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * DELETE request helper
 */
export async function apiDelete<T>(
  endpoint: string,
  options?: ApiRequestOptions
): Promise<T> {
  return apiRequest<T>(endpoint, { method: 'DELETE', ...options });
}

/**
 * Upload file with progress tracking (uses longer timeout)
 */
export async function apiUpload<T>(
  endpoint: string,
  formData: FormData,
  options?: Omit<ApiRequestOptions, 'timeout'> & { timeout?: number }
): Promise<T> {
  const headers = new Headers();
  // Don't set Content-Type for FormData - browser will set it with boundary
  
  if (API_KEY) {
    headers.set('X-API-Key', API_KEY);
  }

  const response = await fetchWithTimeout(`${API_URL}${endpoint}`, {
    method: 'POST',
    body: formData,
    headers,
    timeout: options?.timeout ?? TIMEOUTS.UPLOAD,
    retry: options?.retry,
    signal: options?.signal,
    onRetry: options?.onRetry,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(
      errorData.detail || `Upload failed: ${response.status}`,
      response.status,
      errorData
    );
  }

  return response.json();
}

/**
 * Get user-friendly error message
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof TimeoutError) {
    return error.userMessage;
  }
  if (error instanceof ApiError) {
    return error.userMessage;
  }
  if (error instanceof Error) {
    if (error.name === 'AbortError') {
      return '請求已取消';
    }
    return error.message || '發生未知錯誤';
  }
  return '發生未知錯誤';
}

/**
 * Get base headers with API key
 */
export function getApiHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }
  
  return headers;
}

export { API_URL, API_KEY };
