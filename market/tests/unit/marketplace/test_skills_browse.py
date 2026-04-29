# -*- coding: utf-8 -*-
import asyncio
import json
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


def _make_app(tmp_path):
    from fastapi import FastAPI
    from market.app.routers.skills_browse import router
    from market.marketplace.service import MarketplaceService
    from market.database.connection import DatabaseConnection

    mock_db = AsyncMock(spec=DatabaseConnection)
    mock_db.is_connected = False  # no DB needed for fs-only tests

    svc = MarketplaceService(
        db=mock_db,
        marketplace_root=tmp_path / "market",
        swe_root=tmp_path / "swe",
    )
    app = FastAPI()
    app.state.marketplace = svc
    app.include_router(router, prefix="/api")
    return app


def _publish(svc, source_id, name, bbk_ids=None):
    from market.marketplace.schemas import PublishSkillRequest

    req = PublishSkillRequest(
        name=name,
        description="desc",
        creator_id="u1",
        creator_name="User",
        skill_json={},
        skill_md="",
        bbk_ids=bbk_ids or [],
    )
    return asyncio.run(svc.publish_skill(source_id, req))


def test_list_skills_returns_active_items(tmp_path):
    app = _make_app(tmp_path)
    _publish(app.state.marketplace, "src_a", "skill_1")
    _publish(app.state.marketplace, "src_a", "skill_2")
    client = TestClient(app)
    resp = client.get(
        "/api/marketplace/skills",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_skills_missing_source_id_returns_400(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/marketplace/skills", headers={"X-Bbk-Id": "100"})
    assert resp.status_code == 400


def test_list_skills_filters_by_category(tmp_path):
    from market.marketplace.schemas import PublishSkillRequest

    app = _make_app(tmp_path)
    svc = app.state.marketplace
    req1 = PublishSkillRequest(
        name="skill_cat1",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
        category_id=1,
    )
    req2 = PublishSkillRequest(
        name="skill_cat2",
        description="",
        creator_id="u1",
        creator_name="",
        skill_json={},
        skill_md="",
        category_id=2,
    )
    asyncio.run(svc.publish_skill("src_a", req1))
    asyncio.run(svc.publish_skill("src_a", req2))
    client = TestClient(app)
    resp = client.get(
        "/api/marketplace/skills?category_id=1",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "skill_cat1"


def test_get_skill_detail_returns_200(tmp_path):
    app = _make_app(tmp_path)
    item = _publish(app.state.marketplace, "src_a", "skill_d")
    client = TestClient(app)
    resp = client.get(
        f"/api/marketplace/skills/{item.item_id}",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 200
    assert resp.json()["item_id"] == item.item_id


def test_get_skill_detail_not_found_returns_404(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(
        "/api/marketplace/skills/no-such-id",
        headers={"X-Source-Id": "src_a", "X-Bbk-Id": "100"},
    )
    assert resp.status_code == 404


def test_get_my_skills_returns_list(tmp_path):
    from market.marketplace.fs import get_user_skills_dir

    skills_dir = get_user_skills_dir(tmp_path / "swe", "user1")
    skill_dir = skills_dir / "my_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.json").write_text(
        json.dumps({"source": "customized", "description": "my skill"}),
        encoding="utf-8",
    )
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(
        "/api/skills/mine",
        headers={"X-Source-Id": "src_a", "X-User-Id": "user1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["skill_name"] == "my_skill"
    assert data[0]["is_received"] is False


def test_get_received_skills_returns_only_received(tmp_path):
    from market.marketplace.fs import get_user_skills_dir

    skills_dir = get_user_skills_dir(tmp_path / "swe", "user2")
    d1 = skills_dir / "created_skill"
    d1.mkdir(parents=True)
    (d1 / "skill.json").write_text(
        json.dumps({"source": "customized"}),
        encoding="utf-8",
    )
    d2 = skills_dir / "received_skill"
    d2.mkdir(parents=True)
    (d2 / "skill.json").write_text(
        json.dumps(
            {"source": "marketplace:item-1", "received_version": "1.0.0"},
        ),
        encoding="utf-8",
    )
    app = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get(
        "/api/skills/received",
        headers={"X-Source-Id": "src_a", "X-User-Id": "user2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["skill_name"] == "received_skill"
    assert data[0]["is_received"] is True
