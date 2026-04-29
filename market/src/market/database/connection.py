# -*- coding: utf-8 -*-
"""异步 MySQL 连接池."""
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    import aiomysql

    AIOMYSQL_AVAILABLE = True
except ImportError:
    AIOMYSQL_AVAILABLE = False
    logger.debug(
        "aiomysql not installed, database features will be unavailable",
    )


class DatabaseConfig(BaseModel):
    host: str = Field(default="localhost")
    port: int = Field(default=3306)
    user: str = Field(default="root")
    password: str = Field(default="")
    database: str = Field(default="swe")
    min_connections: int = Field(default=2)
    max_connections: int = Field(default=10)
    charset: str = Field(default="utf8mb4")


class DatabaseConnection:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: Optional[Any] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._pool is not None

    async def connect(self) -> None:
        if not AIOMYSQL_AVAILABLE:
            raise RuntimeError("aiomysql is not installed")
        if self._pool is not None:
            return
        try:
            self._pool = await aiomysql.create_pool(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                db=self.config.database,
                charset=self.config.charset,
                minsize=self.config.min_connections,
                maxsize=self.config.max_connections,
                autocommit=True,
            )
            self._connected = True
            logger.info(
                "DB pool created: %s:%s/%s",
                self.config.host,
                self.config.port,
                self.config.database,
            )
        except Exception as e:
            logger.error("Failed to create DB pool: %s", e)
            self._connected = False
            raise

    async def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            self._connected = False

    @asynccontextmanager
    async def acquire(self):
        if self._pool is None:
            raise RuntimeError("Database not connected")
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, params: Optional[tuple] = None) -> int:
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return cur.rowcount

    async def execute_many(self, query: str, params_list: list[tuple]) -> int:
        if not params_list:
            return 0
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(query, params_list)
                return cur.rowcount

    async def fetch_one(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> Optional[dict]:
        async with self.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                row = await cur.fetchone()
                return dict(row) if row else None

    async def fetch_all(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> list[dict]:
        async with self.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
                return [dict(row) for row in rows] if rows else []
