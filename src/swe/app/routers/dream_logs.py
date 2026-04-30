# -*- coding: utf-8 -*-
"""Dream logs API router.

Provides REST API endpoints for dream optimization records.
"""
import json
import shutil
import logging
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/dream-logs", tags=["dream-logs"])
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------


class FileStats(BaseModel):
    """File statistics before and after optimization."""

    size_before: int
    size_after: int
    size_saved: int
    lines_before: int
    lines_after: int
    lines_removed: int
    backup_path: str


class DreamLogRecord(BaseModel):
    """Single dream optimization record."""

    id: str
    timestamp: str
    trigger: str  # "cron" or "manual"
    status: str  # "success", "failed", "rollback"
    files_optimized: list[str]
    file_stats: dict[str, FileStats]
    total_size_saved: int
    total_files_changed: int
    duration_ms: int
    model_used: str
    input_tokens: int
    output_tokens: int
    summary: str
    error: Optional[str] = None


class DreamLogsStats(BaseModel):
    """Aggregate statistics for dream optimization."""

    total_executions: int
    success_count: int
    failed_count: int
    total_size_saved: int
    total_files_changed: int
    avg_duration_ms: int = 0
    last_execution: Optional[str] = None


class DreamLogsResponse(BaseModel):
    """Response for listing dream logs."""

    records: list[DreamLogRecord]
    stats: DreamLogsStats
    total: int
    page: int
    page_size: int


class DiffResponse(BaseModel):
    """Response for file diff."""

    filename: str
    content_before: str
    content_after: str
    size_before: int
    size_after: int
    size_saved: int


class TriggerResponse(BaseModel):
    """Response for manual trigger."""

    success: bool
    message: str
    record_id: Optional[str] = None


class RollbackResponse(BaseModel):
    """Response for rollback operation."""

    success: bool
    message: str
    files_rolled_back: list[str]


class RollbackRequest(BaseModel):
    """Request body for rollback operation."""

    files: Optional[list[str]] = None


class BackupFileInfo(BaseModel):
    """Information about a backup file."""

    filename: str
    original_file: str
    record_id: str
    timestamp: str
    size: int
    created_at: str


class BackupListResponse(BaseModel):
    """Response for listing backup files."""

    files: list[BackupFileInfo]
    total_size: int
    total_files: int


class DeleteBackupResponse(BaseModel):
    """Response for deleting backup files."""

    success: bool
    message: str
    files_deleted: list[str]


class BackupContentResponse(BaseModel):
    """Response for backup file content preview."""

    filename: str
    content: str
    size: int
    original_file: str


class OrphanFileInfo(BaseModel):
    """Information about an orphan file."""

    filename: str
    size: int
    created_at: str
    modified_at: str
    path: str  # Relative path (filename only for workspace root files)
    full_path: str  # Absolute path


class OrphanFilesResponse(BaseModel):
    """Response for listing orphan files."""

    files: list[OrphanFileInfo]
    total_size: int
    total_files: int
    workspace_dir: str


class OrphanFileContentResponse(BaseModel):
    """Response for orphan file content preview."""

    filename: str
    content: str
    size: int
    file_type: str  # "text", "image", "binary", "error"
    is_loadable: bool
    error_message: Optional[str] = None


# Keep list - files and directories that should NOT be listed as orphan
KEEP_FILES = {
    "MEMORY.md",
    "AGENTS.md",
    "SOUL.md",
    "PROFILE.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "agent.json",
    "chats.json",
    "jobs.json",
    "token_usage.json",
    "dream_logs.json",
    "swe_file_metadata.json",
    "skill.json",
}

KEEP_DIRS = {
    "memory",
    "sessions",
    "backup",
    "skills",
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

DREAM_LOGS_FILE = "dream_logs.json"
BACKUP_DIR = "backup"

# Image file extensions for preview
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


def _get_file_type(filepath: Path) -> str:
    """Determine file type based on extension."""
    ext = filepath.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".py",
        ".sh",
        ".log",
        ".toml",
    }:
        return "text"
    return "binary"


def _get_agent_id(request: Request) -> str:
    """Get agent_id from request header or default."""
    return request.headers.get("X-Agent-Id", "default")


