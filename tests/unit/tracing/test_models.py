# -*- coding: utf-8 -*-
"""Tests for tracing data models."""

from datetime import datetime

from swe.tracing.models import (
    EventType,
    Span,
    Trace,
    TraceStatus,
    ModelUsage,
    ToolUsage,
    SkillUsage,
    MCPToolUsage,
    MCPServerUsage,
    DailyStats,
    OverviewStats,
    UserStats,
    ToolCall,
    TraceDetail,
    UserListItem,
    TraceListItem,
    SessionListItem,
    SessionStats,
    UserMessageItem,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """Test that EventType has expected values."""
        assert EventType.SESSION_START == "session_start"
        assert EventType.SESSION_END == "session_end"
        assert EventType.LLM_INPUT == "llm_input"
        assert EventType.LLM_OUTPUT == "llm_output"
        assert EventType.TOOL_CALL_START == "tool_call_start"
        assert EventType.TOOL_CALL_END == "tool_call_end"
        assert EventType.SKILL_INVOCATION == "skill_invocation"

    def test_event_type_is_string_enum(self):
        """Test that EventType is a string enum."""
        assert isinstance(EventType.LLM_INPUT.value, str)


class TestTraceStatus:
    """Tests for TraceStatus enum."""

    def test_trace_status_values(self):
        """Test that TraceStatus has expected values."""
        assert TraceStatus.RUNNING == "running"
        assert TraceStatus.COMPLETED == "completed"
        assert TraceStatus.ERROR == "error"
        assert TraceStatus.CANCELLED == "cancelled"


class TestSpan:
    """Tests for Span model."""

    def test_span_creation_minimal(self):
        """Test creating a Span with minimal required fields."""
        now = datetime.now()
        span = Span(
            span_id="span-123",
            trace_id="trace-456",
            source_id="test-source",
            name="test_span",
            event_type=EventType.LLM_INPUT,
            start_time=now,
        )

        assert span.span_id == "span-123"
        assert span.trace_id == "trace-456"
        assert span.source_id == "test-source"
        assert span.name == "test_span"
        assert span.event_type == EventType.LLM_INPUT
        assert span.start_time == now
        assert span.end_time is None
        assert span.duration_ms is None
        assert span.model_name is None
        assert span.input_tokens is None
        assert span.output_tokens is None
        assert span.tool_name is None
        assert span.skill_name is None
        assert span.mcp_server is None
        assert span.tool_input is None
        assert span.tool_output is None
        assert span.error is None

    def test_span_creation_full(self):
        """Test creating a Span with all fields."""
        now = datetime.now()
        span = Span(
            span_id="span-123",
            trace_id="trace-456",
            source_id="test-source",
            name="test_span",
            event_type=EventType.TOOL_CALL_END,
            start_time=now,
            end_time=now,
            duration_ms=1500,
            user_id="user-1",
            session_id="session-1",
            channel="console",
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=200,
            tool_name="browser_control",
            skill_name="pdf",
            mcp_server="mcp-server-1",
            tool_input={"url": "https://example.com"},
            tool_output="result",
            error=None,
        )

        assert span.span_id == "span-123"
        assert span.trace_id == "trace-456"
        assert span.source_id == "test-source"
        assert span.name == "test_span"
        assert span.event_type == EventType.TOOL_CALL_END
        assert span.duration_ms == 1500
        assert span.user_id == "user-1"
        assert span.tool_name == "browser_control"
        assert span.mcp_server == "mcp-server-1"

    def test_span_default_values(self):
        """Test Span default values."""
        span = Span(
            span_id="span-123",
            trace_id="trace-456",
            source_id="test-source",
            name="test",
            event_type=EventType.LLM_INPUT,
            start_time=datetime.now(),
        )

        assert span.user_id == ""
        assert span.session_id == ""
        assert span.channel == ""


class TestTrace:
    """Tests for Trace model."""

    def test_trace_creation_minimal(self):
        """Test creating a Trace with minimal required fields."""
        now = datetime.now()
        trace = Trace(
            trace_id="trace-123",
            source_id="test-source",
            user_id="user-1",
            session_id="session-1",
            channel="console",
            start_time=now,
        )

        assert trace.trace_id == "trace-123"
        assert trace.source_id == "test-source"
        assert trace.user_id == "user-1"
        assert trace.session_id == "session-1"
        assert trace.channel == "console"
        assert trace.start_time == now
        assert trace.end_time is None
        assert trace.duration_ms is None
        assert trace.model_name is None
        assert trace.total_input_tokens == 0
        assert trace.total_output_tokens == 0
        assert trace.tools_used == []
        assert trace.skills_used == []
        assert trace.status == TraceStatus.RUNNING
        assert trace.error is None
        assert trace.user_message is None

    def test_trace_creation_full(self):
        """Test creating a Trace with all fields."""
        now = datetime.now()
        trace = Trace(
            trace_id="trace-123",
            source_id="test-source",
            user_id="user-1",
            session_id="session-1",
            channel="console",
            start_time=now,
            end_time=now,
            duration_ms=5000,
            model_name="gpt-4",
            total_input_tokens=1000,
            total_output_tokens=500,
            tools_used=["browser_control", "file_search"],
            skills_used=["pdf", "docx"],
            status=TraceStatus.COMPLETED,
            error=None,
            user_message="Hello, world!",
        )

        assert trace.trace_id == "trace-123"
        assert trace.source_id == "test-source"
        assert trace.duration_ms == 5000
        assert trace.total_input_tokens == 1000
        assert trace.total_output_tokens == 500
        assert len(trace.tools_used) == 2
        assert len(trace.skills_used) == 2
        assert trace.status == TraceStatus.COMPLETED
        assert trace.user_message == "Hello, world!"


class TestModelUsage:
    """Tests for ModelUsage model."""

    def test_model_usage_creation(self):
        """Test creating ModelUsage."""
        usage = ModelUsage(
            model_name="gpt-4",
            count=10,
            total_tokens=5000,
            input_tokens=3000,
            output_tokens=2000,
        )

        assert usage.model_name == "gpt-4"
        assert usage.count == 10
        assert usage.total_tokens == 5000


class TestToolUsage:
    """Tests for ToolUsage model."""

    def test_tool_usage_creation(self):
        """Test creating ToolUsage."""
        usage = ToolUsage(
            tool_name="browser_control",
            count=25,
            avg_duration_ms=1500,
            error_count=2,
        )

        assert usage.tool_name == "browser_control"
        assert usage.count == 25
        assert usage.avg_duration_ms == 1500
        assert usage.error_count == 2


class TestSkillUsage:
    """Tests for SkillUsage model."""

    def test_skill_usage_creation(self):
        """Test creating SkillUsage."""
        usage = SkillUsage(
            skill_name="pdf",
            count=15,
            avg_duration_ms=800,
        )

        assert usage.skill_name == "pdf"
        assert usage.count == 15


class TestMCPToolUsage:
    """Tests for MCPToolUsage model."""

    def test_mcp_tool_usage_creation(self):
        """Test creating MCPToolUsage."""
        usage = MCPToolUsage(
            tool_name="get_weather",
            mcp_server="weather-server",
            count=10,
            avg_duration_ms=500,
            error_count=1,
        )

        assert usage.tool_name == "get_weather"
        assert usage.mcp_server == "weather-server"
        assert usage.count == 10


class TestMCPServerUsage:
    """Tests for MCPServerUsage model."""

    def test_mcp_server_usage_creation(self):
        """Test creating MCPServerUsage."""
        tool = MCPToolUsage(
            tool_name="get_weather",
            mcp_server="weather-server",
            count=5,
        )
        usage = MCPServerUsage(
            server_name="weather-server",
            tool_count=3,
            total_calls=15,
            avg_duration_ms=400,
            error_count=0,
            tools=[tool],
        )

        assert usage.server_name == "weather-server"
        assert usage.tool_count == 3
        assert usage.total_calls == 15
        assert len(usage.tools) == 1


class TestDailyStats:
    """Tests for DailyStats model."""

    def test_daily_stats_creation(self):
        """Test creating DailyStats."""
        stats = DailyStats(
            date="2026-04-08",
            total_users=100,
            active_users=50,
            total_tokens=10000,
            input_tokens=6000,
            output_tokens=4000,
            session_count=200,
            conversation_count=150,
            avg_duration_ms=2500,
        )

        assert stats.date == "2026-04-08"
        assert stats.total_users == 100
        assert stats.active_users == 50


class TestOverviewStats:
    """Tests for OverviewStats model."""

    def test_overview_stats_creation(self):
        """Test creating OverviewStats with defaults."""
        stats = OverviewStats()

        assert stats.online_users == 0
        assert stats.total_users == 0
        assert stats.model_distribution == []
        assert stats.total_tokens == 0
        assert stats.top_tools == []
        assert stats.top_skills == []

    def test_overview_stats_with_data(self):
        """Test creating OverviewStats with data."""
        model_usage = ModelUsage(model_name="gpt-4", count=10)
        stats = OverviewStats(
            online_users=5,
            total_users=100,
            model_distribution=[model_usage],
            total_tokens=5000,
        )

        assert stats.online_users == 5
        assert stats.total_users == 100
        assert len(stats.model_distribution) == 1


class TestUserStats:
    """Tests for UserStats model."""

    def test_user_stats_creation(self):
        """Test creating UserStats."""
        stats = UserStats(user_id="user-1")

        assert stats.user_id == "user-1"
        assert stats.model_usage == []
        assert stats.total_tokens == 0


class TestToolCall:
    """Tests for ToolCall model."""

    def test_tool_call_creation(self):
        """Test creating ToolCall."""
        call = ToolCall(
            tool_name="browser_control",
            tool_input={"url": "https://example.com"},
            tool_output="success",
            duration_ms=1500,
            error=None,
        )

        assert call.tool_name == "browser_control"
        # pylint: disable-next=unsubscriptable-object
        assert call.tool_input["url"] == "https://example.com"


class TestTraceDetail:
    """Tests for TraceDetail model."""

    def test_trace_detail_creation(self):
        """Test creating TraceDetail."""
        trace = Trace(
            trace_id="trace-1",
            source_id="test-source",
            user_id="user-1",
            session_id="session-1",
            channel="console",
            start_time=datetime.now(),
        )
        detail = TraceDetail(
            trace=trace,
            spans=[],
            llm_duration_ms=3000,
            tool_duration_ms=1500,
            tools_called=[],
        )

        assert detail.trace.trace_id == "trace-1"
        assert detail.llm_duration_ms == 3000
        assert detail.tool_duration_ms == 1500


class TestUserListItem:
    """Tests for UserListItem model."""

    def test_user_list_item_creation(self):
        """Test creating UserListItem."""
        now = datetime.now()
        item = UserListItem(
            user_id="user-1",
            total_sessions=10,
            total_conversations=15,
            total_tokens=5000,
            total_skills=3,
            last_active=now,
        )

        assert item.user_id == "user-1"
        assert item.total_sessions == 10
        assert item.last_active == now


class TestTraceListItem:
    """Tests for TraceListItem model."""

    def test_trace_list_item_creation(self):
        """Test creating TraceListItem."""
        now = datetime.now()
        item = TraceListItem(
            trace_id="trace-1",
            source_id="test-source",
            user_id="user-1",
            session_id="session-1",
            channel="console",
            start_time=now,
            duration_ms=5000,
            total_tokens=1500,
            model_name="gpt-4",
            status="completed",
            skills_count=2,
        )

        assert item.trace_id == "trace-1"
        assert item.duration_ms == 5000
        assert item.status == "completed"


class TestSessionListItem:
    """Tests for SessionListItem model."""

    def test_session_list_item_creation(self):
        """Test creating SessionListItem."""
        now = datetime.now()
        item = SessionListItem(
            session_id="session-1",
            user_id="user-1",
            channel="console",
            total_traces=5,
            total_tokens=2500,
            total_skills=2,
            first_active=now,
            last_active=now,
        )

        assert item.session_id == "session-1"
        assert item.total_traces == 5


class TestSessionStats:
    """Tests for SessionStats model."""

    def test_session_stats_creation(self):
        """Test creating SessionStats."""
        stats = SessionStats(
            session_id="session-1",
            user_id="user-1",
            channel="console",
        )

        assert stats.session_id == "session-1"
        assert stats.user_id == "user-1"
        assert stats.model_usage == []


class TestUserMessageItem:
    """Tests for UserMessageItem model."""

    def test_user_message_item_creation(self):
        """Test creating UserMessageItem."""
        now = datetime.now()
        item = UserMessageItem(
            trace_id="trace-1",
            source_id="test-source",
            user_id="user-1",
            session_id="session-1",
            channel="console",
            user_message="Hello",
            input_tokens=10,
            output_tokens=20,
            model_name="gpt-4",
            start_time=now,
            duration_ms=1500,
        )

        assert item.trace_id == "trace-1"
        assert item.user_message == "Hello"
        assert item.input_tokens == 10
        assert item.output_tokens == 20
