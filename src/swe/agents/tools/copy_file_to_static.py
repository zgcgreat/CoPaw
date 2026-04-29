# -*- coding: utf-8 -*-
"""copy file to static folder tool."""

import json
import shutil
import os

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from ...app.agent_context import get_current_agent_id
from ...config.context import get_current_user_id, get_current_workspace_dir


def _tool_error(msg: str) -> ToolResponse:
    """Return error response."""
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=json.dumps(
                    {"ok": False, "error": msg},
                    ensure_ascii=False,
                    indent=2,
                ),
            ),
        ],
    )


def _tool_ok(path: str, message: str) -> ToolResponse:
    """Return success response."""
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=json.dumps(
                    {
                        "ok": True,
                        "path": path,
                        "message": message,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ),
        ],
    )


async def copy_file_to_static(file_path: str) -> ToolResponse:
    """copy a file to the static folder under the working directory.

    This tool copys the specified file to the `static` subdirectory of the
    current working directory. If the `static` folder does not exist, it
    will be created automatically.

    Args:
        file_path (`str`):
            The absolute or relative path of the file to copy.

    Returns:
        `ToolResponse`:
            JSON with "ok", a markdown link accessible to the user.
    """
    # Validate input
    if not file_path or not file_path.strip():
        return _tool_error("file_path is required")

    file_path = file_path.strip()

    # Check if source file exists
    if not os.path.exists(file_path):
        return _tool_error(f"File not found: {file_path}")

    if not os.path.isfile(file_path):
        return _tool_error(f"Path is not a file: {file_path}")

    # Get working directory and create static folder if needed
    working_dir = get_current_workspace_dir()
    if working_dir is None:
        return _tool_error("workspace directory is not configured")
    static_dir = working_dir / "static"

    try:
        static_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return _tool_error(f"Failed to create static directory: {e!s}")

    # Build destination path
    file_name = os.path.basename(file_path)
    dest_path = static_dir / file_name

    # If destination already exists, add a suffix to avoid collision
    if dest_path.exists():
        base, ext = os.path.splitext(file_name)
        counter = 1
        while dest_path.exists():
            dest_path = static_dir / f"{base}_{counter}{ext}"
            counter += 1
    # copy the file
    try:
        # 行内手工代码,移动文件改为复制文件
        # shutil.copy(file_path, dest_path)
        shutil.copy(file_path, dest_path)
    except Exception as e:
        return _tool_error(f"Failed to copy file: {e!s}")

    # Get user_id for response
    user_id = get_current_user_id() or "default"
    file_name = os.path.basename(dest_path)
    agent_id = get_current_agent_id()
    access = os.getenv("FILE_URL", "http://localhost:8088")
    url = access + "/static/" + user_id + "/" + agent_id + "/" + file_name

    return _tool_ok(
        f"![{file_name}]({url})",
        "已返回markdown格式的访问链接",
    )
