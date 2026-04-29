# -*- coding: utf-8 -*-
"""SysOps 运维工程简单入口。

Usage:
    python main.py                  # 默认启动
    python main.py --port 9090      # 指定端口
    python main.py --host 0.0.0.0 --port 9090
"""
import argparse
import sys
from pathlib import Path
import uvicorn

# 将 src 目录添加到 Python 路径，支持直接运行
_src_dir = Path(__file__).resolve().parent / "src"
if _src_dir.exists() and str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


def main():
    parser = argparse.ArgumentParser(
        description="SysOps 运维服务启动入口",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="服务监听地址",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="服务监听端口",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发模式，自动重载",
    )
    args = parser.parse_args()

    uvicorn.run(
        "sysops.app._app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