def _get_workspace_dir(request: Request) -> Path:
    """Get agent-level workspace directory from request state.

    Returns the agent workspace directory (e.g., /root/.swe/{tenant}/workspaces/{agent})
    where dream_logs.json is stored.
    """
    workspace = getattr(request.state, "workspace", None)
    if workspace is None:
        raise HTTPException(
            status_code=503,
            detail="Tenant workspace not available",
        )
    # workspace is TenantWorkspaceContext with tenant-level directory
    # Add workspaces/{agent_id} to get agent-level directory
    tenant_dir = workspace.workspace_dir
    agent_id = _get_agent_id(request)
    return tenant_dir / "workspaces" / agent_id


def _get_tenant_id(request: Request) -> str:
    """Get tenant_id from request header or default."""
    return request.headers.get("X-Tenant-Id", "default")


def _parse_backup_filename(filename: str) -> str:
    """Parse backup filename to get original file name.

    Args:
        filename: Backup filename like "memory_backup_20260428_104646.md"

    Returns:
        Original filename like "MEMORY.md"
    """
    stem = Path(filename).stem
    if "_backup_" in stem:
        prefix = stem.split("_backup_")[0]
        return prefix.upper() + ".md"
    # Fallback: just capitalize the stem
    return stem.replace("_backup_", "").replace("_", "").upper() + ".md"


