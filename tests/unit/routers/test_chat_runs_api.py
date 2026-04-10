from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.runner.api import router
from swe.app.runner.models import ChatSpec
from swe.app.runner.run_models import ChatRunRecord


class FakeManager:
    async def get_chat(self, chat_id):
        if chat_id != "chat-1":
            return None
        return ChatSpec(
            id="chat-1",
            name="Alpha",
            session_id="console:alice",
            user_id="alice",
            channel="console",
        )

    async def list_runs(self, chat_id, limit=20):
        return [
            ChatRunRecord(
                id="run-1",
                chat_id=chat_id,
                status="completed",
                session_id="console:alice",
                user_id="alice",
                channel="console",
            ),
        ]


def test_list_chat_runs_returns_durable_run_records(monkeypatch):
    workspace = SimpleNamespace(chat_manager=FakeManager())

    async def _get_workspace(_request):
        return workspace

    monkeypatch.setattr("swe.app.runner.api.get_workspace", _get_workspace)

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/chats/chat-1/runs")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "run-1",
            "chat_id": "chat-1",
            "status": "completed",
            "session_id": "console:alice",
            "user_id": "alice",
            "channel": "console",
            "started_at": response.json()[0]["started_at"],
            "finished_at": None,
            "error": None,
        },
    ]


def test_list_chat_runs_returns_404_for_unknown_chat(monkeypatch):
    workspace = SimpleNamespace(chat_manager=FakeManager())

    async def _get_workspace(_request):
        return workspace

    monkeypatch.setattr("swe.app.runner.api.get_workspace", _get_workspace)

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/chats/missing/runs")

    assert response.status_code == 404
    assert response.json() == {"detail": "Chat not found: missing"}
