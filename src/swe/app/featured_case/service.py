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
