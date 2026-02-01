"""Task manager for document processing with Redis-backed storage."""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Callable
import redis

from app.config import get_settings
from app.models.schemas import ProcessingTask, TaskStatus, ProcessingStep, ProgressMessage

logger = logging.getLogger(__name__)

# Task key prefix
TASK_PREFIX = "task:"
ACTIVE_TASKS_KEY = "tasks:active"

# Task TTL after completion (24 hours)
TASK_TTL = 86400

# Progress callback type
ProgressCallback = Callable[[ProgressMessage], None]

# Active callbacks (in-memory, per-process)
_progress_callbacks: dict[str, list[ProgressCallback]] = {}


def _get_redis() -> Optional[redis.Redis]:
    """Get Redis client for task storage."""
    settings = get_settings()
    try:
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis unavailable for task storage: {e}")
        return None


def create_task(
    document_id: str,
    filename: str,
    file_size: int,
) -> ProcessingTask:
    """Create a new processing task."""
    task_id = str(uuid.uuid4())
    now = datetime.utcnow()

    task = ProcessingTask(
        id=task_id,
        document_id=document_id,
        filename=filename,
        file_size=file_size,
        status=TaskStatus.PENDING,
        step=ProcessingStep.UPLOADING,
        progress=0,
        created_at=now,
        updated_at=now,
    )

    # Store in Redis
    client = _get_redis()
    if client:
        key = f"{TASK_PREFIX}{task_id}"
        client.set(key, task.model_dump_json(), ex=TASK_TTL)
        client.sadd(ACTIVE_TASKS_KEY, task_id)
        logger.info(f"Created task: {task_id} for {filename}")

    return task


def get_task(task_id: str) -> Optional[ProcessingTask]:
    """Get a task by ID."""
    client = _get_redis()
    if not client:
        return None

    key = f"{TASK_PREFIX}{task_id}"
    data = client.get(key)
    if not data:
        return None

    try:
        return ProcessingTask.model_validate_json(data)
    except Exception as e:
        logger.error(f"Invalid task data for {task_id}: {e}")
        return None


def update_task(
    task_id: str,
    status: Optional[TaskStatus] = None,
    step: Optional[ProcessingStep] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    chunk_count: Optional[int] = None,
) -> Optional[ProcessingTask]:
    """Update a task and notify callbacks."""
    task = get_task(task_id)
    if not task:
        return None

    # Update fields
    task.updated_at = datetime.utcnow()

    if status is not None:
        task.status = status
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.completed_at = task.updated_at

    if step is not None:
        task.step = step

    if progress is not None:
        task.progress = max(0, min(100, progress))

    if message is not None:
        task.message = message

    if error is not None:
        task.error = error

    if chunk_count is not None:
        task.chunk_count = chunk_count

    # Store updated task
    client = _get_redis()
    if client:
        key = f"{TASK_PREFIX}{task_id}"
        client.set(key, task.model_dump_json(), ex=TASK_TTL)

        # Remove from active set if completed
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            client.srem(ACTIVE_TASKS_KEY, task_id)

    # Notify callbacks
    _notify_progress(task)

    return task


def list_active_tasks() -> list[ProcessingTask]:
    """List all active (non-completed) tasks."""
    client = _get_redis()
    if not client:
        return []

    task_ids = client.smembers(ACTIVE_TASKS_KEY)
    tasks = []

    for task_id in task_ids:
        task = get_task(task_id)
        if task:
            tasks.append(task)

    return sorted(tasks, key=lambda t: t.created_at, reverse=True)


def delete_task(task_id: str) -> bool:
    """Delete a task."""
    client = _get_redis()
    if not client:
        return False

    key = f"{TASK_PREFIX}{task_id}"
    client.delete(key)
    client.srem(ACTIVE_TASKS_KEY, task_id)

    # Remove callbacks
    if task_id in _progress_callbacks:
        del _progress_callbacks[task_id]

    return True


def register_callback(task_id: str, callback: ProgressCallback) -> None:
    """Register a callback for task progress updates."""
    if task_id not in _progress_callbacks:
        _progress_callbacks[task_id] = []
    _progress_callbacks[task_id].append(callback)
    logger.debug(f"Registered callback for task {task_id}")


def unregister_callback(task_id: str, callback: ProgressCallback) -> None:
    """Unregister a callback."""
    if task_id in _progress_callbacks:
        try:
            _progress_callbacks[task_id].remove(callback)
            if not _progress_callbacks[task_id]:
                del _progress_callbacks[task_id]
        except ValueError:
            pass


def _notify_progress(task: ProcessingTask) -> None:
    """Notify all registered callbacks about task progress."""
    callbacks = _progress_callbacks.get(task.id, [])
    if not callbacks:
        return

    message = ProgressMessage(
        task_id=task.id,
        status=task.status,
        step=task.step,
        progress=task.progress,
        message=task.message or _get_step_message(task.step, task.progress),
        chunk_count=task.chunk_count,
        error=task.error,
    )

    for callback in callbacks:
        try:
            callback(message)
        except Exception as e:
            logger.error(f"Callback error for task {task.id}: {e}")


def _get_step_message(step: ProcessingStep, progress: int) -> str:
    """Get a human-readable message for the current step."""
    messages = {
        ProcessingStep.UPLOADING: "上傳中...",
        ProcessingStep.PARSING: "解析文件中...",
        ProcessingStep.CHUNKING: "文件分塊中...",
        ProcessingStep.EMBEDDING: f"向量化中 ({progress}%)...",
        ProcessingStep.INDEXING: "建立索引中...",
        ProcessingStep.DONE: "處理完成！",
    }
    return messages.get(step, "處理中...")


# Context manager for progress tracking
class ProgressTracker:
    """Context manager for tracking document processing progress."""

    def __init__(self, task_id: str):
        self.task_id = task_id

    def update(
        self,
        step: ProcessingStep,
        progress: int,
        message: Optional[str] = None,
        chunk_count: Optional[int] = None,
    ):
        """Update progress."""
        update_task(
            self.task_id,
            step=step,
            progress=progress,
            message=message,
            chunk_count=chunk_count,
        )

    def complete(self, chunk_count: int, message: str = "處理完成！"):
        """Mark task as complete."""
        update_task(
            self.task_id,
            status=TaskStatus.COMPLETED,
            step=ProcessingStep.DONE,
            progress=100,
            message=message,
            chunk_count=chunk_count,
        )

    def fail(self, error: str):
        """Mark task as failed."""
        update_task(
            self.task_id,
            status=TaskStatus.FAILED,
            error=error,
            message=f"處理失敗: {error}",
        )