def _load_dream_logs(workspace_dir: Path) -> dict:
    """Load dream_logs.json from workspace directory."""
    log_path = workspace_dir / DREAM_LOGS_FILE
    if not log_path.exists():
        return {
            "records": [],
            "stats": {
                "total_executions": 0,
                "success_count": 0,
                "failed_count": 0,
                "total_size_saved": 0,
                "total_files_changed": 0,
                "last_execution": None,
            },
        }
    try:
        with open(log_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load dream logs: {e}")
        return {
            "records": [],
            "stats": {
                "total_executions": 0,
                "success_count": 0,
                "failed_count": 0,
                "total_size_saved": 0,
                "total_files_changed": 0,
                "last_execution": None,
            },
        }


def _save_dream_logs(workspace_dir: Path, data: dict) -> None:
    """Save dream_logs.json to workspace directory."""
    log_path = workspace_dir / DREAM_LOGS_FILE
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save dream logs: {e}")


def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable format."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


# ------------------------------------------------------------------
# API endpoints
# ------------------------------------------------------------------


@router.get("", response_model=DreamLogsResponse)
async def list_dream_logs(
    request: Request,
    page: int = 1,
    page_size: int = 20,
) -> DreamLogsResponse:
    """List dream optimization records.

    Args:
        request: FastAPI request.
        page: Page number (1-indexed).
        page_size: Number of records per page.

    Returns:
        DreamLogsResponse with records and stats.
    """
    tenant_id = _get_tenant_id(request)
    workspace_dir = _get_workspace_dir(request)

    data = _load_dream_logs(workspace_dir)
    records = data.get("records", [])
    stats = data.get("stats", {})

    # Calculate avg_duration_ms
    total_executions = stats.get("total_executions", 0)
    total_duration_ms = stats.get("total_duration_ms", 0)
    stats["avg_duration_ms"] = (
        total_duration_ms // total_executions if total_executions > 0 else 0
    )

    # Sort records by timestamp (most recent first)
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

    # Paginate records
    total = len(records)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_records = records[start_idx:end_idx]

    # Convert to response models
    record_models = []
    for r in paginated_records:
        file_stats_dict = {}
        for filename, fs in r.get("file_stats", {}).items():
            file_stats_dict[filename] = FileStats(**fs)
        record_models.append(
            DreamLogRecord(
                id=r["id"],
                timestamp=r["timestamp"],
                trigger=r["trigger"],
                status=r["status"],
                files_optimized=r.get("files_optimized", []),
                file_stats=file_stats_dict,
                total_size_saved=r.get("total_size_saved", 0),
                total_files_changed=r.get("total_files_changed", 0),
                duration_ms=r.get("duration_ms", 0),
                model_used=r.get("model_used", ""),
                input_tokens=r.get("input_tokens", 0),
                output_tokens=r.get("output_tokens", 0),
                summary=r.get("summary", ""),
                error=r.get("error"),
            ),
        )

    return DreamLogsResponse(
        records=record_models,
        stats=DreamLogsStats(**stats),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DreamLogsStats)
async def get_dream_logs_stats(request: Request) -> DreamLogsStats:
    """Get aggregate statistics for dream optimization.

    Args:
        request: FastAPI request.

    Returns:
        DreamLogsStats with aggregate stats.
    """
    tenant_id = _get_tenant_id(request)
    workspace_dir = _get_workspace_dir(request)

    data = _load_dream_logs(workspace_dir)
    stats = data.get("stats", {})

    # Calculate avg_duration_ms
    total_executions = stats.get("total_executions", 0)
    total_duration_ms = stats.get("total_duration_ms", 0)
    avg_duration_ms = (
        total_duration_ms // total_executions if total_executions > 0 else 0
    )
    stats["avg_duration_ms"] = avg_duration_ms

    return DreamLogsStats(**stats)


@router.get("/diff/{record_id}/{filename}", response_model=DiffResponse)
async def get_file_diff(
    request: Request,
    record_id: str,
    filename: str,
) -> DiffResponse:
    """Get before/after diff for a specific file.

    Args:
        request: FastAPI request.
        record_id: Dream optimization record ID.
        filename: File name (e.g., "MEMORY.md").

    Returns:
        DiffResponse with before/after content.
    """
    tenant_id = _get_tenant_id(request)
    workspace_dir = _get_workspace_dir(request)

    data = _load_dream_logs(workspace_dir)
    records = data.get("records", [])

    # Find the record
    record = None
    for r in records:
        if r["id"] == record_id:
            record = r
            break

    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    file_stats = record.get("file_stats", {}).get(filename)
    if not file_stats:
        raise HTTPException(status_code=404, detail="File stats not found")

    backup_path = workspace_dir / file_stats["backup_path"]
    current_path = workspace_dir / filename

    # Read before content (backup)
    content_before = ""
    if backup_path.exists():
        try:
            content_before = backup_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read backup file: {e}")

    # Read after content (current)
    content_after = ""
    if current_path.exists():
        try:
            content_after = current_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read current file: {e}")

    return DiffResponse(
        filename=filename,
        content_before=content_before,
        content_after=content_after,
        size_before=file_stats["size_before"],
        size_after=file_stats["size_after"],
        size_saved=file_stats["size_saved"],
    )


@router.post("/rollback/{record_id}", response_model=RollbackResponse)
async def rollback_dream_optimization(
    request: Request,
    record_id: str,
    body: Optional[RollbackRequest] = None,
) -> RollbackResponse:
    """Rollback specific files or all files from a dream optimization.

    Args:
        request: FastAPI request.
        record_id: Dream optimization record ID.
        body: Optional request body with list of files to rollback. If None or empty, rollback all.

    Returns:
        RollbackResponse with rollback status.
    """
    tenant_id = _get_tenant_id(request)
    workspace_dir = _get_workspace_dir(request)

    data = _load_dream_logs(workspace_dir)
    records = data.get("records", [])

    # Find the record
    record_idx = None
    record = None
    for i, r in enumerate(records):
        if r["id"] == record_id:
            record_idx = i
            record = r
            break

    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Determine which files to rollback
    file_stats = record.get("file_stats", {})
    files_to_rollback = body.files if body and body.files else None
    if files_to_rollback:
        rollback_files = {
            f: file_stats[f] for f in files_to_rollback if f in file_stats
        }
    else:
        rollback_files = file_stats

    if not rollback_files:
        return RollbackResponse(
            success=False,
            message="No files to rollback",
            files_rolled_back=[],
        )

    rolled_back_files = []
    for filename, stats in rollback_files.items():
        backup_path = workspace_dir / stats["backup_path"]
        current_path = workspace_dir / filename

        if not backup_path.exists():
            logger.warning(f"Backup file not found: {backup_path}")
            continue

        try:
            shutil.copyfile(backup_path, current_path)
            rolled_back_files.append(filename)
            logger.info(f"Rolled back {filename} from {backup_path}")
        except Exception as e:
            logger.error(f"Failed to rollback {filename}: {e}")

    # Update record status
    if record_idx is not None and rolled_back_files:
        records[record_idx]["status"] = "rollback"
        records[record_idx]["rollback_timestamp"] = datetime.now().isoformat()
        records[record_idx]["rollback_files"] = rolled_back_files
        _save_dream_logs(workspace_dir, data)

    return RollbackResponse(
        success=bool(rolled_back_files),
        message=f"Rolled back {len(rolled_back_files)} files",
        files_rolled_back=rolled_back_files,
    )


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_dream_optimization(request: Request) -> TriggerResponse:
    """Manually trigger dream optimization (async, returns immediately).

    Args:
        request: FastAPI request.

    Returns:
        TriggerResponse with trigger status.
    """
    import asyncio

    tenant_id = _get_tenant_id(request)

    # Get agent_id from request or use default
    agent_id = request.headers.get("X-Agent-Id", "default")

    try:
        # Get MultiAgentManager from app state
        manager = getattr(request.app.state, "multi_agent_manager", None)
        if not manager:
            return TriggerResponse(
                success=False,
                message="MultiAgentManager not initialized",
            )

        workspace = await manager.get_agent(agent_id, tenant_id=tenant_id)

        if not workspace:
            return TriggerResponse(
                success=False,
                message=f"Workspace not found for agent {agent_id}",
            )

        runner = workspace.runner
        if not runner or not runner.memory_manager:
            return TriggerResponse(
                success=False,
                message="Memory manager not available",
            )

        # Execute dream asynchronously in background (fire and forget)
        asyncio.create_task(
            runner.memory_manager.dream_memory(
                tenant_id=tenant_id,
                trigger="manual",
            ),
        )

        return TriggerResponse(
            success=True,
            message="Dream optimization started in background",
            record_id=None,  # Will be available after execution completes
        )

    except Exception as e:
        logger.error(f"Failed to trigger dream optimization: {e}")
        return TriggerResponse(
            success=False,
            message=f"Failed to trigger dream optimization: {str(e)}",
        )


# ------------------------------------------------------------------
# Backup endpoints
# ------------------------------------------------------------------


@router.get("/backups", response_model=BackupListResponse)
async def list_backup_files(request: Request) -> BackupListResponse:
    """List all backup files in the backup directory."""
    tenant_id = _get_tenant_id(request)
    workspace_dir = _get_workspace_dir(request)
    backup_dir = workspace_dir / BACKUP_DIR

    if not backup_dir.exists():
        return BackupListResponse(files=[], total_size=0, total_files=0)

    data = _load_dream_logs(workspace_dir)
    records = data.get("records", [])

    backup_info_map: dict[str, dict] = {}
    for record in records:
        record_id = record.get("id", "")
        timestamp = record.get("timestamp", "")
        for filename, stats in record.get("file_stats", {}).items():
            backup_path = stats.get("backup_path", "")
            if backup_path:
                backup_info_map[backup_path] = {
                    "original_file": filename,
                    "record_id": record_id,
                    "timestamp": timestamp,
                }

    backup_files: list[BackupFileInfo] = []
    total_size = 0

    for backup_file in backup_dir.glob("*.md"):
        try:
            stat = backup_file.stat()
            backup_path_rel = str(backup_file.relative_to(workspace_dir))
            info = backup_info_map.get(backup_path_rel, {})
            backup_files.append(
                BackupFileInfo(
                    filename=backup_file.name,
                    original_file=info.get(
                        "original_file",
                        _parse_backup_filename(backup_file.name),
                    ),
                    record_id=info.get("record_id", ""),
                    timestamp=info.get("timestamp", ""),
                    size=stat.st_size,
                    created_at=datetime.fromtimestamp(
                        stat.st_ctime,
                    ).isoformat(),
                ),
            )
            total_size += stat.st_size
        except Exception as e:
            logger.error(f"Failed to read backup file {backup_file}: {e}")

    backup_files.sort(key=lambda x: x.created_at, reverse=True)
    return BackupListResponse(
        files=backup_files,
        total_size=total_size,
        total_files=len(backup_files),
    )


@router.delete("/backups", response_model=DeleteBackupResponse)
async def delete_all_backups(request: Request) -> DeleteBackupResponse:
    """Delete all backup files."""
    tenant_id = _get_tenant_id(request)
    workspace_dir = _get_workspace_dir(request)
    backup_dir = workspace_dir / BACKUP_DIR

    if not backup_dir.exists():
        return DeleteBackupResponse(
            success=True,
            message="No backup directory found",
            files_deleted=[],
        )

    deleted_files: list[str] = []
    for backup_file in backup_dir.glob("*.md"):
        try:
            backup_file.unlink()
            deleted_files.append(backup_file.name)
            logger.info(f"Deleted backup file: {backup_file}")
        except Exception as e:
            logger.error(f"Failed to delete backup file {backup_file}: {e}")

    return DeleteBackupResponse(
        success=True,
        message=f"Deleted {len(deleted_files)} backup files",
        files_deleted=deleted_files,
    )


@router.delete("/backups/{filename}", response_model=DeleteBackupResponse)
async def delete_single_backup(
    request: Request,
    filename: str,
) -> DeleteBackupResponse:
    """Delete a specific backup file."""
    tenant_id = _get_tenant_id(request)
    workspace_dir = _get_workspace_dir(request)
    backup_file = workspace_dir / BACKUP_DIR / filename

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        backup_file.unlink()
        logger.info(f"Deleted backup file: {backup_file}")
        return DeleteBackupResponse(
            success=True,
            message=f"Deleted backup file: {filename}",
            files_deleted=[filename],
        )
    except Exception as e:
        logger.error(f"Failed to delete backup file {backup_file}: {e}")
        return DeleteBackupResponse(
            success=False,
            message=f"Failed to delete backup file: {str(e)}",
            files_deleted=[],
        )


@router.get(
    "/backups/{filename}/content",
    response_model=BackupContentResponse,
)
async def get_backup_content(
    request: Request,
    filename: str,
) -> BackupContentResponse:
    """Get content of a specific backup file for preview."""
    workspace_dir = _get_workspace_dir(request)
    backup_file = workspace_dir / BACKUP_DIR / filename

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        content = backup_file.read_text(encoding="utf-8")
        stat = backup_file.stat()

        # Find original file from dream logs
        data = _load_dream_logs(workspace_dir)
        records = data.get("records", [])
        original_file = ""
        for record in records:
            for fname, stats in record.get("file_stats", {}).items():
                if stats.get("backup_path", "").endswith(filename):
                    original_file = fname
                    break
            if original_file:
                break

        if not original_file:
            # Guess from filename pattern
            original_file = _parse_backup_filename(filename)

        return BackupContentResponse(
            filename=filename,
            content=content,
            size=stat.st_size,
            original_file=original_file,
        )
    except Exception as e:
        logger.error(f"Failed to read backup file {backup_file}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read backup file: {str(e)}",
        )


# ------------------------------------------------------------------
# Orphan files endpoints
# ------------------------------------------------------------------


def _scan_orphan_files(workspace_dir: Path) -> list[OrphanFileInfo]:
    """Scan workspace directory for orphan files.

    Returns files that are NOT in the keep list and NOT hidden files.
    Also scans static directory which is considered cleanup target.
    """
    orphan_files: list[OrphanFileInfo] = []

    if not workspace_dir.exists():
        return orphan_files

    def scan_directory(dir_path: Path, relative_base: Path) -> None:
        """Recursively scan a directory for orphan files."""
        try:
            for item in dir_path.iterdir():
                # Skip hidden files (starting with .)
                if item.name.startswith("."):
                    continue

                # Skip directories in keep list (at root level only)
                if item.is_dir():
                    if item.name in KEEP_DIRS and dir_path == workspace_dir:
                        continue
                    # Recursively scan subdirectories (including static)
                    scan_directory(item, relative_base)
                    continue

                # Skip files in keep list (at root level only)
                if item.is_file() and dir_path == workspace_dir:
                    if item.name in KEEP_FILES:
                        continue

                # Process files
                if item.is_file():
                    try:
                        stat = item.stat()
                        relative_path = str(item.relative_to(relative_base))
                        orphan_files.append(
                            OrphanFileInfo(
                                filename=item.name,
                                size=stat.st_size,
                                created_at=datetime.fromtimestamp(
                                    stat.st_ctime,
                                ).isoformat(),
                                modified_at=datetime.fromtimestamp(
                                    stat.st_mtime,
                                ).isoformat(),
                                path=relative_path,  # Relative to workspace_dir
                                full_path=str(item),  # Absolute path
                            ),
                        )
                    except Exception as e:
                        logger.error(f"Failed to read file {item}: {e}")
        except Exception as e:
            logger.error(f"Failed to scan directory {dir_path}: {e}")

    # Start scanning from workspace root
    scan_directory(workspace_dir, workspace_dir)

    # Sort by modified time (most recent first)
    orphan_files.sort(key=lambda x: x.modified_at, reverse=True)
    return orphan_files


@router.get("/orphan-files", response_model=OrphanFilesResponse)
async def list_orphan_files(request: Request) -> OrphanFilesResponse:
    """List orphan files in workspace directory.

    Orphan files are files that are NOT in the standard keep list
    (core config files, system data files, and standard directories).
    """
    workspace_dir = _get_workspace_dir(request)
    orphan_files = _scan_orphan_files(workspace_dir)

    total_size = sum(f.size for f in orphan_files)
    return OrphanFilesResponse(
        files=orphan_files,
        total_size=total_size,
        total_files=len(orphan_files),
        workspace_dir=str(workspace_dir),
    )


@router.get(
    "/orphan-files/{filepath:path}/content",
    response_model=OrphanFileContentResponse,
)
async def get_orphan_file_content(
    request: Request,
    filepath: str,
) -> OrphanFileContentResponse:
    """Get content of an orphan file for preview."""
    workspace_dir = _get_workspace_dir(request)
    file_path = workspace_dir / filepath

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Security check: ensure file is within workspace_dir
    try:
        file_path.resolve().relative_to(workspace_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    stat = file_path.stat()
    file_type = _get_file_type(file_path)

    try:
        if file_type == "image":
            # Read image as base64
            content_bytes = file_path.read_bytes()
            content = base64.b64encode(content_bytes).decode("utf-8")
            return OrphanFileContentResponse(
                filename=filepath,
                content=content,
                size=stat.st_size,
                file_type="image",
                is_loadable=True,
            )
        elif file_type == "text":
            # Read text file
            content = file_path.read_text(encoding="utf-8")
            return OrphanFileContentResponse(
                filename=filepath,
                content=content,
                size=stat.st_size,
                file_type="text",
                is_loadable=True,
            )
        else:
            # Binary file - cannot preview
            return OrphanFileContentResponse(
                filename=filepath,
                content="",
                size=stat.st_size,
                file_type="binary",
                is_loadable=False,
                error_message="Binary file cannot be previewed",
            )
    except UnicodeDecodeError:
        # Text file with non-UTF8 encoding
        return OrphanFileContentResponse(
            filename=filepath,
            content="",
            size=stat.st_size,
            file_type="text",
            is_loadable=False,
            error_message="File encoding is not UTF-8, cannot preview",
        )
    except Exception as e:
        logger.error(f"Failed to read orphan file {file_path}: {e}")
        return OrphanFileContentResponse(
            filename=filepath,
            content="",
            size=stat.st_size,
            file_type="error",
            is_loadable=False,
            error_message=f"Failed to read file: {str(e)}",
        )


@router.delete(
    "/orphan-files/{filepath:path}",
    response_model=DeleteBackupResponse,
)
async def delete_orphan_file(
    request: Request,
    filepath: str,
) -> DeleteBackupResponse:
    """Delete an orphan file."""
    workspace_dir = _get_workspace_dir(request)
    file_path = workspace_dir / filepath

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Security check: ensure file is within workspace_dir
    try:
        file_path.resolve().relative_to(workspace_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    # Extra check: ensure file is NOT in keep list
    if file_path.name in KEEP_FILES:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete protected file",
        )

    # Extra check: ensure file is NOT hidden (starting with .)
    if file_path.name.startswith("."):
        raise HTTPException(
            status_code=403,
            detail="Cannot delete hidden file",
        )

    try:
        file_path.unlink()
        logger.info(f"Deleted orphan file: {file_path}")
        return DeleteBackupResponse(
            success=True,
            message=f"Deleted file: {filepath}",
            files_deleted=[filepath],
        )
    except Exception as e:
        logger.error(f"Failed to delete orphan file {file_path}: {e}")
        return DeleteBackupResponse(
            success=False,
            message=f"Failed to delete file: {str(e)}",
            files_deleted=[],
        )
