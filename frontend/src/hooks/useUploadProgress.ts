"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type TaskStatus = "pending" | "processing" | "completed" | "failed" | "cancelled";
export type ProcessingStep = "uploading" | "parsing" | "chunking" | "embedding" | "indexing" | "done";

export interface ProgressMessage {
  task_id: string;
  status: TaskStatus;
  step: ProcessingStep;
  progress: number;
  message: string;
  chunk_count?: number;
  error?: string;
}

interface UseUploadProgressOptions {
  /** WebSocket URL base (defaults to ws://localhost:8000) */
  wsUrl?: string;
  /** Auto-reconnect on disconnect */
  autoReconnect?: boolean;
  /** Reconnect delay in ms (default: 3000) */
  reconnectDelay?: number;
  /** Max reconnect attempts (default: 5) */
  maxReconnectAttempts?: number;
  /** Callback when progress updates */
  onProgress?: (message: ProgressMessage) => void;
  /** Callback when complete */
  onComplete?: (message: ProgressMessage) => void;
  /** Callback when error */
  onError?: (error: string) => void;
}

interface UseUploadProgressReturn {
  /** Connect to task progress WebSocket */
  connect: (taskId: string) => void;
  /** Disconnect from WebSocket */
  disconnect: () => void;
  /** Cancel the current task */
  cancel: () => void;
  /** Current progress message */
  progress: ProgressMessage | null;
  /** Connection status */
  isConnected: boolean;
  /** Is task complete (success or failure) */
  isComplete: boolean;
  /** Error message if any */
  error: string | null;
}

export function useUploadProgress(options: UseUploadProgressOptions = {}): UseUploadProgressReturn {
  const {
    wsUrl = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000",
    autoReconnect = true,
    reconnectDelay = 3000,
    maxReconnectAttempts = 5,
    onProgress,
    onComplete,
    onError,
  } = options;

  const [progress, setProgress] = useState<ProgressMessage | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const taskIdRef = useRef<string | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const connect = useCallback(
    (taskId: string) => {
      // Cleanup any existing connection
      cleanup();

      taskIdRef.current = taskId;
      reconnectAttemptsRef.current = 0;
      setProgress(null);
      setIsComplete(false);
      setError(null);

      const ws = new WebSocket(`${wsUrl}/api/ws/upload/${taskId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;

        // Setup ping interval to keep connection alive
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: "ping" }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle heartbeat
          if (data.heartbeat) {
            return;
          }

          // Handle pong
          if (data.action === "pong") {
            return;
          }

          // Handle progress message
          const message = data as ProgressMessage;
          setProgress(message);
          onProgress?.(message);

          // Check for completion
          if (
            message.status === "completed" ||
            message.status === "failed" ||
            message.status === "cancelled"
          ) {
            setIsComplete(true);
            if (message.status === "completed") {
              onComplete?.(message);
            } else if (message.error) {
              setError(message.error);
              onError?.(message.error);
            }
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      };

      ws.onclose = (event) => {
        setIsConnected(false);
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Auto-reconnect if not complete and not intentionally closed
        if (
          autoReconnect &&
          !isComplete &&
          taskIdRef.current &&
          reconnectAttemptsRef.current < maxReconnectAttempts
        ) {
          reconnectAttemptsRef.current += 1;
          reconnectTimeoutRef.current = setTimeout(() => {
            if (taskIdRef.current) {
              connect(taskIdRef.current);
            }
          }, reconnectDelay);
        }
      };

      ws.onerror = (event) => {
        console.error("WebSocket error:", event);
        setError("WebSocket connection error");
        onError?.("WebSocket connection error");
      };
    },
    [wsUrl, autoReconnect, reconnectDelay, maxReconnectAttempts, onProgress, onComplete, onError, cleanup, isComplete]
  );

  const disconnect = useCallback(() => {
    taskIdRef.current = null;
    cleanup();
  }, [cleanup]);

  const cancel = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "cancel" }));
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    connect,
    disconnect,
    cancel,
    progress,
    isConnected,
    isComplete,
    error,
  };
}

/**
 * Get human-readable step name in Chinese
 */
export function getStepLabel(step: ProcessingStep): string {
  const labels: Record<ProcessingStep, string> = {
    uploading: "上傳中",
    parsing: "解析文件",
    chunking: "文件分塊",
    embedding: "向量化",
    indexing: "建立索引",
    done: "完成",
  };
  return labels[step] || step;
}

/**
 * Get step order for progress bar segments
 */
export function getStepOrder(step: ProcessingStep): number {
  const order: Record<ProcessingStep, number> = {
    uploading: 0,
    parsing: 1,
    chunking: 2,
    embedding: 3,
    indexing: 4,
    done: 5,
  };
  return order[step] ?? 0;
}
