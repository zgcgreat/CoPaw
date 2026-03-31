# -*- coding: utf-8 -*-
from __future__ import annotations

import contextvars
import os
from pathlib import Path

# Default working directory (used when no user_id is specified)
DEFAULT_WORKING_DIR = (
    Path(os.environ.get("COPAW_WORKING_DIR", "~/.copaw"))
    .expanduser()
    .resolve()
)

# Default secret directory (used when no user_id is specified)
DEFAULT_SECRET_DIR = (
    Path(os.environ.get("COPAW_SECRET_DIR", f"{DEFAULT_WORKING_DIR}.secret"))
    .expanduser()
    .resolve()
)

# Runtime state for user-specific directory (for single-user mode / daemon mode)
_current_user_id: str | None = None
_runtime_working_dir: Path = DEFAULT_WORKING_DIR
_runtime_secret_dir: Path = DEFAULT_SECRET_DIR

# Context variables for request-scoped user isolation (multi-user concurrent mode)
_request_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_user_id",
    default=None,
)

# Request-scoped directory cache (computed per-request)
_request_working_dir: contextvars.ContextVar[
    Path | None
] = contextvars.ContextVar("request_working_dir", default=None)
_request_secret_dir: contextvars.ContextVar[
    Path | None
] = contextvars.ContextVar("request_secret_dir", default=None)


def get_working_dir(user_id: str | None = None) -> Path:
    """获取工作目录，支持用户隔离。

    Args:
        user_id: 用户标识，None 表示使用当前运行时设置

    Returns:
        工作目录路径
    """
    if user_id is None:
        return _runtime_working_dir
    return DEFAULT_WORKING_DIR / user_id


def get_secret_dir(user_id: str | None = None) -> Path:
    """获取敏感信息目录，支持用户隔离。

    Args:
        user_id: 用户标识，None 表示使用当前运行时设置

    Returns:
        敏感信息目录路径
    """
    if user_id is None:
        return _runtime_secret_dir
    return DEFAULT_SECRET_DIR / user_id


def set_current_user(user_id: str | None) -> None:
    """设置当前用户标识。

    Args:
        user_id: 用户标识，None 表示使用默认目录
    """
    global _current_user_id, _runtime_working_dir, _runtime_secret_dir
    _current_user_id = user_id
    if user_id:
        _runtime_working_dir = DEFAULT_WORKING_DIR / user_id
        _runtime_secret_dir = DEFAULT_SECRET_DIR / user_id
    else:
        _runtime_working_dir = DEFAULT_WORKING_DIR
        _runtime_secret_dir = DEFAULT_SECRET_DIR


def get_runtime_working_dir() -> Path:
    """获取运行时工作目录（考虑 set_current_user 后的值）。"""
    return _runtime_working_dir


def get_runtime_secret_dir() -> Path:
    """获取运行时敏感目录（考虑 set_current_user 后的值）。"""
    return _runtime_secret_dir


def get_current_user_id() -> str | None:
    """获取当前用户标识。"""
    return _current_user_id


# ============================================================================
# Request-scoped directory access (for multi-user concurrent mode)
# ============================================================================


def set_request_user_id(user_id: str | None) -> tuple[contextvars.Token, contextvars.Token, contextvars.Token]:
    """设置请求级用户 ID，返回 tokens 用于恢复。

    Args:
        user_id: 用户标识

    Returns:
        三个 contextvars.Token 分别用于恢复 user_id、working_dir、secret_dir
    """
    token_id = _request_user_id.set(user_id)
    if user_id:
        token_wd = _request_working_dir.set(DEFAULT_WORKING_DIR / user_id)
        token_sd = _request_secret_dir.set(DEFAULT_SECRET_DIR / user_id)
    else:
        token_wd = _request_working_dir.set(DEFAULT_WORKING_DIR)
        token_sd = _request_secret_dir.set(DEFAULT_SECRET_DIR)
    return token_id, token_wd, token_sd


def reset_request_user_id(
    token_id: contextvars.Token,
    token_wd: contextvars.Token,
    token_sd: contextvars.Token,
) -> None:
    """恢复之前的用户 ID 上下文。

    Args:
        token_id: set_request_user_id 返回的 user_id token
        token_wd: set_request_user_id 返回的 working_dir token
        token_sd: set_request_user_id 返回的 secret_dir token
    """
    _request_user_id.reset(token_id)
    _request_working_dir.reset(token_wd)
    _request_secret_dir.reset(token_sd)


