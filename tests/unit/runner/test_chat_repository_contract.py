import pytest

from swe.app.runner.models import ChatSpec
from swe.app.runner.repo.json_repo import JsonChatRepository


@pytest.mark.asyncio
async def test_json_repo_implements_entity_contract(tmp_path):
    repo = JsonChatRepository(tmp_path / "chats.json")
    spec = ChatSpec(
        id="chat-1",
        name="Alpha",
        session_id="console:alice",
        user_id="alice",
        channel="console",
    )

    await repo.upsert_chat(spec)

    fetched = await repo.get_chat_by_session(
        "console:alice",
        "alice",
        "console",
    )
    assert fetched is not None
    assert fetched.id == "chat-1"
