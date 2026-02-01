"""WebSocket router for upload progress tracking."""
import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.schemas import ProgressMessage, TaskStatus
from app.services import task_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Active WebSocket connections per task
_active_connections: dict[str, list[WebSocket]] = {}


async def broadcast_progress(task_id: str, message: ProgressMessage) -> None:
    """Broadcast progress to all connected clients for a task."""
    connections = _active_connections.get(task_id, [])
    if not connections:
        return

    message_json = message.model_dump_json()
    disconnected = []

    for ws in connections:
        try:
            await ws.send_text(message_json)
        except Exception as e:
            logger.warning(f"Failed to send to WebSocket: {e}")
            disconnected.append(ws)

    # Remove disconnected clients
    for ws in disconnected:
        if ws in connections:
            connections.remove(ws)


def _sync_progress_callback(message: ProgressMessage) -> None:
    """Synchronous callback wrapper for async broadcast."""
    # This runs in the context of the event loop
    task_id = message.task_id
    connections = _active_connections.get(task_id, [])
    if not connections:
        return

    # Schedule the async broadcast
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_progress(task_id, message))
    except RuntimeError:
        # No running loop (shouldn't happen in FastAPI context)
        pass


@router.websocket("/api/ws/upload/{task_id}")
async def websocket_upload_progress(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for upload progress updates."""
    await websocket.accept()
    logger.info(f"WebSocket connected for task: {task_id}")

    # Add to active connections
    if task_id not in _active_connections:
        _active_connections[task_id] = []
    _active_connections[task_id].append(websocket)

    # Register callback
    task_manager.register_callback(task_id, _sync_progress_callback)

    try:
        # Send current task state
        task = task_manager.get_task(task_id)
        if task:
            message = ProgressMessage(
                task_id=task.id,
                status=task.status,
                step=task.step,
                progress=task.progress,
                message=task.message or "連線成功",
                chunk_count=task.chunk_count,
                error=task.error,
            )
            await websocket.send_text(message.model_dump_json())

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client messages (ping/pong, or control commands)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,  # 30 second timeout
                )

                # Handle control messages
                try:
                    msg = json.loads(data)
                    action = msg.get("action")

                    if action == "cancel":
                        task_manager.update_task(
                            task_id,
                            status=TaskStatus.CANCELLED,
                            message="使用者取消",
                        )
                    elif action == "ping":
                        await websocket.send_text(json.dumps({"action": "pong"}))

                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_text(json.dumps({"heartbeat": True}))
                except Exception:
                    break

            # Check if task is done
            task = task_manager.get_task(task_id)
            if task and task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ):
                # Send final status and close
                final_message = ProgressMessage(
                    task_id=task.id,
                    status=task.status,
                    step=task.step,
                    progress=task.progress,
                    message=task.message or "完成",
                    chunk_count=task.chunk_count,
                    error=task.error,
                )
                await websocket.send_text(final_message.model_dump_json())
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task: {task_id}")
    except Exception as e:
        logger.error(f"WebSocket error for task {task_id}: {e}")
    finally:
        # Cleanup
        if task_id in _active_connections:
            if websocket in _active_connections[task_id]:
                _active_connections[task_id].remove(websocket)
            if not _active_connections[task_id]:
                del _active_connections[task_id]

        task_manager.unregister_callback(task_id, _sync_progress_callback)


@router.websocket("/api/ws/tasks")
async def websocket_all_tasks(websocket: WebSocket):
    """WebSocket endpoint for all active task updates."""
    await websocket.accept()
    logger.info("WebSocket connected for all tasks")

    try:
        while True:
            # Send current active tasks
            tasks = task_manager.list_active_tasks()
            message = {
                "tasks": [
                    {
                        "task_id": t.id,
                        "filename": t.filename,
                        "status": t.status.value,
                        "progress": t.progress,
                        "step": t.step.value,
                        "updated_at": t.updated_at.isoformat(),
                    }
                    for t in tasks
                ],
                "active_count": len(tasks),
            }
            await websocket.send_text(json.dumps(message))

            # Wait before next update
            await asyncio.sleep(2.0)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for all tasks")
    except Exception as e:
        logger.error(f"WebSocket error for all tasks: {e}")