def get_request_user_id() -> str | None:
    """获取当前请求的用户 ID。"""
    return _request_user_id.get()


def get_request_working_dir() -> Path:
    """获取请求级工作目录，回退到运行时目录。

    在 Channel 处理多用户并发请求时，返回当前请求 user_id 对应的目录。
    在无请求上下文的场景中（如 CLI、Daemon），回退到 _runtime_working_dir。
    """
    wd = _request_working_dir.get()
    return wd if wd is not None else _runtime_working_dir


def get_request_secret_dir() -> Path:
    """获取请求级敏感目录，回退到运行时目录。

    在 Channel 处理多用户并发请求时，返回当前请求 user_id 对应的目录。
    在无请求上下文的场景中（如 CLI、Daemon），回退到 _runtime_secret_dir。
    """
    sd = _request_secret_dir.get()
    return sd if sd is not None else _runtime_secret_dir


# ============================================================================
# Module-level constants (now use request-scoped accessors)
# ============================================================================
WORKING_DIR = DEFAULT_WORKING_DIR
SECRET_DIR = DEFAULT_SECRET_DIR

JOBS_FILE = os.environ.get("COPAW_JOBS_FILE", "jobs.json")

CHATS_FILE = os.environ.get("COPAW_CHATS_FILE", "chats.json")

CONFIG_FILE = os.environ.get("COPAW_CONFIG_FILE", "config.json")

HEARTBEAT_FILE = os.environ.get("COPAW_HEARTBEAT_FILE", "HEARTBEAT.md")
HEARTBEAT_DEFAULT_EVERY = "6h"
HEARTBEAT_DEFAULT_TARGET = "main"
HEARTBEAT_TARGET_LAST = "last"

# Env key for app log level (used by CLI and app load for reload child).
LOG_LEVEL_ENV = "COPAW_LOG_LEVEL"

# Env to indicate running inside a container (e.g. Docker). Set to 1/true/yes.
RUNNING_IN_CONTAINER = os.environ.get("COPAW_RUNNING_IN_CONTAINER", "false")

# Timeout in seconds for checking if a provider is reachable.
# TODO: add a module to parse and validate env vars
try:
    MODEL_PROVIDER_CHECK_TIMEOUT = float(
        os.environ.get("COPAW_MODEL_PROVIDER_CHECK_TIMEOUT", "5.0"),
    )
except (TypeError, ValueError):
    MODEL_PROVIDER_CHECK_TIMEOUT = 5.0

# Playwright: use system Chromium when set (e.g. in Docker).
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"

# When True, expose /docs, /redoc, /openapi.json
# (dev only; keep False in prod).
DOCS_ENABLED = os.environ.get("COPAW_OPENAPI_DOCS", "false").lower() in (
    "true",
    "1",
    "yes",
)

# Skills directories - use function accessors for request-scoped access
# Note: These are now functions to support request-scoped directory resolution


def get_active_skills_dir() -> Path:
    """Get active skills directory for current request."""
    return get_request_working_dir() / "active_skills"


def get_customized_skills_dir() -> Path:
    """Get customized skills directory for current request."""
    return get_request_working_dir() / "customized_skills"


def get_memory_dir() -> Path:
    """Get memory directory for current request."""
    return get_request_working_dir() / "memory"


def get_custom_channels_dir() -> Path:
    """Get custom channel modules directory for current request."""
    return get_request_working_dir() / "custom_channels"


def get_models_dir() -> Path:
    """Get local models directory for current request."""
    return get_request_working_dir() / "models"


def list_all_user_ids() -> list[str]:
    """Scan and return all existing user IDs.

    Scans the ~/.copaw/ directory and returns all directory names
    that contain a valid config.json file.

    Returns:
        List of user IDs
    """
    user_ids = []
    if not DEFAULT_WORKING_DIR.exists():
        return user_ids

    for entry in DEFAULT_WORKING_DIR.iterdir():
        if entry.is_dir() and (entry / "config.json").exists():
            user_ids.append(entry.name)

    return user_ids


# Backward compatibility: module-level variables that resolve at access time
# These will use the request-scoped directory when in a request context
ACTIVE_SKILLS_DIR = None  # Use get_active_skills_dir() instead
CUSTOMIZED_SKILLS_DIR = None  # Use get_customized_skills_dir() instead
MEMORY_DIR = None  # Use get_memory_dir() instead
CUSTOM_CHANNELS_DIR = None  # Use get_custom_channels_dir() instead
MODELS_DIR = None  # Use get_models_dir() instead

