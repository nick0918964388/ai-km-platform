"""Backup service for Qdrant vector database."""
import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import requests

from app.config import get_settings
from app.models.schemas import BackupRecord, BackupStatus
from app.services.vector_store import TEXT_COLLECTION, IMAGE_COLLECTION, get_client

logger = logging.getLogger(__name__)

# Backup manifest file
MANIFEST_FILE = "manifest.json"


def _get_backup_dir() -> Path:
    """Get backup directory path."""
    settings = get_settings()
    backup_dir = Path(settings.backup_dir) / "qdrant"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _load_manifest() -> dict:
    """Load backup manifest."""
    manifest_path = _get_backup_dir() / MANIFEST_FILE
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            return json.load(f)
    return {"backups": []}


def _save_manifest(manifest: dict) -> None:
    """Save backup manifest."""
    manifest_path = _get_backup_dir() / MANIFEST_FILE
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)


def _get_qdrant_api_url() -> str:
    """Get Qdrant API base URL."""
    settings = get_settings()
    return settings.qdrant_url.rstrip("/")


def list_backups() -> list[BackupRecord]:
    """List all backup records."""
    manifest = _load_manifest()
    backups = []
    for record in manifest.get("backups", []):
        try:
            backups.append(BackupRecord(**record))
        except Exception as e:
            logger.warning(f"Invalid backup record: {e}")
    return sorted(backups, key=lambda x: x.created_at, reverse=True)


def get_backup(backup_id: str) -> Optional[BackupRecord]:
    """Get a specific backup record."""
    manifest = _load_manifest()
    for record in manifest.get("backups", []):
        if record.get("id") == backup_id:
            return BackupRecord(**record)
    return None


def create_backup(collection_name: str = TEXT_COLLECTION) -> BackupRecord:
    """
    Create a backup of a Qdrant collection.

    Uses Qdrant's snapshot API to create a consistent backup.
    """
    backup_id = str(uuid.uuid4())
    timestamp = datetime.utcnow()
    snapshot_name = f"{collection_name}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

    # Create initial record
    record = BackupRecord(
        id=backup_id,
        collection_name=collection_name,
        snapshot_name=snapshot_name,
        status=BackupStatus.PENDING,
        created_at=timestamp,
    )

    # Add to manifest
    manifest = _load_manifest()
    manifest["backups"].append(record.model_dump())
    _save_manifest(manifest)

    try:
        # Update status to in progress
        record.status = BackupStatus.IN_PROGRESS
        _update_backup_record(record)

        # Get collection stats
        client = get_client()
        try:
            collection_info = client.get_collection(collection_name)
            vector_count = collection_info.points_count
        except Exception:
            vector_count = 0

        # Create snapshot via Qdrant REST API
        qdrant_url = _get_qdrant_api_url()
        response = requests.post(
            f"{qdrant_url}/collections/{collection_name}/snapshots",
            timeout=300,  # 5 minute timeout for large collections
        )

        if response.status_code != 200:
            raise Exception(f"Snapshot creation failed: {response.text}")

        result = response.json().get("result", {})
        snapshot_name = result.get("name", snapshot_name)

        # Download snapshot to backup directory
        backup_dir = _get_backup_dir()
        snapshot_path = backup_dir / f"{snapshot_name}.snapshot"

        download_url = f"{qdrant_url}/collections/{collection_name}/snapshots/{snapshot_name}"
        download_response = requests.get(download_url, stream=True, timeout=600)

        if download_response.status_code == 200:
            with open(snapshot_path, "wb") as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            file_size = snapshot_path.stat().st_size
        else:
            file_size = 0

        # Update record with success
        record.status = BackupStatus.COMPLETED
        record.completed_at = datetime.utcnow()
        record.snapshot_name = snapshot_name
        record.file_path = str(snapshot_path)
        record.file_size = file_size
        record.vector_count = vector_count
        _update_backup_record(record)

        logger.info(
            f"Backup completed: {backup_id}, collection={collection_name}, "
            f"vectors={vector_count}, size={file_size}"
        )

    except Exception as e:
        # Update record with failure
        record.status = BackupStatus.FAILED
        record.error_message = str(e)
        record.completed_at = datetime.utcnow()
        _update_backup_record(record)
        logger.error(f"Backup failed: {backup_id}, error={e}")

    return record


def restore_backup(backup_id: str) -> BackupRecord:
    """
    Restore a collection from a backup.

    Uses Qdrant's snapshot recovery API.
    """
    record = get_backup(backup_id)
    if not record:
        raise ValueError(f"Backup not found: {backup_id}")

    if record.status != BackupStatus.COMPLETED:
        raise ValueError(f"Cannot restore incomplete backup: {record.status}")

    snapshot_path = Path(record.file_path) if record.file_path else None
    if not snapshot_path or not snapshot_path.exists():
        raise ValueError(f"Snapshot file not found: {record.file_path}")

    try:
        qdrant_url = _get_qdrant_api_url()

        # Upload snapshot to Qdrant
        with open(snapshot_path, "rb") as f:
            files = {"snapshot": (snapshot_path.name, f)}
            response = requests.post(
                f"{qdrant_url}/collections/{record.collection_name}/snapshots/upload",
                files=files,
                timeout=600,
            )

        if response.status_code not in (200, 201):
            raise Exception(f"Snapshot upload failed: {response.text}")

        # Recover from snapshot
        response = requests.put(
            f"{qdrant_url}/collections/{record.collection_name}/snapshots/recover",
            json={"location": f"file://{snapshot_path}"},
            timeout=600,
        )

        if response.status_code not in (200, 201):
            raise Exception(f"Recovery failed: {response.text}")

        logger.info(f"Restore completed: {backup_id}, collection={record.collection_name}")
        return record

    except Exception as e:
        logger.error(f"Restore failed: {backup_id}, error={e}")
        raise


def delete_backup(backup_id: str) -> bool:
    """Delete a backup record and its snapshot file."""
    record = get_backup(backup_id)
    if not record:
        return False

    # Delete snapshot file if exists
    if record.file_path:
        try:
            Path(record.file_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Failed to delete snapshot file: {e}")

    # Remove from manifest
    manifest = _load_manifest()
    manifest["backups"] = [
        b for b in manifest["backups"] if b.get("id") != backup_id
    ]
    _save_manifest(manifest)

    logger.info(f"Backup deleted: {backup_id}")
    return True


def get_backup_file_path(backup_id: str) -> Optional[Path]:
    """Get the file path for a backup snapshot."""
    record = get_backup(backup_id)
    if not record or not record.file_path:
        return None

    path = Path(record.file_path)
    if not path.exists():
        return None

    return path


def _update_backup_record(record: BackupRecord) -> None:
    """Update a backup record in the manifest."""
    manifest = _load_manifest()
    for i, existing in enumerate(manifest["backups"]):
        if existing.get("id") == record.id:
            manifest["backups"][i] = record.model_dump()
            break
    _save_manifest(manifest)
