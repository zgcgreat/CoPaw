# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient


def _make_app(mock_db):
    from fastapi import FastAPI
    from market.app.routers.categories import router
    from market.app.deps import get_db

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: mock_db
    return app


def test_get_categories_returns_list():
    mock_db = AsyncMock()
    mock_db.is_connected = True
    mock_db.fetch_all = AsyncMock(
        return_value=[
            {
                "id": 1,
                "source_id": "src_a",
                "name": "数据分析",
                "sort_order": 0,
                "created_at": None,
            },
            {
                "id": 2,
                "source_id": "src_a",
                "name": "报表",
                "sort_order": 1,
                "created_at": None,
            },
        ],
    )
    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.get(
        "/api/marketplace/categories",
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "数据分析"


def test_get_categories_missing_source_id_returns_400():
    mock_db = AsyncMock()
    mock_db.is_connected = True
    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.get("/api/marketplace/categories")
    assert response.status_code == 400


def test_get_categories_db_not_connected_returns_503():
    mock_db = MagicMock()
    mock_db.is_connected = False
    app = _make_app(mock_db)
    client = TestClient(app)
    response = client.get(
        "/api/marketplace/categories",
        headers={"X-Source-Id": "src_a"},
    )
    assert response.status_code == 503
