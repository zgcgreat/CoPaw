import pytest

from swe.app.runner.shared_run_coordinator import (
    RunOwnedByAnotherInstanceError,
)


@pytest.mark.asyncio
async def test_remote_owner_conflict_is_logged_and_ignored():
    from swe.app.channels.base import BaseChannel

    async def _get_or_create_chat(*_args, **_kwargs):
        return type(
            "Chat",
            (),
            {
                "id": "chat-1",
                "session_id": "console:alice",
                "user_id": "alice",
                "channel": "console",
            },
        )()

    async def _attach_or_start(*_args, **_kwargs):
        raise RunOwnedByAnotherInstanceError(
            "chat-1",
            "pod-a:123",
        )

    channel = BaseChannel.__new__(BaseChannel)
    channel.channel = "console"
    channel._workspace = type(
        "Workspace",
        (),
        {
            "chat_manager": type(
                "ChatManager",
                (),
                {
                    "get_or_create_chat": staticmethod(_get_or_create_chat),
                },
            )(),
            "task_tracker": type(
                "Tracker",
                (),
                {
                    "attach_or_start": staticmethod(_attach_or_start),
                },
            )(),
        },
    )()
    channel._extract_chat_name = lambda _payload: "Test"
    channel._stream_with_tracker = lambda _payload: None

    request = type(
        "Request",
        (),
        {
            "session_id": "console:alice",
            "user_id": "alice",
            "channel": "console",
        },
    )()

    await BaseChannel._consume_with_tracker(
        channel,
        request,
        {"content_parts": []},
    )
