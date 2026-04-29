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
        """Get cases for display on chat page (top 5).

        Logic:
        - bbk_id is None or "100" (total branch): return all active cases for source_id
        - bbk_id is non-100: return specified bbk_id cases + default (bbk_id="100") cases,
          with specified bbk_id cases first

        Limited to top 5 results.

        Args:
            source_id: Source identifier
            bbk_id: BBK identifier (optional)

        Returns:
            List of case dicts for display (max 5 items)
        """
        if not self._use_db:
            return []

        DEFAULT_BBK_ID = "100"

        if bbk_id is None or bbk_id == DEFAULT_BBK_ID:
            # Total branch or no filter - return all active cases for source_id
            query = """
                SELECT id, label, value, image_url,
                       iframe_url, iframe_title, steps, sort_order
                FROM swe_featured_case
                WHERE source_id = %s AND is_active = 1
                ORDER BY sort_order ASC
                LIMIT 5
            """
            rows = await self.db.fetch_all(query, (source_id,))
        else:
            # Query both specified bbk_id and default (bbk_id="100")
            # Sort: specified bbk_id first, then default
            query = """
                SELECT id, label, value, image_url,
                       iframe_url, iframe_title, steps, sort_order
                FROM swe_featured_case
                WHERE source_id = %s
                  AND (bbk_id <=> %s OR bbk_id <=> %s)
                  AND is_active = 1
                ORDER BY
                    CASE WHEN bbk_id <=> %s THEN 0 ELSE 1 END,
                    sort_order ASC
                LIMIT 5
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, bbk_id, DEFAULT_BBK_ID, bbk_id),
            )

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
        """List cases for a specific source_id.

        Logic:
        - bbk_id is None or "100" (total branch): return all cases for source_id
        - bbk_id is non-100: return specified bbk_id cases + default (bbk_id="100") cases,
          with specified bbk_id cases first

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

        DEFAULT_BBK_ID = "100"

        if bbk_id is None or bbk_id == DEFAULT_BBK_ID:
            # Total branch or no filter - return all cases for source_id
            where_sql = "source_id = %s"
            where_params: list = [source_id]
            order_sql = "sort_order ASC, created_at DESC"
            order_params: list = []
        else:
            # Query both specified bbk_id and default (bbk_id="100")
            where_sql = "source_id = %s AND (bbk_id <=> %s OR bbk_id <=> %s)"
            where_params = [source_id, bbk_id, DEFAULT_BBK_ID]
            # Sort: specified bbk_id first, then default
            order_sql = "CASE WHEN bbk_id <=> %s THEN 0 ELSE 1 END, sort_order ASC, created_at DESC"
            order_params = [bbk_id]

        # Count query only uses where_params
        count_query = f"SELECT COUNT(*) as total FROM swe_featured_case WHERE {where_sql}"
        count_row = await self.db.fetch_one(count_query, tuple(where_params))
        total = count_row["total"] if count_row else 0

        offset = (page - 1) * page_size
        query = f"""
            SELECT * FROM swe_featured_case
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT %s OFFSET %s
        """
        params = where_params + order_params + [page_size, offset]
        rows = await self.db.fetch_all(query, tuple(params))
        cases = [self._row_to_case(row) for row in rows]
        return cases, total

    async def create_case(self, case: FeaturedCase) -> FeaturedCase:
        """Create case with auto-increment sort_order.

        Sort order is automatically set to max(sort_order) + 1 for the
        current dimension (source_id + bbk_id).
        First case starts at sort_order=1.

        Args:
            case: FeaturedCase to create

        Returns:
            Created FeaturedCase
        """
        if self._use_db:
            # Get max sort_order for current dimension
            # COALESCE with 0 means first case gets sort_order=1
            max_query = """
                SELECT COALESCE(MAX(sort_order), 0) as max_order
                FROM swe_featured_case
                WHERE source_id = %s AND bbk_id <=> %s
            """
            max_row = await self.db.fetch_one(
                max_query,
                (case.source_id, case.bbk_id),
            )
            next_order = (max_row["max_order"] if max_row else 0) + 1

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
                    next_order,
                    int(case.is_active),
                ),
            )
            case.sort_order = next_order
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
