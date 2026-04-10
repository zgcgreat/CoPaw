# -*- coding: utf-8 -*-
"""SQLAlchemy schema for durable chat control storage."""
from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON

CONTROL_STORE_METADATA = MetaData()

chat_specs_table = Table(
    "chat_specs",
    CONTROL_STORE_METADATA,
    Column("tenant_id", String(255), primary_key=True),
    Column("agent_id", String(255), primary_key=True),
    Column("chat_id", String(255), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("session_id", String(255), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("channel", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("meta", SQLITE_JSON, nullable=False),
    Column("status", String(64), nullable=False),
    UniqueConstraint(
        "tenant_id",
        "agent_id",
        "session_id",
        "user_id",
        "channel",
        name="uq_chat_specs_scope_session",
    ),
)

chat_runs_table = Table(
    "chat_runs",
    CONTROL_STORE_METADATA,
    Column("tenant_id", String(255), primary_key=True),
    Column("agent_id", String(255), primary_key=True),
    Column("run_id", String(255), primary_key=True),
    Column("chat_id", String(255), nullable=False),
    Column("status", String(64), nullable=False),
    Column("session_id", String(255), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("channel", String(255), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error", String, nullable=True),
)

session_checkpoints_table = Table(
    "session_checkpoints",
    CONTROL_STORE_METADATA,
    Column("tenant_id", String(255), primary_key=True),
    Column("agent_id", String(255), primary_key=True),
    Column("user_id", String(255), primary_key=True),
    Column("session_id", String(255), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("blob_path", String, nullable=False),
    Column("payload_sha256", String(64), nullable=False),
)
