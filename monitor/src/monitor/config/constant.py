# -*- coding: utf-8 -*-
"""Monitor 常量与环境变量加载工具."""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


_ENV_VAR_OVERRIDES: ContextVar[dict[str, str]] = ContextVar(
    "monitor_env_var_overrides",
    default=None,  # type: ignore[arg-type]
)


def _get_overrides() -> dict[str, str]:
    """Get current env var overrides."""
    val = _ENV_VAR_OVERRIDES.get()
    return val if val is not None else {}


@contextmanager
def env_var_overrides(overrides: dict[str, str]):
    """Temporarily override environment variables."""
    current = _get_overrides().copy()
    current.update(overrides)
    token = _ENV_VAR_OVERRIDES.set(current)
    try:
        yield
    finally:
        _ENV_VAR_OVERRIDES.reset(token)


class EnvVarLoader:
    """Utility to load and parse environment variables with type safety."""

    @staticmethod
    def get_bool(env_var: str, default: bool = False) -> bool:
        """Get a boolean environment variable."""
        overrides = _get_overrides()
        val = overrides.get(
            env_var,
            os.environ.get(env_var, str(default)),
        ).lower()
        return val in ("true", "1", "yes")

    @staticmethod
    def get_float(
        env_var: str,
        default: float = 0.0,
        min_value: float | None = None,
        max_value: float | None = None,
        allow_inf: bool = False,
    ) -> float:
        """Get a float environment variable with optional bounds."""
        try:
            overrides = _get_overrides()
            value = float(
                overrides.get(env_var, os.environ.get(env_var, str(default))),
            )
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            if not allow_inf and (
                value == float("inf") or value == float("-inf")
            ):
                return default
            return value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_int(
        env_var: str,
        default: int = 0,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Get an integer environment variable with optional bounds."""
        try:
            overrides = _get_overrides()
            value = int(
                overrides.get(env_var, os.environ.get(env_var, str(default))),
            )
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            return value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_str(env_var: str, default: str = "") -> str:
        """Get a string environment variable."""
        overrides = _get_overrides()
        return overrides.get(env_var, os.environ.get(env_var, default))


# ============================================================
# 核心目录配置
# ============================================================

WORKING_DIR = (
    Path(EnvVarLoader.get_str("MONITOR_WORKING_DIR", "~/.monitor"))
    .expanduser()
    .resolve()
)

SECRET_DIR = (
    Path(
        EnvVarLoader.get_str(
            "MONITOR_SECRET_DIR",
            f"{WORKING_DIR}.secret",
        ),
    )
    .expanduser()
    .resolve()
)

CONFIG_FILE = EnvVarLoader.get_str("MONITOR_CONFIG_FILE", "config.json")

LOG_LEVEL_ENV = "MONITOR_LOG_LEVEL"

# ============================================================
# 应用配置
# ============================================================

ENV_NAME = EnvVarLoader.get_str("MONITOR_ENV", "prd")

DOCS_ENABLED = EnvVarLoader.get_bool("MONITOR_OPENAPI_DOCS", False)

CORS_ORIGINS = EnvVarLoader.get_str("MONITOR_CORS_ORIGINS", "").strip()

DEFAULT_PORT = EnvVarLoader.get_int("MONITOR_PORT", 9090, min_value=1)
DEFAULT_HOST = EnvVarLoader.get_str("MONITOR_HOST", "127.0.0.1")

# ============================================================
# 数据库配置
# ============================================================

DB_HOST = EnvVarLoader.get_str("MONITOR_DB_HOST", "")
DB_PORT = EnvVarLoader.get_int("MONITOR_DB_PORT", 3306, min_value=1)
DB_USER = EnvVarLoader.get_str("MONITOR_DB_USER", "root")
DB_ACCESS = EnvVarLoader.get_str("MONITOR_DB_ACCESS", "")
DB_NAME = EnvVarLoader.get_str("MONITOR_DB_NAME", "monitor")
DB_MIN_CONN = EnvVarLoader.get_int("MONITOR_DB_MIN_CONN", 2, min_value=1)
DB_MAX_CONN = EnvVarLoader.get_int("MONITOR_DB_MAX_CONN", 10, min_value=1)

# ============================================================
# 监控配置
# ============================================================

MONITOR_INTERVAL = EnvVarLoader.get_int(
    "MONITOR_MONITOR_INTERVAL",
    60,
    min_value=10,
)

ALERT_ENABLED = EnvVarLoader.get_bool("MONITOR_ALERT_ENABLED", False)

ALERT_RETRY_COUNT = EnvVarLoader.get_int(
    "MONITOR_ALERT_RETRY_COUNT",
    3,
    min_value=1,
)

# ============================================================
# 请求超时配置
# ============================================================

REQUEST_TIMEOUT_SECONDS = EnvVarLoader.get_float(
    "MONITOR_REQUEST_TIMEOUT_SECONDS",
    60.0,
    min_value=10.0,
)

API_CALL_TIMEOUT = EnvVarLoader.get_float(
    "MONITOR_API_CALL_TIMEOUT",
    30.0,
    min_value=5.0,
)

HEALTH_CHECK_TIMEOUT = EnvVarLoader.get_float(
    "MONITOR_HEALTH_CHECK_TIMEOUT",
    10.0,
    min_value=1.0,
)
