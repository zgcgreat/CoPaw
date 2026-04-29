# 精选案例管理简化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 `case_id` 字段，简化精选案例数据模型，使用数据库 `id` 作为唯一标识。

**Architecture:** 后端三层架构（models → store → service → router），前端类型/API/组件三层，测试覆盖核心逻辑。

**Tech Stack:** Python/FastAPI/Pydantic (后端), TypeScript/React/Ant Design (前端), MySQL (数据库), pytest (测试)

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `scripts/sql/content_config_tables.sql` | 修改 | 数据库表结构 |
| `src/swe/app/featured_case/models.py` | 修改 | 数据模型定义 |
| `src/swe/app/featured_case/store.py` | 修改 | 数据库操作层 |
| `src/swe/app/featured_case/service.py` | 修改 | 业务逻辑层 |
| `src/swe/app/featured_case/router.py` | 修改 | API 路由层 |
| `console/src/api/types/featuredCases.ts` | 修改 | 前端类型定义 |
| `console/src/api/modules/featuredCases.ts` | 修改 | 前端 API 模块 |
| `console/src/pages/Control/FeaturedCases/index.tsx` | 修改 | 管理页面 |
| `console/src/pages/Control/FeaturedCases/components/columns.tsx` | 修改 | 表格列定义 |
| `console/src/pages/Control/FeaturedCases/components/CaseDrawer.tsx` | 修改 | 案例 Drawer |
| `console/src/components/agentscope-chat/FeaturedCases/index.tsx` | 修改 | 展示组件 |
| `console/src/components/agentscope-chat/CaseDetailDrawer/index.tsx` | 修改 | 详情 Drawer |
| `tests/unit/app/test_featured_case.py` | 修改 | 单元测试 |

---

### Task 1: 更新数据库表结构

**Files:**
- Modify: `scripts/sql/content_config_tables.sql`

- [ ] **Step 1: 移除 case_id 字段和唯一约束**

更新 `swe_featured_case` 表结构：

```sql
# -*- coding: utf-8 -*-
-- ============================================================
-- CoPaw 精选案例配置管理数据库表（简化版）
-- 创建时间: 2026-04-27
-- 说明: 移除 case_id 字段，使用数据库 id 作为唯一标识
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------
-- 表: swe_featured_case
-- 说明: 精选案例表
-- 变更: 移除 case_id 字段，移除唯一约束
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_featured_case` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '案例ID（唯一标识）',
    `source_id` VARCHAR(64) NOT NULL COMMENT '来源ID（从 X-Source-Id 获取）',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK ID（可选）',
    `label` VARCHAR(512) NOT NULL COMMENT '案例标题',
    `value` TEXT NOT NULL COMMENT '提问内容',
    `image_url` VARCHAR(1024) DEFAULT NULL COMMENT '案例图片 URL',
    `iframe_url` VARCHAR(1024) DEFAULT NULL COMMENT 'iframe 详情页 URL',
    `iframe_title` VARCHAR(256) DEFAULT NULL COMMENT 'iframe 标题',
    `steps` JSON DEFAULT NULL COMMENT '步骤说明（JSON 数组）',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_source_bbk` (`source_id`, `bbk_id`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='精选案例表';

-- -----------------------------------------------------------
-- 表: swe_greeting_config
-- 说明: 引导文案配置表（保留不变）
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_greeting_config` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `source_id` VARCHAR(64) NOT NULL COMMENT '来源ID（必填）',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK ID（可选，source_id 子分组）',
    `greeting` VARCHAR(512) NOT NULL COMMENT '欢迎语',
    `subtitle` VARCHAR(512) DEFAULT NULL COMMENT '副标题',
    `placeholder` VARCHAR(256) DEFAULT NULL COMMENT '输入框占位符',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_source_bbk` (`source_id`, `bbk_id`),
    INDEX `idx_source_id` (`source_id`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='引导文案配置表';

SET FOREIGN_KEY_CHECKS = 1;
```

- [ ] **Step 2: 提交数据库变更**

```bash
git add scripts/sql/content_config_tables.sql
git commit -m "refactor(db): remove case_id from swe_featured_case table"
```

---

### Task 2: 更新后端数据模型

**Files:**
- Modify: `src/swe/app/featured_case/models.py`

- [ ] **Step 1: 移除 case_id 字段**

更新 models.py：

```python
# -*- coding: utf-8 -*-
"""Featured case models (simplified - no case_id)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CaseStep(BaseModel):
    """Case step."""

    title: str
    content: str


class CaseDetail(BaseModel):
    """Case detail with iframe and steps."""

    iframe_url: str = ""
    iframe_title: str = ""
    steps: List[CaseStep] = []


class FeaturedCase(BaseModel):
    """Featured case with dimension info."""

    model_config = ConfigDict(use_enum_values=True)

    id: Optional[int] = None
    source_id: str = Field(..., min_length=1, max_length=64)
    bbk_id: Optional[str] = Field(None, max_length=64)
    label: str = Field(..., min_length=1, max_length=512)
    value: str = Field(..., min_length=1)
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FeaturedCaseCreate(BaseModel):
    """Create featured case request.

    Note: source_id is NOT a form field - it comes from X-Source-Id header.
    """

    bbk_id: Optional[str] = Field(None, max_length=64)
    label: str = Field(..., min_length=1, max_length=512)
    value: str = Field(..., min_length=1)
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: int = 0


class FeaturedCaseUpdate(BaseModel):
    """Update featured case request."""

    bbk_id: Optional[str] = Field(None, max_length=64)
    label: Optional[str] = Field(None, min_length=1, max_length=512)
    value: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class FeaturedCaseListResponse(BaseModel):
    """Featured case list response."""

    cases: List[FeaturedCase]
    total: int
```

- [ ] **Step 2: 验证模型导入正常**

```bash
python -c "from swe.app.featured_case.models import FeaturedCase, FeaturedCaseCreate, FeaturedCaseUpdate; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交模型变更**

```bash
git add src/swe/app/featured_case/models.py
git commit -m "refactor(models): remove case_id from FeaturedCase models"
```

---

### Task 3: 更新存储层

**Files:**
- Modify: `src/swe/app/featured_case/store.py`

- [ ] **Step 1: 更新 store.py**

移除 case_id 相关逻辑，使用 id 作为标识：

```python
# -*- coding: utf-8 -*-
"""Featured case store (simplified - no case_id)."""

