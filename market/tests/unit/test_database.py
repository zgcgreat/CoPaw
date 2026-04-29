# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_database_connection_is_connected_false_before_connect():
    from market.database.connection import DatabaseConnection, DatabaseConfig

    config = DatabaseConfig(
        host="localhost",
        port=3306,
        user="root",
        password="",
        database="test",
    )
    db = DatabaseConnection(config)
    assert db.is_connected is False


@pytest.mark.asyncio
async def test_get_db_dependency_returns_connection():
    from market.app.deps import get_db

    assert callable(get_db)
