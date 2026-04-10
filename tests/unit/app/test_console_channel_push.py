# -*- coding: utf-8 -*-
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_send_passes_workspace_tenant_id(monkeypatch, tmp_path):
    from swe.app.channels.console.channel import ConsoleChannel

    calls = []

    async def fake_append(session_id, text, *, sticky=False, tenant_id=None):
        calls.append(
            {
                "session_id": session_id,
                "text": text,
                "sticky": sticky,
                "tenant_id": tenant_id,
            },
        )

    monkeypatch.setattr(
        "swe.app.channels.console.channel.push_store_append",
        fake_append,
    )

    channel = ConsoleChannel(
        process=lambda request: None,
        enabled=True,
        bot_prefix="",
        workspace_dir=Path(tmp_path),
    )
    channel.set_workspace(
        SimpleNamespace(
            tenant_id="tenant-a",
            workspace_dir=Path(tmp_path),
        ),
    )

    await channel.send("user-a", "hello", meta={"session_id": "session-a"})

    assert calls == [
        {
            "session_id": "session-a",
            "text": "hello",
            "sticky": False,
            "tenant_id": "tenant-a",
        },
    ]


@pytest.mark.asyncio
async def test_send_content_parts_passes_workspace_tenant_id(
    monkeypatch,
    tmp_path,
):
    from swe.app.channels.console.channel import ConsoleChannel, ContentType

    calls = []

    async def fake_append(session_id, text, *, sticky=False, tenant_id=None):
        calls.append(
            {
                "session_id": session_id,
                "text": text,
                "sticky": sticky,
                "tenant_id": tenant_id,
            },
        )

    monkeypatch.setattr(
        "swe.app.channels.console.channel.push_store_append",
        fake_append,
    )

    channel = ConsoleChannel(
        process=lambda request: None,
        enabled=True,
        bot_prefix="BOT:",
        workspace_dir=Path(tmp_path),
    )
    channel.set_workspace(
        SimpleNamespace(
            tenant_id="tenant-a",
            workspace_dir=Path(tmp_path),
        ),
    )

    await channel.send_content_parts(
        "user-a",
        [SimpleNamespace(type=ContentType.TEXT, text="hello")],
        meta={"session_id": "session-a"},
    )

    assert calls == [
        {
            "session_id": "session-a",
            "text": "BOT:  hello",
            "sticky": False,
            "tenant_id": "tenant-a",
        },
    ]