import json
import logging
from typing import Any, Optional

from .models import CaseStep, FeaturedCase

logger = logging.getLogger(__name__)


class FeaturedCaseStore:
    """Store for featured case operations."""

    def __init__(self, db: Optional[Any] = None):
        """Initialize store.

        Args:
            db: Database connection (TDSQLConnection)
        """
        self.db = db
        self._use_db = db is not None and db.is_connected

    # ==================== Case display queries ====================

    async def get_cases_for_dimension(
        self,
        source_id: str,
        bbk_id: Optional[str] = None,
    ) -> list[dict]:
        """Get cases for a specific dimension.

        Exact match: source_id=X AND bbk_id=Y
        Returns empty list if no match.

        Args:
            source_id: Source identifier
            bbk_id: BBK identifier (optional)

        Returns:
            List of case dicts for display
        """
        if not self._use_db:
            return []

        query = """
            SELECT id, label, value, image_url,
                   iframe_url, iframe_title, steps, sort_order
            FROM swe_featured_case
            WHERE source_id = %s AND bbk_id <=> %s AND is_active = 1
            ORDER BY sort_order ASC
        """
        rows = await self.db.fetch_all(query, (source_id, bbk_id))

        result = []
        for row in rows:
            steps = None
            if row["steps"]:
                try:
                    steps = json.loads(row["steps"])
                except json.JSONDecodeError:
                    steps = None

            detail = None
            if row["iframe_url"] or steps:
                detail = {
                    "iframe_url": row["iframe_url"] or "",
                    "iframe_title": row["iframe_title"] or "",
                    "steps": steps or [],
                }

            result.append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "value": row["value"],
                    "image_url": row["image_url"],
                    "sort_order": row["sort_order"],
                    "detail": detail,
                },
            )
        return result

    async def get_case_by_id(self, case_id: int) -> Optional[FeaturedCase]:
        """Get case by id.

        Args:
            case_id: Case database id

        Returns:
            FeaturedCase if found, None otherwise
        """
        if not self._use_db:
            return None

        query = "SELECT * FROM swe_featured_case WHERE id = %s"
        row = await self.db.fetch_one(query, (case_id,))
        return self._row_to_case(row) if row else None

    # ==================== Case CRUD ====================

    async def list_cases(
        self,
        source_id: str,
        bbk_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FeaturedCase], int]:
        """List cases for a specific source_id with optional bbk_id filter.

        Args:
            source_id: Source identifier (required)
            bbk_id: BBK identifier (optional filter)
            page: Page number (1-based)
            page_size: Items per page

        Returns:
            Tuple of (cases list, total count)
        """
        if not self._use_db:
            return [], 0

        where_clauses = ["source_id = %s"]
        params: list = [source_id]

        if bbk_id is not None:
            where_clauses.append("bbk_id <=> %s")
            params.append(bbk_id)

        where_sql = " AND ".join(where_clauses)

        count_query = f"SELECT COUNT(*) as total FROM swe_featured_case WHERE {where_sql}"
        count_row = await self.db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        offset = (page - 1) * page_size
        query = f"""
            SELECT * FROM swe_featured_case
            WHERE {where_sql}
            ORDER BY sort_order ASC, created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        rows = await self.db.fetch_all(query, tuple(params))
        cases = [self._row_to_case(row) for row in rows]
        return cases, total

    async def create_case(self, case: FeaturedCase) -> FeaturedCase:
        """Create case.

        Args:
            case: FeaturedCase to create

        Returns:
            Created FeaturedCase
        """
        if self._use_db:
            steps_json = (
                json.dumps([s.model_dump() for s in case.steps])
                if case.steps
                else None
            )
            query = """
                INSERT INTO swe_featured_case
                    (source_id, bbk_id, label, value, image_url,
                     iframe_url, iframe_title, steps, sort_order, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            await self.db.execute(
                query,
                (
                    case.source_id,
                    case.bbk_id,
                    case.label,
                    case.value,
                    case.image_url,
                    case.iframe_url,
                    case.iframe_title,
                    steps_json,
                    case.sort_order,
                    int(case.is_active),
                ),
            )
        return case

    async def update_case(
        self,
        case_id: int,
        bbk_id: Optional[str] = None,
        label: Optional[str] = None,
        value: Optional[str] = None,
        image_url: Optional[str] = None,
        iframe_url: Optional[str] = None,
        iframe_title: Optional[str] = None,
        steps: Optional[list[CaseStep]] = None,
        sort_order: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[FeaturedCase]:
        """Update case.

        Args:
            case_id: Case database id
            bbk_id: New bbk_id
            label: New label
            value: New value
            image_url: New image URL
            iframe_url: New iframe URL
            iframe_title: New iframe title
            steps: New steps
            sort_order: New sort order
            is_active: New active status

        Returns:
            Updated FeaturedCase or None if not found
        """
        if not self._use_db:
            return None

        updates = []
        params: list = []

        if bbk_id is not None:
            updates.append("bbk_id = %s")
            params.append(bbk_id)
        if label is not None:
            updates.append("label = %s")
            params.append(label)
        if value is not None:
            updates.append("value = %s")
            params.append(value)
        if image_url is not None:
            updates.append("image_url = %s")
            params.append(image_url)
        if iframe_url is not None:
            updates.append("iframe_url = %s")
            params.append(iframe_url)
        if iframe_title is not None:
            updates.append("iframe_title = %s")
            params.append(iframe_title)
        if steps is not None:
            updates.append("steps = %s")
            params.append(
                json.dumps([s.model_dump() for s in steps]) if steps else None,
            )
        if sort_order is not None:
            updates.append("sort_order = %s")
            params.append(sort_order)
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(int(is_active))

        if not updates:
            return None

        params.append(case_id)
        query = f"""
            UPDATE swe_featured_case
            SET {', '.join(updates)}
            WHERE id = %s
        """
        await self.db.execute(query, tuple(params))
        return await self.get_case_by_id(case_id)

    async def delete_case(self, case_id: int) -> bool:
        """Delete case.

        Args:
            case_id: Case database id

        Returns:
            True if deleted, False otherwise
        """
        if self._use_db:
            query = "DELETE FROM swe_featured_case WHERE id = %s"
            result = await self.db.execute(query, (case_id,))
            return result > 0
        return False

    def _row_to_case(self, row: dict) -> FeaturedCase:
        """Convert row to FeaturedCase.

        Args:
            row: Database row dict

        Returns:
            FeaturedCase instance
        """
        steps = None
        if row.get("steps"):
            try:
                steps_data = json.loads(row["steps"])
                steps = [CaseStep(**s) for s in steps_data]
            except json.JSONDecodeError:
                steps = None

        return FeaturedCase(
            id=row["id"],
            source_id=row["source_id"],
            bbk_id=row["bbk_id"],
            label=row["label"],
            value=row["value"],
            image_url=row["image_url"],
            iframe_url=row["iframe_url"],
            iframe_title=row["iframe_title"],
            steps=steps,
            sort_order=row["sort_order"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
```

- [ ] **Step 2: 验证 store 导入正常**

```bash
python -c "from swe.app.featured_case.store import FeaturedCaseStore; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交存储层变更**

```bash
git add src/swe/app/featured_case/store.py
git commit -m "refactor(store): use id instead of case_id in FeaturedCaseStore"
```

---

### Task 4: 更新服务层

**Files:**
- Modify: `src/swe/app/featured_case/service.py`

- [ ] **Step 1: 更新 service.py**

移除 check_case_exists 逻辑，使用 id 作为标识：

```python
# -*- coding: utf-8 -*-
"""Featured case service (simplified - no case_id)."""

import logging
from typing import Optional

from .models import FeaturedCase, FeaturedCaseCreate, FeaturedCaseUpdate
from .store import FeaturedCaseStore

logger = logging.getLogger(__name__)


class FeaturedCaseService:
    """Service for featured case operations."""

    def __init__(self, store: FeaturedCaseStore):
        """Initialize service.

        Args:
            store: FeaturedCaseStore instance
        """
        self.store = store

    # ==================== Case display ====================

    async def get_cases_for_dimension(
        self,
        source_id: str,
        bbk_id: Optional[str] = None,
    ) -> list[dict]:
        """Get cases for a specific dimension.

        Args:
            source_id: Source identifier
            bbk_id: BBK identifier (optional)

        Returns:
            List of case dicts for display
        """
        return await self.store.get_cases_for_dimension(source_id, bbk_id)

    async def get_case_by_id(self, case_id: int) -> Optional[FeaturedCase]:
        """Get case by id.

        Args:
            case_id: Case database id

        Returns:
            FeaturedCase if found, None otherwise
        """
        return await self.store.get_case_by_id(case_id)

    # ==================== Case CRUD ====================

    async def list_cases(
        self,
        source_id: str,
        bbk_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FeaturedCase], int]:
        """List cases for a specific source_id.

        Args:
            source_id: Source identifier (required)
            bbk_id: BBK identifier (optional filter)
            page: Page number (1-based)
            page_size: Items per page

        Returns:
            Tuple of (cases list, total count)
        """
        return await self.store.list_cases(
            source_id=source_id,
            bbk_id=bbk_id,
            page=page,
            page_size=page_size,
        )

    async def create_case(
        self,
        source_id: str,
        request: FeaturedCaseCreate,
    ) -> FeaturedCase:
        """Create case with source_id from context.

        Args:
            source_id: Source identifier (from X-Source-Id header)
            request: Create request (without source_id)

        Returns:
            Created FeaturedCase
        """
        case = FeaturedCase(
            source_id=source_id,
            bbk_id=request.bbk_id,
            label=request.label,
            value=request.value,
            image_url=request.image_url,
            iframe_url=request.iframe_url,
            iframe_title=request.iframe_title,
            steps=request.steps,
            sort_order=request.sort_order,
            is_active=True,
        )
        return await self.store.create_case(case)

    async def update_case(
        self,
        case_id: int,
        request: FeaturedCaseUpdate,
    ) -> FeaturedCase:
        """Update case.

        Args:
            case_id: Case database id
            request: Update request

        Returns:
            Updated FeaturedCase

        Raises:
            ValueError: If case not found
        """
        updated = await self.store.update_case(
            case_id=case_id,
            bbk_id=request.bbk_id,
            label=request.label,
            value=request.value,
            image_url=request.image_url,
            iframe_url=request.iframe_url,
            iframe_title=request.iframe_title,
            steps=request.steps,
            sort_order=request.sort_order,
            is_active=request.is_active,
        )
        if not updated:
            raise ValueError("案例不存在")
        return updated

    async def delete_case(self, case_id: int) -> None:
        """Delete case.

        Args:
            case_id: Case database id

        Raises:
            ValueError: If case not found
        """
        deleted = await self.store.delete_case(case_id)
        if not deleted:
            raise ValueError("案例不存在")
```

- [ ] **Step 2: 验证 service 导入正常**

```bash
python -c "from swe.app.featured_case.service import FeaturedCaseService; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交服务层变更**

```bash
git add src/swe/app/featured_case/service.py
git commit -m "refactor(service): use id instead of case_id in FeaturedCaseService"
```

---

### Task 5: 更新 API 路由

**Files:**
- Modify: `src/swe/app/featured_case/router.py`

- [ ] **Step 1: 更新 router.py**

API 路径使用 id 而非 case_id：

```python
# -*- coding: utf-8 -*-
"""Featured case API router (simplified - no case_id)."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from .models import (
    FeaturedCaseCreate,
    FeaturedCaseListResponse,
    FeaturedCaseUpdate,
)
from .service import FeaturedCaseService
from .store import FeaturedCaseStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/featured-cases", tags=["featured-cases"])

# Global instances
_store: Optional[FeaturedCaseStore] = None
_service: Optional[FeaturedCaseService] = None


def init_featured_case_module(db=None) -> None:
    """Initialize featured case module.

    Args:
        db: Database connection (TDSQLConnection)

    Raises:
        RuntimeError: If database is not connected
    """
    global _store, _service

    if db is None or not getattr(db, "is_connected", False):
        raise RuntimeError(
            "Featured case module requires a connected database.",
        )

    _store = FeaturedCaseStore(db)
    _service = FeaturedCaseService(_store)
    logger.info("Featured case module initialized")


def get_service() -> FeaturedCaseService:
    """Get featured case service.

    Returns:
        FeaturedCaseService instance

    Raises:
        RuntimeError: If module not initialized
    """
    global _service
    if _service is None:
        raise RuntimeError("Featured case module not initialized")
    return _service


# ==================== Client endpoints (for frontend display) ====================


@router.get(
    "",
    summary="Get cases for current context",
    description="Returns cases matched by X-Source-Id and X-Bbk-Id headers",
)
async def list_cases_for_display(request: Request) -> list[dict]:
    """Get cases for display.

    Headers:
        X-Source-Id: Source ID (required)
        X-Bbk-Id: BBK ID (optional)
    """
    source_id = request.headers.get("X-Source-Id")
    bbk_id = request.headers.get("X-Bbk-Id")

    if not source_id:
        return []

    service = get_service()
    return await service.get_cases_for_dimension(source_id, bbk_id)


@router.get(
    "/{case_id}",
    summary="Get case detail",
)
async def get_case_detail(case_id: int) -> dict:
    """Get case detail by id."""
    service = get_service()
    case = await service.get_case_by_id(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case.model_dump()


# ==================== Admin endpoints ====================


@router.get(
    "/admin/cases",
    response_model=FeaturedCaseListResponse,
    summary="List all cases (admin)",
)
async def list_all_cases(
    request: Request,
    bbk_id: Optional[str] = Query(None, description="Filter by BBK ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> FeaturedCaseListResponse:
    """List all cases for the current source_id context.

    Headers:
        X-Source-Id: Source ID (required, used as filter)
    """
    source_id = request.headers.get("X-Source-Id")
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header required",
        )

    service = get_service()
    cases, total = await service.list_cases(
        source_id=source_id,
        bbk_id=bbk_id,
        page=page,
        page_size=page_size,
    )
    return FeaturedCaseListResponse(cases=cases, total=total)


@router.post(
    "/admin/cases",
    summary="Create case (admin)",
)
async def create_case(request: Request, case: FeaturedCaseCreate) -> dict:
    """Create case definition.

    source_id comes from X-Source-Id header (not from request body).
    """
    source_id = request.headers.get("X-Source-Id")
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header required",
        )

    service = get_service()
    created = await service.create_case(source_id, case)
    return {"success": True, "data": created.model_dump()}


@router.put(
    "/admin/cases/{case_id}",
    summary="Update case (admin)",
)
async def update_case(case_id: int, updates: FeaturedCaseUpdate) -> dict:
    """Update case definition."""
    service = get_service()
    try:
        updated = await service.update_case(case_id, updates)
        return {"success": True, "data": updated.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete(
    "/admin/cases/{case_id}",
    summary="Delete case (admin)",
)
async def delete_case(case_id: int) -> dict:
    """Delete case definition."""
    service = get_service()
    try:
        await service.delete_case(case_id)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

- [ ] **Step 2: 验证 router 导入正常**

```bash
python -c "from swe.app.featured_case.router import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交路由变更**

```bash
git add src/swe/app/featured_case/router.py
git commit -m "refactor(router): use id instead of case_id in API paths"
```

---

### Task 6: 更新前端类型定义

**Files:**
- Modify: `console/src/api/types/featuredCases.ts`

- [ ] **Step 1: 更新类型定义**

移除 case_id 字段：

```typescript
/**
 * Featured Cases API types (simplified - no case_id)
 */

export interface CaseStep {
  title: string;
  content: string;
}

export interface CaseDetail {
  iframe_url: string;
  iframe_title: string;
  steps: CaseStep[];
}

export interface FeaturedCase {
  id: number;
  source_id: string;
  bbk_id?: string | null;
  label: string;
  value: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
  sort_order: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface FeaturedCaseCreate {
  bbk_id?: string | null;
  label: string;
  value: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
  sort_order?: number;
}

export interface FeaturedCaseUpdate {
  bbk_id?: string | null;
  label?: string;
  value?: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
  sort_order?: number;
  is_active?: boolean;
}

export interface FeaturedCaseListResponse {
  cases: FeaturedCase[];
  total: number;
}

// Display format (from /featured-cases endpoint)
export interface FeaturedCaseDisplay {
  id: number;
  label: string;
  value: string;
  image_url?: string;
  sort_order: number;
  detail?: CaseDetail;
}
```

- [ ] **Step 2: 提交类型变更**

```bash
git add console/src/api/types/featuredCases.ts
git commit -m "refactor(types): remove case_id from FeaturedCase types"
```

---

### Task 7: 更新前端 API 模块

**Files:**
- Modify: `console/src/api/modules/featuredCases.ts`

- [ ] **Step 1: 更新 API 模块**

使用 id 作为参数：

```typescript
/**
 * Featured Cases API module (simplified - no case_id)
 */
import { request } from "../request";
import type {
  FeaturedCase,
  FeaturedCaseCreate,
  FeaturedCaseUpdate,
  FeaturedCaseDisplay,
  FeaturedCaseListResponse,
} from "../types/featuredCases";

export const featuredCasesApi = {
  /** Get cases for current context (from X-Source-Id and X-Bbk-Id headers) */
  listCases: () => request<FeaturedCaseDisplay[]>("/featured-cases"),

  /** Get case detail by id */
  getCaseDetail: (id: number) =>
    request<FeaturedCase>(`/featured-cases/${id}`),

  // ==================== Admin endpoints ====================

  /** Admin: list cases for current source_id context */
  adminListCases: (params?: { bbk_id?: string; page?: number; page_size?: number }) => {
    const query = params
      ? new URLSearchParams(
          Object.entries(params)
            .filter(([_, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : "";
    return request<FeaturedCaseListResponse>(
      `/featured-cases/admin/cases${query ? `?${query}` : ""}`
    );
  },

  /** Admin: create case (source_id from header) */
  adminCreateCase: (caseItem: FeaturedCaseCreate) =>
    request<{ success: boolean; data: FeaturedCase }>(
      "/featured-cases/admin/cases",
      {
        method: "POST",
        body: JSON.stringify(caseItem),
      }
    ),

  /** Admin: update case */
  adminUpdateCase: (id: number, caseItem: FeaturedCaseUpdate) =>
    request<{ success: boolean; data: FeaturedCase }>(
      `/featured-cases/admin/cases/${id}`,
      {
        method: "PUT",
        body: JSON.stringify(caseItem),
      }
    ),

  /** Admin: delete case */
  adminDeleteCase: (id: number) =>
    request<{ success: boolean }>(
      `/featured-cases/admin/cases/${id}`,
      {
        method: "DELETE",
      }
    ),
};
```

- [ ] **Step 2: 提交 API 模块变更**

```bash
git add console/src/api/modules/featuredCases.ts
git commit -m "refactor(api): use id instead of case_id in featuredCases module"
```

---

### Task 8: 更新管理页面

**Files:**
- Modify: `console/src/pages/Control/FeaturedCases/index.tsx`
- Modify: `console/src/pages/Control/FeaturedCases/components/columns.tsx`
- Modify: `console/src/pages/Control/FeaturedCases/components/CaseDrawer.tsx`
- Modify: `console/src/pages/Control/FeaturedCases/components/hooks.ts`

- [ ] **Step 1: 更新 index.tsx**

将 case_id 改为 id，参数类型改为 number：

```typescript
import { useState, useEffect } from "react";
import { Button, Card, Table, Modal, Input } from "antd";
import { Form } from "@agentscope-ai/design";
import { PageHeader } from "@/components/PageHeader";
import { useFeaturedCases } from "./components/hooks";
import { createCaseColumns } from "./components/columns";
import { CaseDrawer } from "./components/CaseDrawer";
import type { FeaturedCase } from "@/api/types/featuredCases";
import styles from "./index.module.less";

function FeaturedCasesPage() {
  const { cases, loading, total, loadCases, createCase, updateCase, deleteCase } =
    useFeaturedCases();

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingCase, setEditingCase] = useState<FeaturedCase | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<FeaturedCase>();

  // Pagination
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
  });

  // Filter
  const [bbkIdFilter, setBbkIdFilter] = useState<string | undefined>(undefined);

  // Load data on mount
  useEffect(() => {
    loadCases({
      bbk_id: bbkIdFilter,
      page: pagination.current,
      page_size: pagination.pageSize,
    });
  }, [loadCases, pagination.current, pagination.pageSize, bbkIdFilter]);

  // ==================== Handlers ====================

  const handleCreate = () => {
    setEditingCase(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (caseItem: FeaturedCase) => {
    setEditingCase(caseItem);
    form.setFieldsValue(caseItem);
    setDrawerOpen(true);
  };

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: "确认删除",
      content: `确定要删除该案例吗？`,
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        await deleteCase(id);
        loadCases({
          bbk_id: bbkIdFilter,
          page: pagination.current,
          page_size: pagination.pageSize,
        });
      },
    });
  };

  const handleClose = () => {
    setDrawerOpen(false);
    setEditingCase(null);
  };

  const handleSubmit = async (values: FeaturedCase) => {
    setSaving(true);
    try {
      if (editingCase) {
        await updateCase(editingCase.id!, values);
      } else {
        await createCase(values);
      }
      setDrawerOpen(false);
      loadCases({
        bbk_id: bbkIdFilter,
        page: pagination.current,
        page_size: pagination.pageSize,
      });
    } catch (error) {
      // Error handled in hooks
    } finally {
      setSaving(false);
    }
  };

  const handleTableChange = (pag: { current?: number; pageSize?: number }) => {
    setPagination({
      current: pag.current || 1,
      pageSize: pag.pageSize || 20,
    });
  };

  // ==================== Columns ====================

  const columns = createCaseColumns({
    onEdit: handleEdit,
    onDelete: handleDelete,
  });

  return (
    <div className={styles.featuredCasesPage}>
      <PageHeader
        items={[{ title: "控制" }, { title: "精选案例管理" }]}
        extra={
          <Button type="primary" onClick={handleCreate}>
            + 新建案例
          </Button>
        }
      />

      <Card className={styles.tableCard}>
        <div style={{ marginBottom: 16 }}>
          <Input
            placeholder="筛选 BBK ID"
            allowClear
            value={bbkIdFilter || ""}
            onChange={(e) => {
              setBbkIdFilter(e.target.value || undefined);
              setPagination({ ...pagination, current: 1 });
            }}
            style={{ width: 200 }}
          />
        </div>

        <Table
          columns={columns}
          dataSource={cases}
          loading={loading}
          rowKey="id"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={handleTableChange}
        />
      </Card>

      <CaseDrawer
        open={drawerOpen}
        editingCase={editingCase}
        form={form}
        saving={saving}
        onClose={handleClose}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default FeaturedCasesPage;
```

- [ ] **Step 2: 更新 columns.tsx**

```typescript
import type { ColumnType } from "antd/es/table";
import type { FeaturedCase } from "@/api/types/featuredCases";

interface CreateCaseColumnsOptions {
  onEdit: (caseItem: FeaturedCase) => void;
  onDelete: (id: number) => void;
}

export function createCaseColumns({
  onEdit,
  onDelete,
}: CreateCaseColumnsOptions): ColumnType<FeaturedCase>[] {
  return [
    {
      title: "ID",
      dataIndex: "id",
      key: "id",
      width: 80,
    },
    {
      title: "BBK ID",
      dataIndex: "bbk_id",
      key: "bbk_id",
      width: 120,
      render: (bbkId: string | null) =>
        bbkId || <span style={{ color: "#999" }}>-</span>,
    },
    {
      title: "标题",
      dataIndex: "label",
      key: "label",
      ellipsis: true,
    },
    {
      title: "排序",
      dataIndex: "sort_order",
      key: "sort_order",
      width: 80,
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) =>
        active ? (
          <span style={{ color: "#52c41a" }}>启用</span>
        ) : (
          <span style={{ color: "#999" }}>禁用</span>
        ),
    },
    {
      title: "操作",
      key: "action",
      width: 120,
      render: (_, record) => (
        <span>
          <a onClick={() => onEdit(record)} style={{ marginRight: 12 }}>
            编辑
          </a>
          <a
            onClick={() => onDelete(record.id!)}
            style={{ color: "#ff4d4f" }}
          >
            删除
          </a>
        </span>
      ),
    },
  ];
}
```

- [ ] **Step 3: 更新 CaseDrawer.tsx**

移除 case_id 表单字段：

```typescript
import {
  Drawer,
  Form,
  Input,
  Switch,
  Button,
  InputNumber,
} from "@agentscope-ai/design";
import { MinusCircleOutlined, PlusOutlined } from "@ant-design/icons";
import type { FormInstance } from "antd";
import type { FeaturedCase, CaseStep } from "@/api/types/featuredCases";

interface CaseDrawerProps {
  open: boolean;
  editingCase: FeaturedCase | null;
  form: FormInstance<FeaturedCase>;
  saving: boolean;
  onClose: () => void;
  onSubmit: (values: FeaturedCase) => void;
}

const DEFAULT_CASE: Partial<FeaturedCase> = {
  is_active: true,
  bbk_id: "",
  iframe_url: "",
  iframe_title: "",
  steps: [],
  sort_order: 0,
};

export function CaseDrawer({
  open,
  editingCase,
  form,
  saving,
  onClose,
  onSubmit,
}: CaseDrawerProps) {
  return (
    <Drawer
      width={600}
      placement="right"
      title={editingCase ? "编辑案例" : "新建案例"}
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div style={{ display: "flex", gap: 8 }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            保存
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onSubmit}
        initialValues={DEFAULT_CASE}
      >
        {/* source_id NOT displayed - comes from X-Source-Id header */}

        <Form.Item name="bbk_id" label="BBK ID（可选）">
          <Input placeholder="如 bbk-001，留空表示默认配置" />
        </Form.Item>

        <Form.Item
          name="label"
          label="标题"
          rules={[{ required: true, message: "请输入标题" }]}
        >
          <Input.TextArea
            placeholder="案例卡片显示的标题"
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </Form.Item>

        <Form.Item
          name="value"
          label="提问内容"
          rules={[{ required: true, message: "请输入提问内容" }]}
        >
          <Input.TextArea
            placeholder="用户点击案例后的提问内容"
            autoSize={{ minRows: 2, maxRows: 6 }}
          />
        </Form.Item>

        <Form.Item name="image_url" label="图片 URL">
          <Input placeholder="https://..." />
        </Form.Item>

        <Form.Item name="sort_order" label="排序序号">
          <InputNumber min={0} placeholder="0" style={{ width: "100%" }} />
        </Form.Item>

        <Form.Item name="is_active" label="启用" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Form.Item name="iframe_url" label="iframe URL">
          <Input placeholder="https://..." />
        </Form.Item>

        <Form.Item name="iframe_title" label="iframe 标题">
          <Input placeholder="详情面板标题" />
        </Form.Item>

        {/* Steps */}
        <Form.Item label="步骤说明">
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <div
                    key={key}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      marginBottom: 12,
                      padding: 12,
                      background: "#f7f7fc",
                      borderRadius: 4,
                    }}
                  >
                    <Form.Item
                      {...restField}
                      name={[name, "title"]}
                      label="步骤标题"
                      rules={[{ required: true, message: "请输入步骤标题" }]}
                    >
                      <Input placeholder="步骤1：..." />
                    </Form.Item>
                    <Form.Item
                      {...restField}
                      name={[name, "content"]}
                      label="步骤内容"
                      rules={[{ required: true, message: "请输入步骤内容" }]}
                    >
                      <Input.TextArea
                        placeholder="步骤详细说明"
                        autoSize={{ minRows: 2, maxRows: 6 }}
                      />
                    </Form.Item>
                    <MinusCircleOutlined
                      onClick={() => remove(name)}
                      style={{ color: "#ff4d4f", cursor: "pointer" }}
                    />
                  </div>
                ))}
                <Button
                  type="dashed"
                  onClick={() => add({ title: "", content: "" } as CaseStep)}
                  block
                  icon={<PlusOutlined />}
                >
                  添加步骤
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>
      </Form>
    </Drawer>
  );
}
```

- [ ] **Step 4: 更新 hooks.ts**

```typescript
import { useState, useCallback } from "react";
import { featuredCasesApi } from "@/api/modules/featuredCases";
import type { FeaturedCase, FeaturedCaseCreate, FeaturedCaseUpdate } from "@/api/types/featuredCases";

export function useFeaturedCases() {
  const [cases, setCases] = useState<FeaturedCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  const loadCases = useCallback(
    async (params?: { bbk_id?: string; page?: number; page_size?: number }) => {
      setLoading(true);
      try {
        const data = await featuredCasesApi.adminListCases(params);
        setCases(data.cases);
        setTotal(data.total);
      } catch (error) {
        console.error("Failed to load cases:", error);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const createCase = useCallback(async (caseItem: FeaturedCaseCreate) => {
    try {
      const result = await featuredCasesApi.adminCreateCase(caseItem);
      return result.data;
    } catch (error) {
      console.error("Failed to create case:", error);
      throw error;
    }
  }, []);

  const updateCase = useCallback(
    async (id: number, caseItem: FeaturedCaseUpdate) => {
      try {
        const result = await featuredCasesApi.adminUpdateCase(id, caseItem);
        return result.data;
      } catch (error) {
        console.error("Failed to update case:", error);
        throw error;
      }
    },
    []
  );

  const deleteCase = useCallback(async (id: number) => {
    try {
      await featuredCasesApi.adminDeleteCase(id);
    } catch (error) {
      console.error("Failed to delete case:", error);
      throw error;
    }
  }, []);

  return {
    cases,
    loading,
    total,
    loadCases,
    createCase,
    updateCase,
    deleteCase,
  };
}
```

- [ ] **Step 5: 提交管理页面变更**

```bash
git add console/src/pages/Control/FeaturedCases/
git commit -m "refactor(console): remove case_id from FeaturedCases management page"
```

---

### Task 9: 更新展示组件

**Files:**
- Modify: `console/src/components/agentscope-chat/FeaturedCases/index.tsx`
- Modify: `console/src/components/agentscope-chat/CaseDetailDrawer/index.tsx`

- [ ] **Step 1: 更新 FeaturedCases/index.tsx**

使用 id 作为 key 和标识：

```typescript
import React, { useState, useEffect } from "react";
import Style from "./style";
import { featuredCasesApi } from "@/api/modules/featuredCases";

export interface FeaturedCase {
  id: number;
  label: string;
  value: string;
  image?: string;
}

export interface FeaturedCasesProps {
  cases?: FeaturedCase[];
  onFillInput?: (text: string) => void;
  onViewCase?: (id: number) => void;
}

function DocumentIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <rect x="7" y="3" width="5" height="18" rx="1" fill="currentColor" />
      <rect x="14" y="3" width="5" height="18" rx="1" fill="currentColor" />
      <rect x="7" y="3" width="12" height="1.5" fill="currentColor" />
    </svg>
  );
}

function MoreIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M4 6.667L8 11L12 6.667"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function KYCIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12.37" height="10.11" rx="1" fill="white" />
      <circle cx="5.07" cy="7.07" r="1.53" fill="white" />
      <rect x="7.9" y="9.17" width="4.2" height="2.5" rx="0.5" fill="white" />
      <rect
        x="7.07"
        y="4.63"
        width="3.31"
        height="1.04"
        rx="0.5"
        fill="white"
      />
      <rect x="9.6" y="6.21" width="2.74" height="1.04" rx="0.5" fill="white" />
    </svg>
  );
}

export default function FeaturedCases(props: FeaturedCasesProps) {
  const { onFillInput, onViewCase } = props;
  const [cases, setCases] = useState<FeaturedCase[]>([]);
  const [loading, setLoading] = useState(true);

  // Load cases from API on mount
  useEffect(() => {
    const loadCases = async () => {
      try {
        const apiCases = await featuredCasesApi.listCases();
        const featuredCases: FeaturedCase[] = apiCases.map((c) => ({
          id: c.id,
          label: c.label,
          value: c.value,
          image: c.image_url,
        }));
        setCases(featuredCases);
      } catch (error) {
        console.error("Failed to load cases:", error);
        setCases([]);
      } finally {
        setLoading(false);
      }
    };

    loadCases();
  }, []);

  const handleCardClick = (caseItem: FeaturedCase) => {
    onFillInput?.(caseItem.value);
  };

  const handleViewCase = (e: React.MouseEvent, caseItem: FeaturedCase) => {
    e.stopPropagation();
    onViewCase?.(caseItem.id);
  };

  const handleUseSame = (e: React.MouseEvent, caseItem: FeaturedCase) => {
    e.stopPropagation();
    onFillInput?.(caseItem.value);
  };

  if (loading) {
    return (
      <>
        <Style />
        <div className="featured-cases">
          <div className="featured-cases-header">
            <div className="featured-cases-title">
              <span className="featured-cases-title-icon">
                <DocumentIcon />
              </span>
              精选案例
            </div>
          </div>
          <div className="featured-cases-scroll">
            <div className="featured-cases-loading">加载中...</div>
          </div>
        </div>
      </>
    );
  }

  if (cases.length === 0) {
    return null;
  }

  return (
    <>
      <Style />
      <div className="featured-cases">
        <div className="featured-cases-header">
          <div className="featured-cases-title">
            <span className="featured-cases-title-icon">
              <DocumentIcon />
            </span>
            精选案例
          </div>
          {cases.length > 5 && (
            <div className="featured-cases-more">
              查看更多
              <MoreIcon />
            </div>
          )}
        </div>
        <div className="featured-cases-scroll">
          {cases.map((caseItem) => (
            <div
              key={caseItem.id}
              className="featured-cases-card"
              onClick={() => handleCardClick(caseItem)}
              role="button"
              tabIndex={0}
            >
              {caseItem.image && (
                <img
                  className="featured-cases-card-image"
                  src={caseItem.image}
                  alt=""
                />
              )}
              <div className="featured-cases-card-text">{caseItem.label}</div>
              <div className="featured-cases-overlay">
                <button
                  className="featured-cases-overlay-btn"
                  onClick={(e) => handleViewCase(e, caseItem)}
                  type="button"
                >
                  <span className="featured-cases-overlay-btn-icon">
                    <KYCIcon />
                  </span>
                  看案例
                </button>
                <button
                  className="featured-cases-overlay-btn"
                  onClick={(e) => handleUseSame(e, caseItem)}
                  type="button"
                >
                  <span className="featured-cases-overlay-btn-icon">
                    <KYCIcon />
                  </span>
                  做同款
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: 更新 CaseDetailDrawer/index.tsx**

id 类型改为 number：

```typescript
import { useState } from "react";
import { Drawer, Spin } from "antd";
import Style from "./style";
import type { FeaturedCase, CaseStep } from "@/api/types/featuredCases";

export interface CaseDetailDrawerProps {
  visible: boolean;
  onClose: () => void;
  caseData: FeaturedCase | null;
  loading?: boolean;
  onMakeSimilar?: (value: string) => void;
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path
        d="M1 1L13 13M13 1L1 13"
        stroke="#999999"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SubscribeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M8 4.5V8.5L10.5 10"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function NewSessionIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M8 3V13M3 8H13"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M2 8C2 4.68629 4.68629 2 8 2C11.3137 2 14 4.68629 14 8C14 11.3137 11.3137 14 8 14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M14 2L14 5.5L10.5 5.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function CaseDetailDrawer({
  visible,
  onClose,
  caseData,
  loading = false,
  onMakeSimilar,
}: CaseDetailDrawerProps) {
  const [iframeLoading, setIframeLoading] = useState(true);
  const [iframeError, setIframeError] = useState(false);

  const handleMakeSimilar = () => {
    if (caseData) {
      onMakeSimilar?.(caseData.value);
    }
    onClose();
  };

  const handleIframeLoad = () => {
    setIframeLoading(false);
    setIframeError(false);
  };

  const handleIframeError = () => {
    setIframeLoading(false);
    setIframeError(true);
  };

  const handleRefreshIframe = () => {
    setIframeLoading(true);
    setIframeError(false);
    const iframe = document.querySelector(
      ".case-detail-drawer-iframe",
    ) as HTMLIFrameElement;
    if (iframe && caseData?.iframe_url) {
      iframe.src = caseData.iframe_url;
    }
  };

  const steps: CaseStep[] = caseData?.steps || [];
  const iframeUrl = caseData?.iframe_url || "";
  const iframeTitle = caseData?.iframe_title || "详情";

  return (
    <>
      <Style />
      <Drawer
        className="case-detail-drawer"
        placement="bottom"
        open={visible}
        onClose={onClose}
        height="90%"
        closable={false}
        maskClosable
        styles={{
          body: { padding: 0, overflow: "hidden" },
        }}
      >
        {/* Header */}
        <div className="case-detail-drawer-header">
          <span className="case-detail-drawer-title">
            {loading ? "加载中..." : caseData?.label || "案例详情"}
          </span>
          <button
            className="case-detail-drawer-close"
            onClick={onClose}
            type="button"
          >
            <CloseIcon />
          </button>
        </div>

        {/* Body - Left/Right split */}
        {loading ? (
          <div className="case-detail-drawer-loading-body">
            <Spin size="large" />
          </div>
        ) : (
          <div className="case-detail-drawer-body">
            {/* Left: Steps */}
            <div className="case-detail-drawer-steps-panel">
              {steps.length === 0 ? (
                <div className="case-detail-drawer-empty">
                  暂无步骤说明
                </div>
              ) : (
                steps.map((step, i) => (
                  <div key={i} className="case-detail-drawer-step">
                    <div className="case-detail-drawer-step-title">
                      {step.title}
                    </div>
                    <div className="case-detail-drawer-step-content">
                      {step.content}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Right: iframe */}
            <div className="case-detail-drawer-iframe-panel">
              <div className="case-detail-drawer-iframe-title">
                {iframeTitle}
              </div>
              <div className="case-detail-drawer-iframe-container">
                {iframeLoading && !iframeError && (
                  <div className="case-detail-drawer-iframe-loading">
                    <Spin />
                    <span>加载中...</span>
                  </div>
                )}
                {iframeError && (
                  <div className="case-detail-drawer-iframe-error">
                    <span>页面加载失败</span>
                    <button
                      className="case-detail-drawer-iframe-refresh"
                      onClick={handleRefreshIframe}
                      type="button"
                    >
                      <RefreshIcon />
                      重新加载
                    </button>
                  </div>
                )}
                {iframeUrl && (
                  <iframe
                    className="case-detail-drawer-iframe"
                    src={iframeUrl}
                    title={iframeTitle}
                    sandbox="allow-scripts allow-same-origin allow-forms"
                    onLoad={handleIframeLoad}
                    onError={handleIframeError}
                    loading="lazy"
                  />
                )}
                {!iframeUrl && (
                  <div className="case-detail-drawer-iframe-empty">
                    暂无详情页面
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="case-detail-drawer-footer">
          <button
            className="case-detail-drawer-footer-btn"
            type="button"
            onClick={() => {
              /* TODO: subscribe as scheduled task */
            }}
          >
            <SubscribeIcon />
            订阅为定时任务
          </button>
          <button
            className="case-detail-drawer-footer-btn case-detail-drawer-footer-btn--primary"
            type="button"
            onClick={handleMakeSimilar}
            disabled={!caseData}
          >
            <NewSessionIcon />
            做同款
          </button>
        </div>
      </Drawer>
    </>
  );
}
```

- [ ] **Step 3: 提交展示组件变更**

```bash
git add console/src/components/agentscope-chat/FeaturedCases/
git add console/src/components/agentscope-chat/CaseDetailDrawer/
git commit -m "refactor(console): use id instead of case_id in display components"
```

---

### Task 10: 修复测试代码

**Files:**
- Modify: `tests/unit/app/test_featured_case.py`

- [ ] **Step 1: 重写测试文件**

移除 CaseConfigCreate/CaseConfigItem 相关测试，更新所有测试使用 id：

```python
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
    async def test_get_cases_for_dimension_with_null_bbk_id(self, store, mock_db):
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
        cases, total = await store.list_cases(source_id="source1", page=1, page_size=10)
        assert total == 10
        assert len(cases) == 1

    @pytest.mark.asyncio
    async def test_create_case_with_db(self, store, mock_db):
        """Test create_case with database."""
        case = FeaturedCase(
            label="案例",
            value="内容",
            steps=[CaseStep(title="步骤1", content="内容1")],
            is_active=True,
            source_id="source1",
        )
        result = await store.create_case(case)
        mock_db.execute.assert_called_once()
        assert result.label == "案例"

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
```

- [ ] **Step 2: 运行测试验证**

```bash
python -m pytest tests/unit/app/test_featured_case.py -v
```

Expected: All tests pass

- [ ] **Step 3: 提交测试变更**

```bash
git add tests/unit/app/test_featured_case.py
git commit -m "fix(tests): update featured_case tests for simplified model"
```

---

### Task 11: 最终验证与提交

- [ ] **Step 1: 运行完整测试套件**

```bash
python -m pytest tests/unit/app/test_featured_case.py -v
```

Expected: All tests pass

- [ ] **Step 2: 验证前端构建**

```bash
cd console && npm run build
```

Expected: Build succeeds

- [ ] **Step 3: 更新原设计文档**

在 `docs/superpowers/specs/2026-04-18-content-config-management-design.md` 顶部添加变更说明：

```markdown
> **注意**: 本文档已过时。请参考 [2026-04-27-featured-case-simplify-design.md](./2026-04-27-featured-case-simplify-design.md) 获取最新设计。
```

- [ ] **Step 4: 最终提交**

```bash
git add docs/superpowers/specs/2026-04-18-content-config-management-design.md
git commit -m "docs: mark original design as superseded"
```

---

## 自查清单

| 检查项 | 状态 |
|--------|------|
| Spec 覆盖 | ✅ 所有变更点都有对应任务 |
| 无占位符 | ✅ 所有代码块完整 |
| 类型一致性 | ✅ id 类型统一为 number/int |
