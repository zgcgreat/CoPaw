# -*- coding: utf-8 -*-
"""Store module for temporary data storage."""
from __future__ import annotations

from .redis_store import RedisHashStore

__all__ = ["RedisHashStore"]
