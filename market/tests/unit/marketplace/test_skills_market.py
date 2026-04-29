# -*- coding: utf-8 -*-
import asyncio
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


def _make_app(tmp_path):
    from fastapi import FastAPI
    from market.app.routers.skills_market import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = True
    mock_db.execute = AsyncMock(return_value=1)
    mock_db.fetch_one = AsyncMock(return_value=None)
    mock_db.fetch_all = AsyncMock(return_value=[])

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")
    return app


def test_publish_skill_returns_201(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    payload = {
        "name": "skill_x",
        "description": "test",
        "creator_id": "u1",
        "creator_name": "User",
        "skill_json": {"name": "skill_x"},
        "skill_md": "# Skill X",
    }
    resp = client.post(
        "/api/marketplace/skills",
        json=payload,
        headers={"X-Source-Id": "src_a", "X-Manager": "true"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "skill_x"
    assert data["version"] == "1.0.0"


def test_publish_skill_non_manager_returns_403(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    payload = {
        "name": "skill_x",
        "description": "",
        "creator_id": "u1",
        "creator_name": "",
        "skill_json": {},
        "skill_md": "",
    }
    resp = client.post(
        "/api/marketplace/skills",
        json=payload,
        headers={"X-Source-Id": "src_a"},
    )
    assert resp.status_code == 403


def test_unpublish_skill_returns_204(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    req = PublishSkillRequest(
        name="skill_y",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
    )
    item = asyncio.run(svc.publish_skill("src_a", req))
    client = TestClient(app)
    resp = client.delete(
        f"/api/marketplace/skills/{item.item_id}",
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 204


def test_unpublish_skill_not_found_returns_404(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.delete(
        "/api/marketplace/skills/nonexistent-id",
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 404


def test_distribute_skill_returns_200(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    req = PublishSkillRequest(
        name="skill_z",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
    )
    item = asyncio.run(svc.publish_skill("src_a", req))
    svc.db.fetch_all = AsyncMock(
        return_value=[
            {"tenant_id": "user1", "tenant_name": "User One", "bbk_id": "200"},
        ],
    )
    client = TestClient(app)
    resp = client.post(
        f"/api/marketplace/skills/{item.item_id}/distribute",
        json={"target_type": "all", "target_values": []},
        headers={
            "X-Source-Id": "src_a",
            "X-Manager": "true",
            "X-User-Id": "u1",
            "X-User-Name": "User",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["distributed_count"] == 1


def test_publish_skill_missing_source_id_returns_400(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    payload = {
        "name": "skill_x",
        "description": "",
        "creator_id": "u1",
        "creator_name": "",
        "skill_json": {},
        "skill_md": "",
    }
    resp = client.post(
        "/api/marketplace/skills",
        json=payload,
        headers={"X-Manager": "true"},
    )
    assert resp.status_code == 400
