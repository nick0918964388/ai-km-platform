"use client";

import { useEffect } from "react";
import { cn } from "@/lib/utils";
import {
  useUploadProgress,
  getStepLabel,
  getStepOrder,
  type ProgressMessage,
  type ProcessingStep,
  type TaskStatus,
} from "@/hooks/useUploadProgress";

interface UploadProgressProps {
  /** Task ID to track */
  taskId: string | null;
  /** Callback when upload completes */
  onComplete?: (message: ProgressMessage) => void;
  /** Callback when upload fails */
  onError?: (error: string) => void;
  /** Additional className */
  className?: string;
}

const STEPS: ProcessingStep[] = ["uploading", "parsing", "chunking", "embedding", "indexing", "done"];

export function UploadProgress({
  taskId,
  onComplete,
  onError,
  className,
}: UploadProgressProps) {
  const {
    connect,
    disconnect,
    cancel,
    progress,
    isConnected,
    isComplete,
    error,
  } = useUploadProgress({
    onComplete,
    onError,
  });

  // Connect when taskId changes
  useEffect(() => {
    if (taskId) {
      connect(taskId);
    } else {
      disconnect();
    }
    return () => disconnect();
  }, [taskId, connect, disconnect]);

  if (!taskId || !progress) {
    return null;
  }

  const currentStepIndex = getStepOrder(progress.step);
  const isError = progress.status === "failed";
  const isCancelled = progress.status === "cancelled";
  const isDone = progress.status === "completed";

  return (
    <div className={cn("w-full rounded-lg border bg-card p-4 shadow-sm", className)}>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StatusIcon status={progress.status} />
          <span className="font-medium">
            {isDone ? "上傳完成" : isCancelled ? "已取消" : isError ? "上傳失敗" : "處理中..."}
          </span>
        </div>
        {!isComplete && (
          <button
            onClick={cancel}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            取消
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="mb-1 flex justify-between text-sm">
          <span className="text-muted-foreground">{progress.message}</span>
          <span className="font-medium">{progress.progress}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full transition-all duration-300",
              isError ? "bg-destructive" : isCancelled ? "bg-muted-foreground" : "bg-primary"
            )}
            style={{ width: `${progress.progress}%` }}
          />
        </div>
      </div>

      {/* Step indicators */}
      <div className="flex items-center justify-between">
        {STEPS.slice(0, -1).map((step, index) => {
          const isActive = index === currentStepIndex;
          const isCompleted = index < currentStepIndex || isDone;
          const isFailed = isError && isActive;

          return (
            <div key={step} className="flex flex-col items-center">
              <div
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium",
                  isCompleted && !isFailed && "bg-primary text-primary-foreground",
                  isActive && !isFailed && !isCompleted && "bg-primary/20 text-primary ring-2 ring-primary",
                  isFailed && "bg-destructive text-destructive-foreground",
                  !isActive && !isCompleted && !isFailed && "bg-muted text-muted-foreground"
                )}
              >
                {isCompleted && !isFailed ? (
                  <CheckIcon />
                ) : isFailed ? (
                  <XIcon />
                ) : (
                  index + 1
                )}
              </div>
              <span
                className={cn(
                  "mt-1 text-xs",
                  isActive || isCompleted ? "text-foreground" : "text-muted-foreground"
                )}
              >
                {getStepLabel(step)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Chunk count */}
      {progress.chunk_count !== undefined && progress.chunk_count > 0 && (
        <div className="mt-3 text-center text-sm text-muted-foreground">
          已處理 <span className="font-medium text-foreground">{progress.chunk_count}</span> 個區塊
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="mt-3 rounded-md bg-destructive/10 p-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Connection status */}
      {!isConnected && !isComplete && (
        <div className="mt-2 text-center text-xs text-muted-foreground">
          重新連線中...
        </div>
      )}
    </div>
  );
}

function StatusIcon({ status }: { status: TaskStatus }) {
  if (status === "completed") {
    return (
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500 text-white">
        <CheckIcon />
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-destructive-foreground">
        <XIcon />
      </div>
    );
  }
  if (status === "cancelled") {
    return (
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <XIcon />
      </div>
    );
  }
  // Processing - animated spinner
  return (
    <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
  );
}

function CheckIcon() {
  return (
    <svg
      className="h-3 w-3"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={3}
        d="M5 13l4 4L19 7"
      />
    </svg>
  );
}

function XIcon() {
  return (
    <svg
      className="h-3 w-3"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={3}
        d="M6 18L18 6M6 6l12 12"
      />
    </svg>
  );
}

export default UploadProgress;
