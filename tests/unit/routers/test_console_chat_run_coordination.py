from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.routers.console import router as console_router
from swe.app.runner.shared_run_coordinator import (
    RunOwnedByAnotherInstanceError,
    SharedRunCoordinationError,
)


class FakeTracker:
    def __init__(self):
        self.owner = "pod-a:123"
        self.stopped = False

    async def attach(self, _run_key):
        return None

    async def attach_or_start(self, _run_key, _payload, _stream_fn):
        return None, True

    async def get_owner(self, _run_key):
        return self.owner

    async def request_stop(self, _run_key):
        self.stopped = True
        return True


class FakeChatManager:
    async def get_or_create_chat(self, *_args, **_kwargs):
        return SimpleNamespace(
            id="chat-1",
            session_id="console:alice",
            user_id="alice",
            channel="console",
        )


class FakeConsoleChannel:
    channel = "console"

    def resolve_session_id(self, sender_id, channel_meta):
        del sender_id
        return channel_meta["session_id"]

    async def stream_one(self, payload):
        yield payload


class FakeChannelManager:
    async def get_channel(self, _name):
        return FakeConsoleChannel()


@pytest.fixture
def console_client(monkeypatch):
    tracker = FakeTracker()
    workspace = SimpleNamespace(
        task_tracker=tracker,
        chat_manager=FakeChatManager(),
        channel_manager=FakeChannelManager(),
    )

    async def _get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        "swe.app.routers.console.get_agent_for_request",
        _get_agent_for_request,
    )

    app = FastAPI()
    app.include_router(console_router, prefix="/api")
    return TestClient(app)


def test_reconnect_returns_409_when_run_is_owned_elsewhere(console_client):
    response = console_client.post(
        "/api/console/chat",
        json={
            "channel": "console",
            "user_id": "alice",
            "session_id": "console:alice",
            "reconnect": True,
            "input": [],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "chat_running_on_another_instance"
    )
    assert response.json()["detail"]["owner_instance_id"] == "pod-a:123"


def test_chat_post_returns_409_when_run_is_owned_elsewhere(monkeypatch):
    class RemoteOwnerTracker(FakeTracker):
        async def attach_or_start(
            self,
            _run_key,
            _payload,
            _stream_fn,
            **_kwargs,
        ):
            raise RunOwnedByAnotherInstanceError(
                "chat-1",
                "pod-a:123",
            )

    workspace = SimpleNamespace(
        task_tracker=RemoteOwnerTracker(),
        chat_manager=FakeChatManager(),
        channel_manager=FakeChannelManager(),
    )

    async def _get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        "swe.app.routers.console.get_agent_for_request",
        _get_agent_for_request,
    )

    app = FastAPI()
    app.include_router(console_router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/console/chat",
        json={
            "channel": "console",
            "user_id": "alice",
            "session_id": "console:alice",
            "input": [],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "chat_running_on_another_instance",
        "chat_id": "chat-1",
        "owner_instance_id": "pod-a:123",
    }


def test_chat_post_returns_503_when_shared_coordination_is_unavailable(
    monkeypatch,
):
    class UnavailableTracker(FakeTracker):
        async def attach_or_start(
            self,
            _run_key,
            _payload,
            _stream_fn,
            **_kwargs,
        ):
            raise SharedRunCoordinationError(
                "shared run coordination unavailable",
            )

    workspace = SimpleNamespace(
        task_tracker=UnavailableTracker(),
        chat_manager=FakeChatManager(),
        channel_manager=FakeChannelManager(),
    )

    async def _get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        "swe.app.routers.console.get_agent_for_request",
        _get_agent_for_request,
    )

    app = FastAPI()
    app.include_router(console_router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/console/chat",
        json={
            "channel": "console",
            "user_id": "alice",
            "session_id": "console:alice",
            "input": [],
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "shared run coordination unavailable",
    }


def test_stop_returns_shared_cancellation_result(console_client):
    response = console_client.post(
        "/api/console/chat/stop",
        params={"chat_id": "chat-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"stopped": True}


def test_stop_returns_503_when_shared_coordination_is_unavailable(monkeypatch):
    class UnavailableTracker(FakeTracker):
        async def request_stop(self, _run_key):
            raise SharedRunCoordinationError(
                "shared run coordination unavailable",
            )

    workspace = SimpleNamespace(
        task_tracker=UnavailableTracker(),
        chat_manager=FakeChatManager(),
        channel_manager=FakeChannelManager(),
    )

    async def _get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        "swe.app.routers.console.get_agent_for_request",
        _get_agent_for_request,
    )

    app = FastAPI()
    app.include_router(console_router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/console/chat/stop",
        params={"chat_id": "chat-1"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "shared run coordination unavailable",
    }


def test_reconnect_returns_503_when_owner_lookup_is_unavailable(monkeypatch):
    class UnavailableTracker(FakeTracker):
        async def get_owner(self, _run_key):
            raise SharedRunCoordinationError(
                "shared run coordination unavailable",
            )

    workspace = SimpleNamespace(
        task_tracker=UnavailableTracker(),
        chat_manager=FakeChatManager(),
        channel_manager=FakeChannelManager(),
    )

    async def _get_agent_for_request(_request):
        return workspace

    monkeypatch.setattr(
        "swe.app.routers.console.get_agent_for_request",
        _get_agent_for_request,
    )

    app = FastAPI()
    app.include_router(console_router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/console/chat",
        json={
            "channel": "console",
            "user_id": "alice",
            "session_id": "console:alice",
            "reconnect": True,
            "input": [],
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "shared run coordination unavailable",
    }
