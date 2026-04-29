# -*- coding: utf-8 -*-
import logging
import os
import time

from .utils.my_logging import setup_logger

LOG_LEVEL_ENV = "MARKET_LOG_LEVEL"

_bootstrap_err: Exception | None = None
try:
    # Load persisted env vars before importing modules that read env-backed
    # constants at import time.
    from .envs import load_envs_into_environ

    load_envs_into_environ()

    # Load environment-specific defaults (dev/prd) before importing
    # heavier config modules.
    from .env_defaults import load_env_defaults

    load_env_defaults()
except Exception as exc:
    _bootstrap_err = exc

_t0 = time.perf_counter()
setup_logger(os.environ.get(LOG_LEVEL_ENV, "info"))
if _bootstrap_err is not None:
    logging.getLogger(__name__).warning(
        "market: failed to load persisted envs on init: %s",
        _bootstrap_err,
    )
logging.getLogger(__name__).debug(
    "%.3fs package init",
    time.perf_counter() - _t0,
)
