# -*- coding: utf-8 -*-
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from ...app.deps import DbDep
from ...marketplace.models import CategoryItem

router = APIRouter()


@router.get("/marketplace/categories", response_model=list[CategoryItem])
async def get_categories(
    db: DbDep,
    x_source_id: Optional[str] = Header(default=None, alias="X-Source-Id"),
):
    """获取当前 source-id 下的分类列表，按 sort_order 升序."""
    if not x_source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header is required",
        )
    if not db.is_connected:
        raise HTTPException(status_code=503, detail="Database unavailable")

    rows = await db.fetch_all(
        "SELECT id, source_id, name, sort_order, created_at "
        "FROM swe_marketplace_categories "
        "WHERE source_id = %s ORDER BY sort_order ASC",
        (x_source_id,),
    )
    return [CategoryItem(**row) for row in rows]
