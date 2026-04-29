# -*- coding: utf-8 -*-
"""Backup configuration models."""

from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BackupEnvironmentConfig(BaseModel):
    """AWS S3 configuration for a single environment (dev/prd)."""

    aws_access_key_id: str
    aws_secret_access_key: str
    s3_bucket: str
    s3_prefix: str = "swe_backup"
    s3_region: str = "sz"
    endpoint_url: str = ""  # 可选，用于阿里云 ECS 等自定义 S3 端点


class BackupCompressionConfig(BaseModel):
    """Compression settings for backup archives."""

    level: int = Field(default=6, ge=0, le=9)


class BackupTimeoutConfig(BaseModel):
    """Timeout settings for backup operations (minutes)."""

    compress: int = 30
    upload: int = 30
    download: int = 30


class ShellScriptConfig(BaseModel):
    """Shell script backup configuration.

    用于 Shell 脚本模式的备份压缩/解压配置。
    """

    compress_script_path: str = (
        "/opt/deployments/app/src/scripts/backup/compress.sh"
    )
    decompress_script_path: str = (
        "/opt/deployments/app/src/scripts/backup/decompress.sh"
    )
    timeout_seconds: int = Field(default=600, ge=60, le=3600)
    working_dir: str = ""  # 空则使用 WORKING_DIR 常量
    secret_dir: str = ""  # 空则使用 SECRET_DIR 常量


class BackupConfig(BaseModel):
    """Root backup configuration."""

    environments: dict[str, BackupEnvironmentConfig] = Field(
        default_factory=dict,
    )
    compression: BackupCompressionConfig = Field(
        default_factory=BackupCompressionConfig,
    )
    timeout: BackupTimeoutConfig = Field(default_factory=BackupTimeoutConfig)
    shell_script: ShellScriptConfig = Field(default_factory=ShellScriptConfig)

    def get_active_config(self) -> BackupEnvironmentConfig | None:
        """Get active environment config based on SWE_ENV."""
        env = os.environ.get("SWE_ENV", "prd")
        return self.environments.get(env)


def _get_env_var(key: str, default: str = "") -> str:
    """Get environment variable value.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Environment variable value or default
    """
    return os.environ.get(key, default)


def load_backup_config_from_env(
    env: Optional[str] = None,
) -> Optional[BackupConfig]:
    """Load backup configuration from environment variables.

    Environment variables (per environment):
        SWE_BACKUP_AWS_ACCESS_KEY_ID
        SWE_BACKUP_AWS_SECRET_ACCESS_KEY
        SWE_BACKUP_S3_BUCKET
        SWE_BACKUP_S3_PREFIX (optional, default: "swe_backup")
        SWE_BACKUP_S3_REGION (optional, default: "cn-north-1")
        SWE_BACKUP_ENDPOINT_URL (optional)

    Shell script backup configuration:
        SWE_BACKUP_COMPRESS_SCRIPT (optional)
        SWE_BACKUP_DECOMPRESS_SCRIPT (optional)
        SWE_BACKUP_SCRIPT_TIMEOUT (optional, default: "600")
        SWE_BACKUP_SCRIPT_WORKING_DIR (optional)
        SWE_BACKUP_SCRIPT_SECRET_DIR (optional)

    For multiple environments, use prefix:
        {ENV}_SWE_BACKUP_AWS_ACCESS_KEY_ID (e.g., DEV_SWE_BACKUP_AWS_ACCESS_KEY_ID)

    Args:
        env: Environment name ('dev' or 'prd'). If None, uses SWE_ENV.

    Returns:
        BackupConfig if required environment variables are set, None otherwise.
    """
    if env is None:
        env = os.environ.get("SWE_ENV", "prd")

    # Try environment-specific variables first, then fallback to generic
    env_prefix = f"{env.upper()}_"

    def get_var(key: str, default: str = "") -> str:
        """Get variable with environment prefix fallback."""
        # Try env-specific first (e.g., DEV_SWE_BACKUP_S3_BUCKET)
        env_specific = _get_env_var(f"{env_prefix}{key}")
        if env_specific:
            return env_specific
        # Fallback to generic (e.g., SWE_BACKUP_S3_BUCKET)
        return _get_env_var(key, default)

    # Check required variables
    aws_access_key_id = get_var("SWE_BACKUP_AWS_ACCESS_KEY_ID")
    aws_secret_access_key = get_var(
        "SWE_BACKUP_AWS_SECRET_ACCESS_KEY",
    ).removeprefix(
        "BEE_",
    )
    s3_bucket = get_var("SWE_BACKUP_S3_BUCKET")

    if not all([aws_access_key_id, aws_secret_access_key, s3_bucket]):
        logger.debug(
            "Backup configuration not complete for environment '%s'. "
            "Required: SWE_BACKUP_AWS_ACCESS_KEY_ID, "
            "SWE_BACKUP_AWS_SECRET_ACCESS_KEY, SWE_BACKUP_S3_BUCKET",
            env,
        )
        return None

    # Build environment config
    env_config = BackupEnvironmentConfig(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        s3_bucket=s3_bucket,
        s3_prefix=get_var("SWE_BACKUP_S3_PREFIX", "swe_backup"),
        s3_region=get_var("SWE_BACKUP_S3_REGION", "cn-north-1"),
        endpoint_url=get_var("SWE_BACKUP_ENDPOINT_URL", ""),
    )

    # Load shell script configuration
    shell_config = ShellScriptConfig(
        compress_script_path=get_var(
            "SWE_BACKUP_COMPRESS_SCRIPT",
            "/opt/deployments/app/src/scripts/backup/compress.sh",
        ),
        decompress_script_path=get_var(
            "SWE_BACKUP_DECOMPRESS_SCRIPT",
            "/opt/deployments/app/src/scripts/backup/decompress.sh",
        ),
        timeout_seconds=int(get_var("SWE_BACKUP_SCRIPT_TIMEOUT", "600")),
        working_dir=get_var("SWE_BACKUP_SCRIPT_WORKING_DIR", ""),
        secret_dir=get_var("SWE_BACKUP_SCRIPT_SECRET_DIR", ""),
    )

    return BackupConfig(
        environments={env: env_config},
        shell_script=shell_config,
    )


# Backward compatibility
def load_backup_config() -> Optional[BackupConfig]:
    """Load backup configuration from environment variables.

    This is the main entry point for loading backup configuration.

    Returns:
        BackupConfig if configuration is complete, None otherwise.
    """
    return load_backup_config_from_env()
