# -*- coding: utf-8 -*-
"""Environment default configuration loader.

Loads environment-specific defaults from JSON files (dev.json, prd.json)
based on MARKET_ENV environment variable.

Priority (highest to lowest):
1. User's envs.json (persisted secrets)
2. Existing environment variables
3. Environment JSON defaults (this module)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_ENVS = ("dev", "prd")
DEFAULT_ENV = "prd"


def _get_package_dir() -> Path:
    """Get the market package directory."""
    return Path(__file__).resolve().parent.parent


def _load_env_json(env: str) -> dict[str, str]:
    """Load environment defaults from JSON file."""
    if env not in VALID_ENVS:
        logger.warning(
            "Invalid MARKET_ENV '%s', falling back to '%s'",
            env,
            DEFAULT_ENV,
        )
        env = DEFAULT_ENV

    config_file = _get_package_dir() / "config" / "envs" / f"{env}.json"
    if not config_file.exists():
        logger.warning("Environment config file not found: %s", config_file)
        return {}

    try:
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Failed to load environment config from %s: %s",
            config_file,
            exc,
        )
        return {}

    result: dict[str, str] = {}
    for key, value in data.items():
        result[key] = "" if value is None else str(value)
    return result


def load_env_defaults(env: str | None = None) -> dict[str, str]:
    """Load environment defaults and register them into os.environ."""
    if env is None:
        env = os.environ.get("MARKET_ENV", DEFAULT_ENV)

    defaults = _load_env_json(env)
    if not defaults:
        return {}

    set_vars: dict[str, str] = {}
    for key, value in defaults.items():
        if key not in os.environ:
            os.environ[key] = value
            set_vars[key] = value

    if set_vars:
        logger.debug(
            "Loaded %d environment defaults for '%s' environment: %s",
            len(set_vars),
            env,
            ", ".join(sorted(set_vars.keys())),
        )

    return set_vars


def get_current_env() -> str:
    """Get the current environment name."""
    return os.environ.get("MARKET_ENV", DEFAULT_ENV)
