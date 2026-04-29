# -*- coding: utf-8 -*-
"""Unit tests for featured case module (simplified - no case_id)."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from swe.app.featured_case.models import (
    CaseStep,
    FeaturedCase,
    FeaturedCaseCreate,
    FeaturedCaseUpdate,
)
from swe.app.featured_case.service import FeaturedCaseService
from swe.app.featured_case.store import FeaturedCaseStore


class TestModels:
    """Tests for data models."""

    def test_case_step(self):
        """Test CaseStep model."""
        step = CaseStep(title="步骤1", content="内容1")
        assert step.title == "步骤1"
        assert step.content == "内容1"

    def test_featured_case_model(self):
        """Test FeaturedCase model creation."""
        case = FeaturedCase(
            id=1,
            label="存款案例",
            value="我要做存款经营",
            iframe_url="https://example.com",
            iframe_title="详情",
            is_active=True,
            source_id="source1",
        )
        assert case.id == 1
        assert case.label == "存款案例"
        assert case.is_active is True

    def test_featured_case_with_steps(self):
        """Test FeaturedCase with steps."""
        steps = [
            CaseStep(title="步骤1", content="内容1"),
            CaseStep(title="步骤2", content="内容2"),
        ]
        case = FeaturedCase(
            label="案例",
            value="内容",
            steps=steps,
            source_id="source1",
        )
        assert case.steps is not None
        assert len(case.steps) == 2
        # pylint: disable=unsubscriptable-object
        assert case.steps[0].title == "步骤1"

    def test_featured_case_create_validation(self):
        """Test FeaturedCaseCreate validation."""
        request = FeaturedCaseCreate(
            label="案例",
            value="内容",
        )
        assert request.image_url is None
        assert request.steps is None

    def test_featured_case_update(self):
        """Test FeaturedCaseUpdate model."""
        request = FeaturedCaseUpdate(
            label="新标题",
            is_active=False,
        )
        assert request.label == "新标题"
        assert request.value is None


class TestFeaturedCaseStore:
    """Tests for FeaturedCaseStore without database."""

    @pytest.fixture
    def store(self):
        """Create store without database."""
        return FeaturedCaseStore(db=None)

    def test_store_initialization(self, store):
        """Test store initializes correctly without database."""
        assert store.db is None
        # pylint: disable=protected-access
        assert store._use_db is False

    @pytest.mark.asyncio
    async def test_get_cases_for_dimension_no_db(self, store):
        """Test get_cases_for_dimension returns empty without database."""
        result = await store.get_cases_for_dimension("source1", "bbk1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_case_by_id_no_db(self, store):
        """Test get_case_by_id returns None without database."""
        result = await store.get_case_by_id(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_cases_no_db(self, store):
        """Test list_cases returns empty without database."""
        cases, total = await store.list_cases(source_id="source1")
        assert cases == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_create_case_no_db(self, store):
        """Test create_case returns case without database."""
        case = FeaturedCase(
            label="案例",
            value="内容",
            source_id="source1",
        )
        result = await store.create_case(case)
        assert result.label == "案例"

    @pytest.mark.asyncio
    async def test_update_case_no_db(self, store):
        """Test update_case returns None without database."""
        result = await store.update_case(1, label="新")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_case_no_db(self, store):
        """Test delete_case returns False without database."""
        result = await store.delete_case(1)
        assert result is False


class TestFeaturedCaseStoreWithMockDb:
    """Tests for FeaturedCaseStore with mocked database."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database connection."""
        db = MagicMock()
        db.is_connected = True
        db.fetch_one = AsyncMock()
        db.fetch_all = AsyncMock()
        db.execute = AsyncMock(return_value=1)
        return db

    @pytest.fixture
    def store(self, mock_db):
        """Create store with mock database."""
        return FeaturedCaseStore(db=mock_db)

    @pytest.mark.asyncio
    async def test_get_cases_for_dimension(self, store, mock_db):
        """Test get_cases_for_dimension returns cases."""
        mock_db.fetch_all.return_value = [
            {
                "id": 1,
                "label": "存款案例",
                "value": "我要做存款",
                "image_url": None,
                "iframe_url": "https://example.com",
                "iframe_title": "详情",
                "steps": json.dumps([{"title": "步骤1", "content": "内容1"}]),
                "sort_order": 1,
            },
            {
                "id": 2,
                "label": "基金案例",
                "value": "我要买基金",
                "image_url": None,
                "iframe_url": None,
                "iframe_title": None,
                "steps": None,
                "sort_order": 2,
            },
        ]
        result = await store.get_cases_for_dimension("source1", "bbk1")
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["detail"]["steps"][0]["title"] == "步骤1"
        assert result[1]["detail"] is None

    @pytest.mark.asyncio
    async def test_get_cases_for_dimension_with_null_bbk_id(
        self,
        store,
        mock_db,
    ):
        """Test get_cases_for_dimension with null bbk_id."""
        mock_db.fetch_all.return_value = []
        await store.get_cases_for_dimension("source1", None)
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_case_by_id(self, store, mock_db):
        """Test get_case_by_id returns case."""
        mock_db.fetch_one.return_value = {
            "id": 1,
            "source_id": "source1",
            "bbk_id": "bbk1",
            "label": "案例",
            "value": "内容",
            "image_url": None,
            "iframe_url": "https://example.com",
            "iframe_title": "详情",
            "steps": json.dumps([{"title": "步骤1", "content": "内容1"}]),
            "sort_order": 0,
            "is_active": 1,
            "created_at": datetime.now(),
            "updated_at": None,
        }
        result = await store.get_case_by_id(1)
        assert result is not None
        assert result.id == 1
        assert len(result.steps) == 1

    @pytest.mark.asyncio
    async def test_list_cases_with_pagination(self, store, mock_db):
        """Test list_cases with pagination."""
        mock_db.fetch_one.return_value = {"total": 10}
        mock_db.fetch_all.return_value = [
            {
                "id": 1,
                "source_id": "source1",
                "bbk_id": None,
                "label": "案例1",
                "value": "内容1",
                "image_url": None,
                "iframe_url": None,
                "iframe_title": None,
                "steps": None,
                "sort_order": 0,
                "is_active": 1,
                "created_at": datetime.now(),
                "updated_at": None,
            },
        ]
        cases, total = await store.list_cases(
            source_id="source1",
            page=1,
            page_size=10,
        )
        assert total == 10
        assert len(cases) == 1

    @pytest.mark.asyncio
    async def test_create_case_with_db(self, store, mock_db):
        """Test create_case with database auto-increments sort_order."""
        # Mock max sort_order query returns 5
        mock_db.fetch_one.return_value = {"max_order": 5}
        case = FeaturedCase(
            label="案例",
            value="内容",
            steps=[CaseStep(title="步骤1", content="内容1")],
            is_active=True,
            source_id="source1",
        )
        result = await store.create_case(case)
        # Verify sort_order was auto-incremented
        assert result.sort_order == 6
        # Verify both queries were called
        assert mock_db.fetch_one.call_count == 1
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_case_first_in_dimension(self, store, mock_db):
        """Test create_case when no existing cases (sort_order starts at 0)."""
        # Mock max sort_order query returns -1 (no existing cases)
        mock_db.fetch_one.return_value = {"max_order": -1}
        case = FeaturedCase(
            label="首个案例",
            value="内容",
            is_active=True,
            source_id="source1",
        )
        result = await store.create_case(case)
        assert result.sort_order == 0

    @pytest.mark.asyncio
    async def test_update_case_with_db(self, store, mock_db):
        """Test update_case with database."""
        mock_db.fetch_one.return_value = {
            "id": 1,
            "source_id": "source1",
            "bbk_id": None,
            "label": "新标题",
            "value": "新内容",
            "image_url": None,
            "iframe_url": None,
            "iframe_title": None,
            "steps": None,
            "sort_order": 0,
            "is_active": 1,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        result = await store.update_case(1, label="新标题")
        assert result is not None
        assert result.label == "新标题"

    @pytest.mark.asyncio
    async def test_delete_case_with_db(self, store, mock_db):
        """Test delete_case with database."""
        result = await store.delete_case(1)
        assert result is True
        mock_db.execute.assert_called_once()


class TestFeaturedCaseService:
    """Tests for FeaturedCaseService."""

    @pytest.fixture
    def mock_store(self):
        """Create mock store."""
        store = MagicMock(spec=FeaturedCaseStore)
        store.get_cases_for_dimension = AsyncMock(return_value=[])
        store.get_case_by_id = AsyncMock()
        store.list_cases = AsyncMock(return_value=([], 0))
        store.create_case = AsyncMock()
        store.update_case = AsyncMock()
        store.delete_case = AsyncMock()
        return store

    @pytest.fixture
    def service(self, mock_store):
        """Create service with mock store."""
        return FeaturedCaseService(mock_store)

    @pytest.mark.asyncio
    async def test_get_cases_for_dimension(self, service, mock_store):
        """Test get_cases_for_dimension delegates to store."""
        expected = [{"id": 1, "label": "案例"}]
        mock_store.get_cases_for_dimension.return_value = expected
        result = await service.get_cases_for_dimension("source1", "bbk1")
        assert result == expected

    @pytest.mark.asyncio
    async def test_create_case_success(self, service, mock_store):
        """Test create_case succeeds."""
        request = FeaturedCaseCreate(
            label="案例",
            value="内容",
        )
        expected = FeaturedCase(
            id=1,
            label="案例",
            value="内容",
            is_active=True,
            source_id="source1",
        )
        mock_store.create_case.return_value = expected
        result = await service.create_case("source1", request)
        assert result.label == "案例"

    @pytest.mark.asyncio
    async def test_update_case_success(self, service, mock_store):
        """Test update_case succeeds."""
        expected = FeaturedCase(
            id=1,
            label="新标题",
            value="新内容",
            source_id="source1",
        )
        mock_store.update_case.return_value = expected
        request = FeaturedCaseUpdate(label="新标题")
        result = await service.update_case(1, request)
        assert result.label == "新标题"

    @pytest.mark.asyncio
    async def test_update_case_not_found_raises(self, service, mock_store):
        """Test update_case raises when not found."""
        mock_store.update_case.return_value = None
        request = FeaturedCaseUpdate(label="新")
        with pytest.raises(ValueError, match="不存在"):
            await service.update_case(1, request)

    @pytest.mark.asyncio
    async def test_delete_case_success(self, service, mock_store):
        """Test delete_case succeeds."""
        mock_store.delete_case.return_value = True
        await service.delete_case(1)
        mock_store.delete_case.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_case_not_found_raises(self, service, mock_store):
        """Test delete_case raises when not found."""
        mock_store.delete_case.return_value = False
        with pytest.raises(ValueError, match="不存在"):
            await service.delete_case(1)
