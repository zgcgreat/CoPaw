# -*- coding: utf-8 -*-
from fastapi import APIRouter

from .categories import router as categories_router
from .health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(categories_router, tags=["marketplace"])