# Memory compaction configuration
MEMORY_COMPACT_KEEP_RECENT = int(
    os.environ.get("COPAW_MEMORY_COMPACT_KEEP_RECENT", "3"),
)

MEMORY_COMPACT_RATIO = float(
    os.environ.get("COPAW_MEMORY_COMPACT_RATIO", "0.7"),
)

DASHSCOPE_BASE_URL = os.environ.get(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# CORS configuration — comma-separated list of allowed origins for dev mode.
# Example: COPAW_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
# When unset, CORS middleware is not applied.
CORS_ORIGINS = os.environ.get("COPAW_CORS_ORIGINS", "*").strip()

# ============================================================================
# Redis configuration
# ============================================================================
REDIS_HOST = os.environ.get("COPAW_REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("COPAW_REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("COPAW_REDIS_DB", "0"))
REDIS_PASSWORD = os.environ.get("COPAW_REDIS_PASSWORD", "")
REDIS_SSL = os.environ.get("COPAW_REDIS_SSL", "false").lower() in (
    "true",
    "1",
    "yes",
)

# ============================================================================
# Redis Cluster configuration (for multi-instance with Redlock)
# ============================================================================
REDIS_MODE = os.environ.get(
    "COPAW_REDIS_MODE", "single"
)  # "single" or "cluster"
REDIS_SEEDS = os.environ.get("COPAW_REDIS_SEEDS", "localhost:6379")


def get_redis_seeds() -> list[str]:
    """Parse REDIS_SEEDS env var into list of host:port strings."""
    return [s.strip() for s in REDIS_SEEDS.split(",") if s.strip()]


REDIS_CLUSTER_DISCOVERY_INTERVAL = int(
    os.environ.get("COPAW_REDIS_CLUSTER_DISCOVERY_INTERVAL", "60"),
)
REDIS_DISCOVERY_MAX_RETRIES = int(
    os.environ.get("COPAW_REDIS_DISCOVERY_MAX_RETRIES", "3"),
)
REDIS_DISCOVERY_RETRY_DELAY = float(
    os.environ.get("COPAW_REDIS_DISCOVERY_RETRY_DELAY", "5.0"),
)
REDIS_CONNECT_TIMEOUT = int(
    os.environ.get("COPAW_REDIS_CONNECT_TIMEOUT", "2000"),
)
REDIS_MIN_CLUSTER_SIZE = int(
    os.environ.get("COPAW_REDIS_MIN_CLUSTER_SIZE", "3"),
)

# ============================================================================
# Redlock configuration
# ============================================================================
REDIS_LOCK_SINGLE_TIMEOUT = int(
    os.environ.get("COPAW_REDIS_LOCK_SINGLE_TIMEOUT", "50"),
)
REDIS_LOCK_RETRY_COUNT = int(
    os.environ.get("COPAW_REDIS_LOCK_RETRY_COUNT", "3"),
)
REDIS_LOCK_RETRY_DELAY = int(
    os.environ.get("COPAW_REDIS_LOCK_RETRY_DELAY", "100"),
)
REDIS_LOCK_DRIFT_FACTOR = float(
    os.environ.get("COPAW_REDIS_LOCK_DRIFT_FACTOR", "0.01"),
)
REDIS_LOCK_DISCOVERY_MAX_AGE = float(
    os.environ.get("COPAW_REDIS_LOCK_DISCOVERY_MAX_AGE", "5.0"),
)

# ============================================================================
# Cron lock configuration (for multi-instance coordination)
# ============================================================================
CRON_LOCK_ENABLED = os.environ.get(
    "COPAW_CRON_LOCK_ENABLED",
    "true",
).lower() in (
    "true",
    "1",
    "yes",
)
CRON_LOCK_TTL = int(os.environ.get("COPAW_CRON_LOCK_TTL", "600"))
CRON_LOCK_PREFIX = os.environ.get("COPAW_CRON_LOCK_PREFIX", "copaw:cron:user:")
CRON_LOCK_JITTER_MS = int(os.environ.get("COPAW_CRON_LOCK_JITTER_MS", "2000"))

# ============================================================================
# Instance ID (unique identifier for this process/machine)
# ============================================================================
import socket
import uuid as _uuid

_INSTANCE_ID = os.environ.get("COPAW_INSTANCE_ID", "")
if not _INSTANCE_ID:
    try:
        _INSTANCE_ID = socket.gethostname()
    except Exception:
        _INSTANCE_ID = str(_uuid.uuid4())[:8]
INSTANCE_ID = _INSTANCE_ID
