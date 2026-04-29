# -*- coding: utf-8 -*-
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """健康检查."""
    return {"status": "ok"}


@router.get("/version")
def get_version():
    """获取版本信息."""
    from ...__version__ import __version__

    return {"version": __version__}
