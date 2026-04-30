# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import sys

import click

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

logger = logging.getLogger(__name__)


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(
    version="1.0.0",
    prog_name="Monitor",
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Monitor 运维工程 CLI."""
    ctx.ensure_object(dict)


@cli.command()
@click.option("--host", default="127.0.0.1", help="服务监听地址")
@click.option("--port", default=9090, type=int, help="服务监听端口")
@click.option("--reload", is_flag=True, help="开发模式，自动重载")
def app_cmd(host: str, port: int, reload: bool) -> None:
    """启动 Monitor 服务."""
    import uvicorn

    logger.info(f"Starting Monitor service on {host}:{port}")
    uvicorn.run(
        "monitor.app._app:app",
        host=host,
        port=port,
        reload=reload,
    )
