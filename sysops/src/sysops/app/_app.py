# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..__version__ import __version__
from ..config.constant import DOCS_ENABLED, CORS_ORIGINS
from .routers import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(
    fastapi_app: FastAPI,
):  # pylint: disable=redefined-outer-name,unused-argument
    """应用生命周期管理."""
    logger.info("SysOps service starting up...")
    logger.info(f"Environment: {os.environ.get('SYSOPS_ENV', 'prd')}")
    yield
    logger.info("SysOps service shutting down...")


app = FastAPI(
    title="SysOps",
    description="系统运维管理服务",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)

if CORS_ORIGINS:
    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/api")
