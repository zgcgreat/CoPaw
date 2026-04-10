from types import SimpleNamespace

import pytest

from swe.app.runner.api import get_chat, list_chats
from swe.app.runner.models import ChatSpec


class FakeChatManager:
    def __init__(self, chat_spec):
        self.chat_spec = chat_spec

    async def list_chats(self, **_kwargs):
        return [self.chat_spec]

    async def get_chat(self, chat_id):
        return self.chat_spec if chat_id == self.chat_spec.id else None


class FakeSession:
    async def get_session_state_dict(self, *_args, **_kwargs):
        return {}


class FakeTracker:
    async def get_status(self, _chat_id):
        return "running"


@pytest.mark.asyncio
async def test_list_chats_reads_shared_running_status():
    chat = ChatSpec(
        id="chat-1",
        name="Test",
        session_id="console:alice",
        user_id="alice",
        channel="console",
    )
    workspace = SimpleNamespace(task_tracker=FakeTracker())

    result = await list_chats(
        mgr=FakeChatManager(chat),
        workspace=workspace,
    )

    assert result[0].status == "running"


@pytest.mark.asyncio
async def test_get_chat_reads_shared_running_status():
    chat = ChatSpec(
        id="chat-1",
        name="Test",
        session_id="console:alice",
        user_id="alice",
        channel="console",
    )
    workspace = SimpleNamespace(task_tracker=FakeTracker())
    session = FakeSession()

    result = await get_chat(
        chat_id="chat-1",
        mgr=FakeChatManager(chat),
        session=session,
        workspace=workspace,
    )

    assert result.status == "running"
