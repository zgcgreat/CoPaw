# -*- coding: utf-8 -*-
"""Trace store module.

Provides database storage operations for traces and spans.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from .config import TracingConfig
from ..database import DatabaseConnection
from .models import (
    EventType,
    MCPToolUsage,
    MCPServerUsage,
    ModelUsage,
    OverviewStats,
    SessionListItem,
    SessionStats,
    SkillCallTimeline,
    SkillUsage,
    Span,
    TimelineEvent,
    ToolCallInSkill,
    ToolUsage,
    Trace,
    TraceDetail,
    TraceDetailWithTimeline,
    TraceListItem,
    TraceStatus,
    UserListItem,
    UserMessageItem,
    UserStats,
)

logger = logging.getLogger(__name__)

# 需要从统计中排除的 source_id（测试平台等）
EXCLUDED_SOURCE_IDS = ["default"]


def _matches_trace_filters(
    trace: Trace,
    user_id: Optional[str],
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> bool:
    """Return whether a trace matches the requested user/date filters."""
    uid = trace.user_id
    if not uid:
        return False
    if user_id and user_id not in uid:
        return False
    if start_date and trace.start_time < start_date:
        return False
    if end_date and trace.start_time > end_date:
        return False
    return True


def _create_user_summary(trace: Trace) -> dict[str, Any]:
    """Create an in-memory aggregation bucket for a user."""
    return {
        "sessions": 0,
        "conversations": set(),
        "tokens": 0,
        "skills": 0,
        "last_active": trace.start_time,
    }


class TraceStore:
    """Store for traces and spans using database or log-only mode."""

    def __init__(
        self,
        config: TracingConfig,
        db: Optional[DatabaseConnection],
        owns_db: bool = False,
    ):
        """Initialize trace store.

        Args:
            config: Tracing configuration
            db: Optional database connection for persistent storage.
                If None, runs in log-only mode.
            owns_db: Whether this store owns the database connection.
                If True, close() will close the database connection.
                If False (default), the connection is shared and should not be closed here.
        """
        self.config = config
        self.db = db
        self._owns_db = owns_db

    async def initialize(self) -> None:
        """Initialize store. Database tables must be created manually."""
        if self.db is None:
            return

        if not self.db.is_connected:
            logger.warning("Database not connected, running in log-only mode")
            self.db = None
            return

    async def close(self) -> None:
        """Close store. Only closes database connection if this store owns it."""
        if self._owns_db and self.db is not None:
            await self.db.close()

    # Trace operations

    async def create_trace(self, trace: Trace) -> None:
        """Create a new trace.

        Args:
            trace: Trace to create
        """
        if self.db is None:
            return

        query = """
            INSERT INTO swe_tracing_traces (
                trace_id, source_id, user_id, session_id, channel, start_time,
                end_time, duration_ms, model_name, total_input_tokens,
                total_output_tokens, total_tokens, tools_used, skills_used,
                status, error, user_message
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            trace.trace_id,
            trace.source_id,
            trace.user_id,
            trace.session_id,
            trace.channel,
            trace.start_time,
            trace.end_time,
            trace.duration_ms,
            trace.model_name,
            trace.total_input_tokens,
            trace.total_output_tokens,
            trace.total_input_tokens + trace.total_output_tokens,
            json.dumps(trace.tools_used),
            json.dumps(trace.skills_used),
            trace.status.value
            if isinstance(trace.status, TraceStatus)
            else trace.status,
            trace.error,
            trace.user_message,
        )
        await self.db.execute(query, params)

    async def update_trace(self, trace: Trace) -> None:
        """Update an existing trace.

        Args:
            trace: Trace to update
        """
        if self.db is None:
            return

        query = """
            UPDATE swe_tracing_traces SET
                end_time = %s,
                duration_ms = %s,
                model_name = %s,
                total_input_tokens = %s,
                total_output_tokens = %s,
                total_tokens = %s,
                tools_used = %s,
                skills_used = %s,
                status = %s,
                error = %s
            WHERE trace_id = %s
        """
        params = (
            trace.end_time,
            trace.duration_ms,
            trace.model_name,
            trace.total_input_tokens,
            trace.total_output_tokens,
            trace.total_input_tokens + trace.total_output_tokens,
            json.dumps(trace.tools_used),
            json.dumps(trace.skills_used),
            trace.status.value
            if isinstance(trace.status, TraceStatus)
            else trace.status,
            trace.error,
            trace.trace_id,
        )
        await self.db.execute(query, params)

    async def get_trace(
        self,
        trace_id: str,
        source_id: Optional[str] = None,
    ) -> Optional[Trace]:
        """Get a trace by ID.

        Args:
            trace_id: Trace identifier
            source_id: If provided, only return trace matching this source.

        Returns:
            Trace or None
        """
        if self.db is None:
            return None

        if source_id:
            query = (
                "SELECT * FROM swe_tracing_traces "
                "WHERE trace_id = %s AND source_id = %s"
            )
            row = await self.db.fetch_one(query, (trace_id, source_id))
        else:
            query = "SELECT * FROM swe_tracing_traces WHERE trace_id = %s"
            row = await self.db.fetch_one(query, (trace_id,))
        if row is None:
            return None
        return self._row_to_trace(row)

    # Span operations

    async def create_span(self, span: Span) -> None:
        """Create a new span.

        Args:
            span: Span to create
        """
        if self.db is None:
            return

        query = """
            INSERT INTO swe_tracing_spans (
                span_id, trace_id, source_id, name, event_type,
                start_time, end_time, duration_ms, user_id, session_id, channel,
                model_name, input_tokens, output_tokens, tool_name, skill_name, mcp_server,
                tool_input, tool_output, error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            span.span_id,
            span.trace_id,
            span.source_id,
            span.name,
            span.event_type.value
            if isinstance(span.event_type, EventType)
            else span.event_type,
            span.start_time,
            span.end_time,
            span.duration_ms,
            span.user_id,
            span.session_id,
            span.channel,
            span.model_name,
            span.input_tokens,
            span.output_tokens,
            span.tool_name,
            span.skill_name,
            span.mcp_server,
            json.dumps(span.tool_input) if span.tool_input else None,
            span.tool_output,
            span.error,
        )
        await self.db.execute(query, params)

    async def update_span(self, span: Span) -> None:
        """Update an existing span.

        Args:
            span: Span to update
        """
        if self.db is None:
            return

        query = """
            UPDATE swe_tracing_spans SET
                end_time = %s,
                duration_ms = %s,
                input_tokens = %s,
                output_tokens = %s,
                tool_output = %s,
                error = %s,
                event_type = %s
            WHERE span_id = %s
        """
        params = (
            span.end_time,
            span.duration_ms,
            span.input_tokens,
            span.output_tokens,
            span.tool_output,
            span.error,
            span.event_type.value
            if hasattr(span.event_type, "value")
            else span.event_type,
            span.span_id,
        )
        await self.db.execute(query, params)

    async def get_spans(self, trace_id: str) -> list[Span]:
        """Get all spans for a trace.

        Args:
            trace_id: Trace identifier

        Returns:
            List of spans
        """
        if self.db is None:
            return []

        query = "SELECT * FROM swe_tracing_spans WHERE trace_id = %s ORDER BY start_time"
        rows = await self.db.fetch_all(query, (trace_id,))
        return [self._row_to_span(row) for row in rows]

    # Batch operations

    async def batch_create_spans(self, spans: list[Span]) -> None:
        """Batch create spans.

        Args:
            spans: List of spans to create
        """
        if not spans:
            return

        if self.db is None:
            return

        query = """
            INSERT INTO swe_tracing_spans (
                span_id, trace_id, source_id, name, event_type,
                start_time, end_time, duration_ms, user_id, session_id, channel,
                model_name, input_tokens, output_tokens, tool_name, skill_name, mcp_server,
                tool_input, tool_output, error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params_list = []
        for span in spans:
            params_list.append(
                (
                    span.span_id,
                    span.trace_id,
                    span.source_id,
                    span.name,
                    span.event_type.value
                    if isinstance(span.event_type, EventType)
                    else span.event_type,
                    span.start_time,
                    span.end_time,
                    span.duration_ms,
                    span.user_id,
                    span.session_id,
                    span.channel,
                    span.model_name,
                    span.input_tokens,
                    span.output_tokens,
                    span.tool_name,
                    span.skill_name,
                    span.mcp_server,
                    json.dumps(span.tool_input) if span.tool_input else None,
                    span.tool_output,
                    span.error,
                ),
            )
        await self.db.execute_many(query, params_list)

    # Query operations

    def _build_overview_stats(
        self,
        total_users: int,
        online_users: int,
        online_user_ids: list[str],
        token_row: Optional[dict],
        model_distribution: list,
        top_tools: list,
        top_skills: list,
        top_mcp_tools: list,
        mcp_servers: list,
    ) -> OverviewStats:
        """Build OverviewStats from collected data."""
        return OverviewStats(
            online_users=online_users,
            online_user_ids=online_user_ids,
            total_users=total_users,
            model_distribution=model_distribution,
            total_tokens=token_row["total_tokens"] or 0 if token_row else 0,
            input_tokens=token_row["input_tokens"] or 0 if token_row else 0,
            output_tokens=token_row["output_tokens"] or 0 if token_row else 0,
            total_sessions=token_row["total_sessions"] or 0
            if token_row
            else 0,
            total_conversations=token_row["total_traces"] or 0
            if token_row
            else 0,
            avg_duration_ms=(
                int(token_row["avg_duration"] or 0)
                if token_row and token_row["avg_duration"]
                else 0
            ),
            top_tools=top_tools,
            top_skills=top_skills,
            top_mcp_tools=top_mcp_tools,
            mcp_servers=mcp_servers,
            daily_trend=[],
        )

    async def get_overview_stats(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> OverviewStats:
        """Get overview statistics.

        Args:
            source_id: Source identifier (required)
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Overview statistics
        """
        # Verify database connection
        if self.db is None or not self.db.is_connected:
            logger.error("Database not connected in get_overview_stats")
            return OverviewStats()

        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)  # Include today

        # Basic stats
        total_users = await self._db_get_total_users(
            source_id,
            start_date,
            end_date,
        )
        online_users, online_user_ids = await self._db_get_online_users(
            source_id,
        )
        token_row = await self._db_get_token_stats(
            source_id,
            start_date,
            end_date,
        )

        # Distribution stats
        model_distribution = await self._db_get_model_distribution(
            source_id,
            start_date,
            end_date,
        )
        top_tools = await self._db_get_top_tools(
            source_id,
            start_date,
            end_date,
        )
        top_skills = await self._db_get_top_skills(
            source_id,
            start_date,
            end_date,
        )
        top_mcp_tools, mcp_servers = await self._db_get_mcp_stats(
            source_id,
            start_date,
            end_date,
        )

        return self._build_overview_stats(
            total_users,
            online_users,
            online_user_ids,
            token_row,
            model_distribution,
            top_tools,
            top_skills,
            top_mcp_tools,
            mcp_servers,
        )

    async def get_channel_distribution(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Get channel (platform) distribution statistics by source_id.

        Args:
            source_id: Source identifier (required) - if "all", returns distribution across all sources
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Dict with platformUserDistribution, platformCallDistribution, totalPlatforms
        """
        if self.db is None or not self.db.is_connected:
            logger.error("Database not connected in get_channel_distribution")
            return {
                "platformUserDistribution": [],
                "platformCallDistribution": [],
                "totalPlatforms": 0,
            }

        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        # If source_id is "all", get distribution across all sources
        if source_id == "all":
            # 排除测试平台
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT
                    source_id,
                    COUNT(DISTINCT user_id) as user_count,
                    COUNT(*) as call_count,
                    SUM(total_tokens) as token_count
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id IS NOT NULL AND source_id != ''
                  AND source_id NOT IN ({exclude_placeholders})
                GROUP BY source_id
                ORDER BY call_count DESC
            """
            rows = await self.db.fetch_all(
                query,
                (start_date, end_date, *EXCLUDED_SOURCE_IDS),
            )
        else:
            query = """
                SELECT
                    source_id,
                    COUNT(DISTINCT user_id) as user_count,
                    COUNT(*) as call_count,
                    SUM(total_tokens) as token_count
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                GROUP BY source_id
                ORDER BY call_count DESC
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, start_date, end_date),
            )

        platform_user_dist = []
        platform_call_dist = []
        sources = []

        for row in rows:
            src_id = row["source_id"]
            sources.append(src_id)
            platform_user_dist.append(
                {
                    "name": src_id,
                    "value": row["user_count"] or 0,
                },
            )
            platform_call_dist.append(
                {
                    "name": src_id,
                    "value": row["call_count"] or 0,
                },
            )

        return {
            "platformUserDistribution": platform_user_dist,
            "platformCallDistribution": platform_call_dist,
            "totalPlatforms": len(sources),
        }

    async def get_sources(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[str]:
        """Get list of all distinct source_ids.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of source_id strings (excluding test platforms)
        """
        if self.db is None or not self.db.is_connected:
            logger.error("Database not connected in get_sources")
            return []

        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        # 构建排除测试平台的条件
        exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))

        query = f"""
            SELECT DISTINCT source_id
            FROM swe_tracing_traces
            WHERE start_time >= %s AND start_time <= %s
              AND source_id IS NOT NULL AND source_id != ''
              AND source_id NOT IN ({exclude_placeholders})
            ORDER BY source_id
        """
        rows = await self.db.fetch_all(
            query,
            (start_date, end_date, *EXCLUDED_SOURCE_IDS),
        )
        return [row["source_id"] for row in rows]

    async def get_growth_stats(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        time_range: str = "day",
    ) -> dict[str, Any]:
        """Get growth statistics compared to previous period.

        Args:
            source_id: Source identifier (use 'all' for all platforms)
            start_date: Start date of current period
            end_date: End date of current period
            time_range: day/week/month/custom (used to calculate previous period)

        Returns:
            Dict with callsGrowth, tokensGrowth, sessionGrowth, userGrowth, platformGrowth
        """
        if self.db is None or not self.db.is_connected:
            logger.error("Database not connected in get_growth_stats")
            return {
                "callsGrowth": 0,
                "tokensGrowth": 0,
                "sessionGrowth": 0,
                "userGrowth": 0,
                "platformGrowth": 0,
            }

        # Calculate previous period based on time_range
        period_days = 1
        if time_range == "week":
            period_days = 7
        elif time_range == "month":
            period_days = 30
        elif time_range == "custom":
            period_days = (end_date - start_date).days

        prev_start = start_date - timedelta(days=period_days)
        prev_end = start_date - timedelta(seconds=1)

        async def get_stats(s: datetime, e: datetime) -> dict:
            if source_id == "all":
                query = """
                    SELECT
                        COUNT(*) as calls,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COUNT(DISTINCT session_id) as sessions,
                        COUNT(DISTINCT user_id) as users,
                        COUNT(DISTINCT source_id) as platforms
                    FROM swe_tracing_traces
                    WHERE start_time >= %s AND start_time <= %s
                """
                row = await self.db.fetch_one(query, (s, e))
            else:
                query = """
                    SELECT
                        COUNT(*) as calls,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COUNT(DISTINCT session_id) as sessions,
                        COUNT(DISTINCT user_id) as users,
                        COUNT(DISTINCT channel) as platforms
                    FROM swe_tracing_traces
                    WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                """
                row = await self.db.fetch_one(query, (source_id, s, e))
            return {
                "calls": row["calls"] or 0,
                "tokens": row["tokens"] or 0,
                "sessions": row["sessions"] or 0,
                "users": row["users"] or 0,
                "platforms": row["platforms"] or 0,
            }

        curr = await get_stats(start_date, end_date)
        prev = await get_stats(prev_start, prev_end)

        def calc_growth(curr_val: float, prev_val: float) -> float:
            if prev_val == 0:
                return 100.0 if curr_val > 0 else 0.0
            return round(((curr_val - prev_val) / prev_val) * 100, 1)

        return {
            "callsGrowth": calc_growth(curr["calls"], prev["calls"]),
            "tokensGrowth": calc_growth(curr["tokens"], prev["tokens"]),
            "sessionGrowth": calc_growth(curr["sessions"], prev["sessions"]),
            "userGrowth": calc_growth(curr["users"], prev["users"]),
            "platformGrowth": calc_growth(
                curr["platforms"],
                prev["platforms"],
            ),
        }

    async def get_daily_trend(
        self,
        source_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Get daily trend data for the specified period.

        Args:
            source_id: Source identifier (use 'all' to get data across all sources)
            start_date: Start date filter
            end_date: End date filter

        Returns:
            List of { date, calls, tokens, users }
        """
        if self.db is None or not self.db.is_connected:
            logger.error("Database not connected in get_daily_trend")
            return []

        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)

        # If source_id is "all", get trend data across all sources
        if source_id == "all":
            query = """
                SELECT
                    DATE(start_time) as date,
                    COUNT(*) as calls,
                    COALESCE(SUM(total_tokens), 0) as tokens,
                    COUNT(DISTINCT user_id) as users
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                GROUP BY DATE(start_time)
                ORDER BY date
            """
            rows = await self.db.fetch_all(query, (start_date, end_date))
        else:
            query = """
                SELECT
                    DATE(start_time) as date,
                    COUNT(*) as calls,
                    COALESCE(SUM(total_tokens), 0) as tokens,
                    COUNT(DISTINCT user_id) as users
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                GROUP BY DATE(start_time)
                ORDER BY date
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, start_date, end_date),
            )

        return [
            {
                "date": row["date"].strftime("%Y-%m-%d")
                if row["date"]
                else "",
                "calls": row["calls"] or 0,
                "tokens": row["tokens"] or 0,
                "users": row["users"] or 0,
            }
            for row in rows
        ]

    async def get_users(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[UserListItem], int]:
        """Get list of users with stats.

        Args:
            source_id: Source identifier (use 'all' for all platforms)
            page: Page number
            page_size: Page size
            user_id: Filter by user ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Tuple of (users list, total count)
        """
        # Build where clauses based on source_id
        if source_id == "all":
            # 排除测试平台
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            where_clauses: list[str] = [
                f"source_id NOT IN ({exclude_placeholders})",
            ]
            params: list[Any] = list(EXCLUDED_SOURCE_IDS)
        else:
            where_clauses = ["source_id = %s"]
            params = [source_id]

        # 排除测试用户
        where_clauses.append("user_id != 'default'")

        if user_id:
            where_clauses.append("user_id LIKE %s")
            params.append(f"%{user_id}%")
        if start_date:
            where_clauses.append("start_time >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("start_time <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        count_query = f"""
            SELECT COUNT(DISTINCT user_id) as total
            FROM swe_tracing_traces
            WHERE {where_sql}
        """
        count_row = await self.db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        # Get users with skill counts from spans
        offset = (page - 1) * page_size
        if source_id == "all":
            query = f"""
                SELECT t.user_id,
                       COUNT(DISTINCT t.session_id) as total_sessions,
                       COUNT(*) as total_conversations,
                       SUM(t.total_tokens) as total_tokens,
                       MAX(t.start_time) as last_active,
                       (SELECT COUNT(*) FROM swe_tracing_spans s
                        WHERE s.trace_id IN (
                            SELECT trace_id FROM swe_tracing_traces WHERE user_id = t.user_id
                        )
                        AND s.event_type = 'skill_invocation') as total_skills
                FROM swe_tracing_traces t
                WHERE {where_sql}
                GROUP BY t.user_id
                ORDER BY last_active DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
        else:
            query = f"""
                SELECT t.user_id,
                       COUNT(DISTINCT t.session_id) as total_sessions,
                       COUNT(*) as total_conversations,
                       SUM(t.total_tokens) as total_tokens,
                       MAX(t.start_time) as last_active,
                       (SELECT COUNT(*) FROM swe_tracing_spans s
                        WHERE s.source_id = %s
                        AND s.trace_id IN (
                            SELECT trace_id FROM swe_tracing_traces WHERE user_id = t.user_id AND source_id = %s
                        )
                        AND s.event_type = 'skill_invocation') as total_skills
                FROM swe_tracing_traces t
                WHERE {where_sql}
                GROUP BY t.user_id
                ORDER BY last_active DESC
                LIMIT %s OFFSET %s
            """
            # 子查询参数在前，然后是 WHERE 子句参数，最后是 LIMIT/OFFSET
            params = [source_id, source_id] + params + [page_size, offset]
        rows = await self.db.fetch_all(query, tuple(params))
        users = [
            UserListItem(
                user_id=row["user_id"],
                total_sessions=row["total_sessions"] or 0,
                total_conversations=row["total_conversations"] or 0,
                total_tokens=row["total_tokens"] or 0,
                total_skills=row["total_skills"] or 0,
                last_active=row["last_active"],
            )
            for row in rows
        ]
        return users, total

    async def _get_user_model_usage(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ModelUsage]:
        """Get model usage for a user."""
        model_query = """
            SELECT model_name, COUNT(*) as count,
                   SUM(total_input_tokens) as input_tokens,
                   SUM(total_output_tokens) as output_tokens,
                   SUM(total_tokens) as total_tokens
            FROM swe_tracing_traces
            WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
                  AND model_name IS NOT NULL
            GROUP BY model_name
            ORDER BY count DESC
        """
        model_rows = await self.db.fetch_all(
            model_query,
            (source_id, user_id, start_date, end_date),
        )
        return [
            ModelUsage(
                model_name=row["model_name"],
                count=row["count"],
                total_tokens=row["total_tokens"] or 0,
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
            )
            for row in model_rows
        ]

    async def _get_user_tool_usage(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ToolUsage]:
        """Get tool usage for a user."""
        tool_query = """
            SELECT tool_name, COUNT(*) as count,
                   AVG(duration_ms) as avg_duration,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM swe_tracing_spans
            WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'tool_call_end'
              AND tool_name IS NOT NULL
            GROUP BY tool_name
            ORDER BY count DESC
        """
        tool_rows = await self.db.fetch_all(
            tool_query,
            (source_id, user_id, start_date, end_date),
        )
        return [
            ToolUsage(
                tool_name=row["tool_name"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in tool_rows
        ]

    async def _get_user_skill_usage(
        self,
        source_id: str,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[SkillUsage]:
        """Get skill usage for a user."""
        skill_query = """
            SELECT skill_name, COUNT(*) as count,
                   AVG(duration_ms) as avg_duration
            FROM swe_tracing_spans
            WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'skill_invocation'
              AND skill_name IS NOT NULL
            GROUP BY skill_name
            ORDER BY count DESC
        """
        skill_rows = await self.db.fetch_all(
            skill_query,
            (source_id, user_id, start_date, end_date),
        )
        return [
            SkillUsage(
                skill_name=row["skill_name"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in skill_rows
        ]

    def _build_user_stats(
        self,
        user_id: str,
        stats_row: Optional[dict],
        model_usage: list[ModelUsage],
        tools_used: list[ToolUsage],
        skills_used: list[SkillUsage],
    ) -> UserStats:
        """Build UserStats from collected data."""
        return UserStats(
            user_id=user_id,
            model_usage=model_usage,
            total_tokens=stats_row["total_tokens"] if stats_row else 0,
            input_tokens=stats_row["input_tokens"] if stats_row else 0,
            output_tokens=stats_row["output_tokens"] if stats_row else 0,
            total_sessions=stats_row["total_sessions"] if stats_row else 0,
            total_conversations=stats_row["total_conversations"]
            if stats_row
            else 0,
            avg_duration_ms=int(stats_row["avg_duration"] or 0)
            if stats_row
            else 0,
            tools_used=tools_used,
            skills_used=skills_used,
        )

    async def get_user_stats(
        self,
        source_id: str,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> UserStats:
        """Get statistics for a specific user.

        Args:
            source_id: Source identifier (required)
            user_id: User identifier
            start_date: Start date filter
            end_date: End date filter

        Returns:
            User statistics
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        # Get basic stats
        stats_query = """
            SELECT
                COUNT(DISTINCT session_id) as total_sessions,
                COUNT(*) as total_conversations,
                SUM(total_input_tokens) as input_tokens,
                SUM(total_output_tokens) as output_tokens,
                SUM(total_tokens) as total_tokens,
                AVG(duration_ms) as avg_duration
            FROM swe_tracing_traces
            WHERE source_id = %s AND user_id = %s AND start_time >= %s AND start_time <= %s
        """
        stats_row = await self.db.fetch_one(
            stats_query,
            (source_id, user_id, start_date, end_date),
        )

        # Get usage data in parallel
        model_usage = await self._get_user_model_usage(
            source_id,
            user_id,
            start_date,
            end_date,
        )
        tools_used = await self._get_user_tool_usage(
            source_id,
            user_id,
            start_date,
            end_date,
        )
        skills_used = await self._get_user_skill_usage(
            source_id,
            user_id,
            start_date,
            end_date,
        )

        return self._build_user_stats(
            user_id,
            stats_row,
            model_usage,
            tools_used,
            skills_used,
        )

    async def get_traces(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[TraceListItem], int]:
        """Get list of traces.

        Args:
            source_id: Source identifier (required)
            page: Page number
            page_size: Page size
            user_id: Filter by user ID
            session_id: Filter by session ID
            status: Filter by status
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Tuple of (traces list, total count)
        """
        where_clauses: list[str] = ["source_id = %s"]
        params: list[Any] = [source_id]

        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        if session_id:
            where_clauses.append("session_id = %s")
            params.append(session_id)
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        if start_date:
            where_clauses.append("start_time >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("start_time <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)

        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM swe_tracing_traces WHERE {where_sql}"
        count_row = await self.db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        # Get traces
        offset = (page - 1) * page_size
        query = f"""
            SELECT trace_id, source_id, user_id, session_id, channel, start_time,
                   duration_ms, total_tokens, total_input_tokens, total_output_tokens,
                   model_name, status,
                   JSON_LENGTH(skills_used) as skills_count
            FROM swe_tracing_traces
            WHERE {where_sql}
            ORDER BY start_time DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        rows = await self.db.fetch_all(query, tuple(params))
        traces = [
            TraceListItem(
                trace_id=row["trace_id"],
                source_id=row["source_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                channel=row["channel"],
                start_time=row["start_time"],
                duration_ms=row["duration_ms"],
                total_tokens=row["total_tokens"] or 0,
                total_input_tokens=row["total_input_tokens"] or 0,
                total_output_tokens=row["total_output_tokens"] or 0,
                model_name=row["model_name"],
                status=row["status"],
                skills_count=row["skills_count"] or 0,
            )
            for row in rows
        ]
        return traces, total

    async def get_trace_detail(
        self,
        trace_id: str,
        source_id: Optional[str] = None,
    ) -> Optional[TraceDetail]:
        """Get detailed trace with spans.

        Args:
            trace_id: Trace identifier
            source_id: If provided, only return trace matching this source.

        Returns:
            Trace detail or None
        """
        trace = await self.get_trace(trace_id, source_id)
        if trace is None:
            return None

        spans = await self.get_spans(trace_id)

        # Calculate durations by type
        llm_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type in (EventType.LLM_INPUT, EventType.LLM_OUTPUT)
        )
        tool_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type
            in (EventType.TOOL_CALL_START, EventType.TOOL_CALL_END)
        )

        # Extract tool calls
        tools_called = []
        tool_spans = [
            s for s in spans if s.event_type == EventType.TOOL_CALL_END
        ]
        for span in tool_spans:
            tools_called.append(
                {
                    "tool_name": span.tool_name or span.name,
                    "tool_input": span.tool_input,
                    "tool_output": span.tool_output,
                    "duration_ms": span.duration_ms,
                    "error": span.error,
                },
            )

        return TraceDetail(
            trace=trace,
            spans=spans,
            llm_duration_ms=llm_duration,
            tool_duration_ms=tool_duration,
            tools_called=tools_called,
        )

    async def get_trace_detail_with_timeline(
        self,
        trace_id: str,
        source_id: Optional[str] = None,
    ) -> Optional[TraceDetailWithTimeline]:
        """Get trace detail with hierarchical timeline.

        Builds a hierarchical timeline where skill invocations
        are parent nodes containing their tool calls as children.

        Args:
            trace_id: Trace identifier
            source_id: If provided, only return trace matching this source.

        Returns:
            Trace detail with timeline or None
        """
        trace = await self.get_trace(trace_id, source_id)
        if trace is None:
            return None

        spans = await self.get_spans(trace_id)

        # Build timeline from spans
        timeline = self._build_timeline(spans)

        # Build skill invocations summary
        skill_invocations = self._build_skill_invocations(spans)

        # Calculate statistics
        llm_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type in (EventType.LLM_INPUT, EventType.LLM_OUTPUT)
        )
        tool_duration = sum(
            s.duration_ms or 0
            for s in spans
            if s.event_type
            in (EventType.TOOL_CALL_START, EventType.TOOL_CALL_END)
        )
        skill_duration = sum(inv.duration_ms for inv in skill_invocations)

        return TraceDetailWithTimeline(
            trace=trace,
            spans=spans,
            timeline=timeline,
            skill_invocations=skill_invocations,
            llm_duration_ms=llm_duration,
            tool_duration_ms=tool_duration,
            skill_duration_ms=skill_duration,
            total_skills=len(skill_invocations),
            total_tools=len(
                [s for s in spans if s.event_type == EventType.TOOL_CALL_END],
            ),
            total_llm_calls=len(
                [s for s in spans if s.event_type == EventType.LLM_INPUT],
            ),
        )

    def _build_timeline(self, spans: list[Span]) -> list[TimelineEvent]:
        """Build hierarchical timeline from flat spans.

        Converts flat span list to hierarchical structure where
        skill invocations contain their tool calls as children.

        Args:
            spans: List of spans (flat)

        Returns:
            List of TimelineEvent with hierarchical structure
        """
        # Sort spans by start_time
        spans = sorted(spans, key=lambda s: s.start_time)

        timeline: list[TimelineEvent] = []
        skill_stack: list[
            TimelineEvent
        ] = []  # Track active skills for nesting

        for span in spans:
            if span.event_type == EventType.SKILL_INVOCATION:
                # Skill invocation start
                event = TimelineEvent(
                    event_type="skill_invocation",
                    span_id=span.span_id,
                    start_time=span.start_time,
                    end_time=span.end_time,
                    duration_ms=span.duration_ms or 0,
                    skill_name=span.skill_name,
                    confidence=1.0,
                    trigger_reason="declared",
                    children=[],
                )

                # Nest under parent skill if exists
                if skill_stack:
                    skill_stack[-1].children.append(event)
                else:
                    timeline.append(event)

                # Push to stack for tool nesting
                skill_stack.append(event)

            elif span.event_type in (
                EventType.TOOL_CALL_START,
                EventType.TOOL_CALL_END,
            ):
                # Only process TOOL_CALL_END for complete events
                if span.event_type == EventType.TOOL_CALL_END:
                    event = TimelineEvent(
                        event_type="tool_call",
                        span_id=span.span_id,
                        start_time=span.start_time,
                        end_time=span.end_time,
                        duration_ms=span.duration_ms or 0,
                        tool_name=span.tool_name,
                        mcp_server=span.mcp_server,
                        skill_weight=None,
                        children=[],
                    )

                    # Nest under current skill if exists
                    if skill_stack:
                        skill_stack[-1].children.append(event)
                    else:
                        timeline.append(event)

            elif span.event_type in (
                EventType.LLM_INPUT,
                EventType.LLM_OUTPUT,
            ):
                # LLM call event
                if span.event_type == EventType.LLM_INPUT:
                    event = TimelineEvent(
                        event_type="llm_call",
                        span_id=span.span_id,
                        start_time=span.start_time,
                        end_time=span.end_time,
                        duration_ms=span.duration_ms or 0,
                        model_name=span.model_name,
                        input_tokens=span.input_tokens,
                        output_tokens=span.output_tokens,
                        children=[],
                    )
                    timeline.append(event)

        return timeline

    def _build_skill_invocations(
        self,
        spans: list[Span],
    ) -> list[SkillCallTimeline]:
        """Build skill invocation summaries with tool hierarchy.

        Args:
            spans: List of spans

        Returns:
            List of SkillCallTimeline
        """
        skill_spans = [
            s for s in spans if s.event_type == EventType.SKILL_INVOCATION
        ]

        invocations: list[SkillCallTimeline] = []
        skill_tools: dict[str, list[ToolCallInSkill]] = {}

        # Group tools by skill
        for span in spans:
            if span.event_type == EventType.TOOL_CALL_END and span.skill_name:
                skill_name = span.skill_name
                if skill_name not in skill_tools:
                    skill_tools[skill_name] = []

                skill_tools[skill_name].append(
                    ToolCallInSkill(
                        span_id=span.span_id,
                        tool_name=span.tool_name or "",
                        mcp_server=span.mcp_server,
                        start_time=span.start_time,
                        end_time=span.end_time,
                        duration_ms=span.duration_ms or 0,
                        status="error" if span.error else "success",
                        error=span.error,
                        skill_weight=None,
                    ),
                )

        # Build skill invocations
        for skill_span in skill_spans:
            skill_name = skill_span.skill_name or ""
            tools = skill_tools.get(skill_name, [])

            invocations.append(
                SkillCallTimeline(
                    span_id=skill_span.span_id,
                    skill_name=skill_name,
                    start_time=skill_span.start_time,
                    end_time=skill_span.end_time,
                    duration_ms=skill_span.duration_ms or 0,
                    confidence=1.0,
                    trigger_reason="declared",
                    tools=tools,
                    total_tool_calls=len(tools),
                    tool_duration_ms=sum(t.duration_ms for t in tools),
                ),
            )

        return invocations

    async def get_sessions(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[SessionListItem], int]:
        """Get list of sessions with stats.

        Args:
            source_id: Source identifier (required)
            page: Page number
            page_size: Page size
            user_id: Filter by user ID
            session_id: Filter by session ID (partial match)
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Tuple of (sessions list, total count)
        """
        where_clauses: list[str] = ["source_id = %s"]
        params: list[Any] = [source_id]

        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        if session_id:
            where_clauses.append("session_id LIKE %s")
            params.append(f"%{session_id}%")
        if start_date:
            where_clauses.append("start_time >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("start_time <= %s")
            params.append(end_date)

        where_sql = " AND ".join(where_clauses)

        # Get total count of unique sessions
        count_query = f"""
            SELECT COUNT(DISTINCT session_id) as total
            FROM swe_tracing_traces
            WHERE {where_sql}
        """
        count_row = await self.db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        # Get sessions with skill counts from spans
        offset = (page - 1) * page_size
        query = f"""
            SELECT t.session_id,
                   t.user_id,
                   t.channel,
                   COUNT(*) as total_traces,
                   SUM(t.total_tokens) as total_tokens,
                   MIN(t.start_time) as first_active,
                   MAX(t.start_time) as last_active,
                   (SELECT COUNT(*) FROM swe_tracing_spans s
                    WHERE s.source_id = %s
                    AND s.session_id = t.session_id
                    AND s.event_type = 'skill_invocation') as total_skills
            FROM swe_tracing_traces t
            WHERE {where_sql}
            GROUP BY t.session_id, t.user_id, t.channel
            ORDER BY last_active DESC
            LIMIT %s OFFSET %s
        """
        params.extend([source_id, page_size, offset])
        rows = await self.db.fetch_all(query, tuple(params))
        sessions = [
            SessionListItem(
                session_id=row["session_id"],
                user_id=row["user_id"],
                channel=row["channel"],
                total_traces=row["total_traces"] or 0,
                total_tokens=row["total_tokens"] or 0,
                total_skills=row["total_skills"] or 0,
                first_active=row["first_active"],
                last_active=row["last_active"],
            )
            for row in rows
        ]
        return sessions, total

    async def get_session_stats(
        self,
        source_id: str,
        session_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> SessionStats:
        """Get statistics for a specific session.

        Args:
            source_id: Source identifier (required)
            session_id: Session identifier
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Session statistics
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        stats_row = await self._db_get_session_basic_stats(
            source_id,
            session_id,
            start_date,
            end_date,
        )

        if not stats_row or not stats_row.get("user_id"):
            return SessionStats(session_id=session_id, user_id="", channel="")

        user_id = stats_row["user_id"]
        channel = stats_row["channel"] or ""

        # Get distribution stats
        model_usage = await self._db_get_session_model_usage(
            source_id,
            session_id,
            start_date,
            end_date,
        )
        tools_used = await self._db_get_session_tools(
            source_id,
            session_id,
            start_date,
            end_date,
        )
        skills_used = await self._db_get_session_skills(
            source_id,
            session_id,
            start_date,
            end_date,
        )
        mcp_tools_used = await self._db_get_session_mcp_tools(
            source_id,
            session_id,
            start_date,
            end_date,
        )

        return SessionStats(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            model_usage=model_usage,
            total_tokens=stats_row["total_tokens"] or 0,
            input_tokens=stats_row["input_tokens"] or 0,
            output_tokens=stats_row["output_tokens"] or 0,
            total_traces=stats_row["total_traces"] or 0,
            avg_duration_ms=int(stats_row["avg_duration"] or 0)
            if stats_row and stats_row["avg_duration"]
            else 0,
            tools_used=tools_used,
            skills_used=skills_used,
            mcp_tools_used=mcp_tools_used,
            first_active=stats_row["first_active"],
            last_active=stats_row["last_active"],
        )

    async def get_user_messages(
        self,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        query: Optional[str] = None,
        export: bool = False,
    ) -> tuple[list[UserMessageItem], int]:
        """Get user messages with token info for cost analysis.

        Args:
            source_id: Source identifier (required)
            page: Page number
            page_size: Page size
            user_id: Filter by user ID
            session_id: Filter by session ID
            start_date: Filter by start date
            end_date: Filter by end date
            query: Search in user message content (partial match)
            export: If True, return all results (ignore pagination)

        Returns:
            Tuple of (messages list, total count)
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()

        where_clauses = [
            "source_id = %s",
            "start_time >= %s",
            "start_time <= %s",
        ]
        params: list[Any] = [source_id, start_date, end_date]

        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        if session_id:
            where_clauses.append("session_id = %s")
            params.append(session_id)
        if query:
            where_clauses.append("user_message LIKE %s")
            params.append(f"%{query}%")

        where_sql = " AND ".join(where_clauses)

        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM swe_tracing_traces WHERE {where_sql}"
        count_row = await self.db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        # Get messages
        if export:
            sql_query = f"""
                SELECT trace_id, source_id, user_id, session_id, channel, user_message,
                       total_input_tokens, total_output_tokens, model_name,
                       start_time, duration_ms
                FROM swe_tracing_traces
                WHERE {where_sql}
                ORDER BY start_time DESC
            """
            rows = await self.db.fetch_all(sql_query, tuple(params))
        else:
            offset = (page - 1) * page_size
            sql_query = f"""
                SELECT trace_id, source_id, user_id, session_id, channel, user_message,
                       total_input_tokens, total_output_tokens, model_name,
                       start_time, duration_ms
                FROM swe_tracing_traces
                WHERE {where_sql}
                ORDER BY start_time DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
            rows = await self.db.fetch_all(sql_query, tuple(params))

        messages = [
            UserMessageItem(
                trace_id=row["trace_id"],
                source_id=row["source_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                channel=row["channel"],
                user_message=row["user_message"],
                input_tokens=row["total_input_tokens"] or 0,
                output_tokens=row["total_output_tokens"] or 0,
                model_name=row["model_name"],
                start_time=row["start_time"],
                duration_ms=row["duration_ms"],
            )
            for row in rows
        ]
        return messages, total

    # Flush operation (no-op for database storage)

    async def flush(self) -> None:
        """Flush current data - no-op for database storage."""

    # Cleanup operation

    async def cleanup_old_data(self, cutoff_date: datetime) -> None:
        """Clean up data older than the cutoff date.

        Args:
            cutoff_date: Remove data older than this date
        """
        # Delete old spans
        span_query = """
            DELETE FROM swe_tracing_spans
            WHERE trace_id IN (
                SELECT trace_id FROM swe_tracing_traces
                WHERE start_time < %s
            )
        """
        await self.db.execute(span_query, (cutoff_date,))

        # Delete old traces
        trace_query = "DELETE FROM swe_tracing_traces WHERE start_time < %s"
        result = await self.db.execute(trace_query, (cutoff_date,))
        logger.info(
            "Cleaned up %d old traces (older than %s)",
            result,
            cutoff_date.strftime("%Y-%m-%d"),
        )

    # Database helper methods

    async def _db_get_total_users(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """Get total users count (excluding test users)."""
        if source_id == "all":
            # 排除测试平台
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT COUNT(DISTINCT user_id) as total_users
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
                  AND user_id != 'default'
            """
            row = await self.db.fetch_one(
                query,
                (start_date, end_date, *EXCLUDED_SOURCE_IDS),
            )
        else:
            query = """
                SELECT COUNT(DISTINCT user_id) as total_users
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND user_id != 'default'
            """
            row = await self.db.fetch_one(
                query,
                (source_id, start_date, end_date),
            )
        result = row["total_users"] if row else 0
        return result

    async def _db_get_online_users(
        self,
        source_id: str,
    ) -> tuple[int, list[str]]:
        """Get online users count and IDs (active in last 5 minutes).

        Returns:
            Tuple of (count, list of user IDs)
        """
        online_threshold = datetime.now() - timedelta(minutes=5)
        if source_id == "all":
            query = """
                SELECT DISTINCT user_id
                FROM swe_tracing_spans
                WHERE start_time >= %s AND user_id IS NOT NULL AND user_id != ''
            """
            rows = await self.db.fetch_all(query, (online_threshold,))
        else:
            query = """
                SELECT DISTINCT user_id
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND user_id IS NOT NULL AND user_id != ''
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, online_threshold),
            )
        user_ids = [row["user_id"] for row in rows if row["user_id"]]
        return len(user_ids), user_ids

    async def _db_get_token_stats(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[dict]:
        """Get token statistics (excluding test platforms)."""
        if source_id == "all":
            # 排除测试平台
            exclude_placeholders = ", ".join(["%s"] * len(EXCLUDED_SOURCE_IDS))
            query = f"""
                SELECT
                    SUM(total_input_tokens) as input_tokens,
                    SUM(total_output_tokens) as output_tokens,
                    SUM(total_tokens) as total_tokens,
                    COUNT(*) as total_traces,
                    COUNT(DISTINCT session_id) as total_sessions,
                    AVG(duration_ms) as avg_duration
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s
                  AND source_id NOT IN ({exclude_placeholders})
            """
            return await self.db.fetch_one(
                query,
                (start_date, end_date, *EXCLUDED_SOURCE_IDS),
            )
        else:
            query = """
                SELECT
                    SUM(total_input_tokens) as input_tokens,
                    SUM(total_output_tokens) as output_tokens,
                    SUM(total_tokens) as total_tokens,
                    COUNT(*) as total_traces,
                    COUNT(DISTINCT session_id) as total_sessions,
                    AVG(duration_ms) as avg_duration
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
            """
            return await self.db.fetch_one(
                query,
                (source_id, start_date, end_date),
            )

    async def _db_get_model_distribution(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ModelUsage]:
        """Get model distribution."""
        if source_id == "all":
            query = """
                SELECT model_name, COUNT(*) as count,
                       SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM swe_tracing_traces
                WHERE start_time >= %s AND start_time <= %s AND model_name IS NOT NULL
                GROUP BY model_name
                ORDER BY count DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(query, (start_date, end_date))
        else:
            query = """
                SELECT model_name, COUNT(*) as count,
                       SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM swe_tracing_traces
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s AND model_name IS NOT NULL
                GROUP BY model_name
                ORDER BY count DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, start_date, end_date),
            )
        return [
            ModelUsage(
                model_name=row["model_name"],
                count=row["count"] or 0,
                total_tokens=row["total_tokens"] or 0,
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
            )
            for row in rows
        ]

    async def _db_get_top_tools(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ToolUsage]:
        """Get top tools (non-MCP)."""
        if source_id == "all":
            query = """
                SELECT tool_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND tool_name IS NOT NULL
                  AND mcp_server IS NULL
                GROUP BY tool_name
                ORDER BY count DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(query, (start_date, end_date))
        else:
            query = """
                SELECT tool_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND tool_name IS NOT NULL
                  AND mcp_server IS NULL
                GROUP BY tool_name
                ORDER BY count DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, start_date, end_date),
            )
        return [
            ToolUsage(
                tool_name=row["tool_name"],
                count=row["count"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in rows
        ]

    async def _db_get_top_skills(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[SkillUsage]:
        """Get top skills."""
        if source_id == "all":
            query = """
                SELECT skill_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL
                GROUP BY skill_name
                ORDER BY count DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(query, (start_date, end_date))
        else:
            query = """
                SELECT skill_name, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'skill_invocation'
                  AND skill_name IS NOT NULL
                GROUP BY skill_name
                ORDER BY count DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, start_date, end_date),
            )
        return [
            SkillUsage(
                skill_name=row["skill_name"],
                count=row["count"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in rows
        ]

    async def _db_get_top_skills_with_weights(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[SkillUsage]:
        """Get top skills with usage counts.

        Args:
            start_date: Start date filter
            end_date: End date filter

        Returns:
            List of SkillUsage with counts
        """
        query = """
            SELECT skill_name, COUNT(*) as count, AVG(duration_ms) as avg_duration
            FROM swe_tracing_spans
            WHERE start_time >= %s AND start_time <= %s
              AND event_type = 'tool_call_end'
              AND skill_name IS NOT NULL
            GROUP BY skill_name
            ORDER BY count DESC
            LIMIT 10
        """
        rows = await self.db.fetch_all(query, (start_date, end_date))

        result = []
        for row in rows:
            result.append(
                SkillUsage(
                    skill_name=row["skill_name"],
                    count=row["count"] or 0,
                    weighted_count=float(row["count"] or 0),
                    avg_duration_ms=int(row["avg_duration"] or 0),
                    weighted_duration_ms=int(row["avg_duration"] or 0),
                ),
            )

        return result

    async def _db_get_skill_tool_attribution(
        self,
        skill_name: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, float]:
        """Get tool attribution for a specific skill.

        Returns usage count for each tool used by the skill.

        Args:
            skill_name: Skill identifier
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Dict mapping tool_name -> usage count
        """
        query = """
            SELECT tool_name, COUNT(*) as count
            FROM swe_tracing_spans
            WHERE start_time >= %s AND start_time <= %s
              AND event_type = 'tool_call_end'
              AND tool_name IS NOT NULL
              AND skill_name = %s
            GROUP BY tool_name
            ORDER BY count DESC
        """
        rows = await self.db.fetch_all(
            query,
            (start_date, end_date, skill_name),
        )

        return {row["tool_name"]: float(row["count"] or 0) for row in rows}

    async def _db_get_mcp_stats(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[list[MCPToolUsage], list[MCPServerUsage]]:
        """Get MCP tools and server statistics."""
        # Get top MCP tools
        if source_id == "all":
            mcp_tool_query = """
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
                LIMIT 10
            """
            mcp_tool_rows = await self.db.fetch_all(
                mcp_tool_query,
                (start_date, end_date),
            )
        else:
            mcp_tool_query = """
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
                LIMIT 10
            """
            mcp_tool_rows = await self.db.fetch_all(
                mcp_tool_query,
                (source_id, start_date, end_date),
            )
        top_mcp_tools = [
            MCPToolUsage(
                tool_name=row["tool_name"],
                mcp_server=row["mcp_server"],
                count=row["count"] or 0,
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in mcp_tool_rows
        ]

        # Get MCP server statistics
        mcp_servers = await self._db_get_mcp_servers(
            source_id,
            start_date,
            end_date,
        )

        return top_mcp_tools, mcp_servers

    async def _db_get_mcp_servers(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[MCPServerUsage]:
        """Get MCP server statistics with tools."""
        if source_id == "all":
            query = """
                SELECT mcp_server,
                       COUNT(DISTINCT tool_name) as tool_count,
                       COUNT(*) as total_calls,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                GROUP BY mcp_server
                ORDER BY total_calls DESC
            """
            server_rows = await self.db.fetch_all(
                query,
                (start_date, end_date),
            )
        else:
            query = """
                SELECT mcp_server,
                       COUNT(DISTINCT tool_name) as tool_count,
                       COUNT(*) as total_calls,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server IS NOT NULL
                GROUP BY mcp_server
                ORDER BY total_calls DESC
            """
            server_rows = await self.db.fetch_all(
                query,
                (source_id, start_date, end_date),
            )

        mcp_servers = []
        for server_row in server_rows:
            server_name = server_row["mcp_server"]
            tools = await self._db_get_server_tools(
                source_id,
                start_date,
                end_date,
                server_name,
            )
            mcp_servers.append(
                MCPServerUsage(
                    server_name=server_name,
                    tool_count=server_row["tool_count"] or 0,
                    total_calls=server_row["total_calls"] or 0,
                    avg_duration_ms=int(server_row["avg_duration"] or 0),
                    error_count=server_row["error_count"] or 0,
                    tools=tools,
                ),
            )

        return mcp_servers

    async def _db_get_server_tools(
        self,
        source_id: str,
        start_date: datetime,
        end_date: datetime,
        server_name: str,
    ) -> list[MCPToolUsage]:
        """Get tools for a specific MCP server."""
        if source_id == "all":
            query = """
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server = %s
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
            """
            rows = await self.db.fetch_all(
                query,
                (start_date, end_date, server_name),
            )
        else:
            query = """
                SELECT tool_name, mcp_server, COUNT(*) as count,
                       AVG(duration_ms) as avg_duration,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
                FROM swe_tracing_spans
                WHERE source_id = %s AND start_time >= %s AND start_time <= %s
                  AND event_type = 'tool_call_end'
                  AND mcp_server = %s
                GROUP BY tool_name, mcp_server
                ORDER BY count DESC
            """
            rows = await self.db.fetch_all(
                query,
                (source_id, start_date, end_date, server_name),
            )
        return [
            MCPToolUsage(
                tool_name=r["tool_name"],
                mcp_server=r["mcp_server"],
                count=r["count"] or 0,
                avg_duration_ms=int(r["avg_duration"] or 0),
                error_count=r["error_count"] or 0,
            )
            for r in rows
        ]

    async def _db_get_session_basic_stats(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[dict]:
        """Get basic session stats."""
        query = """
            SELECT
                user_id,
                channel,
                COUNT(*) as total_traces,
                SUM(total_input_tokens) as input_tokens,
                SUM(total_output_tokens) as output_tokens,
                SUM(total_tokens) as total_tokens,
                AVG(duration_ms) as avg_duration,
                MIN(start_time) as first_active,
                MAX(start_time) as last_active
            FROM swe_tracing_traces
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
            GROUP BY user_id, channel
        """
        return await self.db.fetch_one(
            query,
            (source_id, session_id, start_date, end_date),
        )

    async def _db_get_session_model_usage(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ModelUsage]:
        """Get model usage for session."""
        query = """
            SELECT model_name, COUNT(*) as count,
                   SUM(total_input_tokens) as input_tokens,
                   SUM(total_output_tokens) as output_tokens,
                   SUM(total_tokens) as total_tokens
            FROM swe_tracing_traces
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
                  AND model_name IS NOT NULL
            GROUP BY model_name
            ORDER BY count DESC
        """
        rows = await self.db.fetch_all(
            query,
            (source_id, session_id, start_date, end_date),
        )
        return [
            ModelUsage(
                model_name=row["model_name"],
                count=row["count"],
                total_tokens=row["total_tokens"] or 0,
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
            )
            for row in rows
        ]

    async def _db_get_session_tools(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ToolUsage]:
        """Get tool usage for session (non-MCP)."""
        query = """
            SELECT tool_name, COUNT(*) as count,
                   AVG(duration_ms) as avg_duration,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM swe_tracing_spans
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'tool_call_end'
              AND tool_name IS NOT NULL
              AND mcp_server IS NULL
            GROUP BY tool_name
            ORDER BY count DESC
        """
        rows = await self.db.fetch_all(
            query,
            (source_id, session_id, start_date, end_date),
        )
        return [
            ToolUsage(
                tool_name=row["tool_name"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in rows
        ]

    async def _db_get_session_mcp_tools(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[MCPToolUsage]:
        """Get MCP tool usage for session."""
        query = """
            SELECT tool_name, mcp_server, COUNT(*) as count,
                   AVG(duration_ms) as avg_duration,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM swe_tracing_spans
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'tool_call_end'
              AND mcp_server IS NOT NULL
            GROUP BY tool_name, mcp_server
            ORDER BY count DESC
        """
        rows = await self.db.fetch_all(
            query,
            (source_id, session_id, start_date, end_date),
        )
        return [
            MCPToolUsage(
                tool_name=row["tool_name"],
                mcp_server=row["mcp_server"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
                error_count=row["error_count"] or 0,
            )
            for row in rows
        ]

    async def _db_get_session_skills(
        self,
        source_id: str,
        session_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[SkillUsage]:
        """Get skill usage for session."""
        query = """
            SELECT skill_name, COUNT(*) as count,
                   AVG(duration_ms) as avg_duration
            FROM swe_tracing_spans
            WHERE source_id = %s AND session_id = %s AND start_time >= %s AND start_time <= %s
              AND event_type = 'skill_invocation'
              AND skill_name IS NOT NULL
            GROUP BY skill_name
            ORDER BY count DESC
        """
        rows = await self.db.fetch_all(
            query,
            (source_id, session_id, start_date, end_date),
        )
        return [
            SkillUsage(
                skill_name=row["skill_name"],
                count=row["count"],
                avg_duration_ms=int(row["avg_duration"] or 0),
            )
            for row in rows
        ]

    # Row conversion helpers

    def _row_to_trace(self, row: dict) -> Trace:
        """Convert database row to Trace model."""
        return Trace(
            trace_id=row["trace_id"],
            source_id=row["source_id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            channel=row["channel"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            duration_ms=row["duration_ms"],
            model_name=row["model_name"],
            total_input_tokens=row["total_input_tokens"] or 0,
            total_output_tokens=row["total_output_tokens"] or 0,
            tools_used=json.loads(row["tools_used"])
            if row["tools_used"]
            else [],
            skills_used=json.loads(row["skills_used"])
            if row["skills_used"]
            else [],
            status=TraceStatus(row["status"])
            if row["status"]
            else TraceStatus.RUNNING,
            error=row["error"],
            user_message=row.get("user_message"),
        )

    def _row_to_span(self, row: dict) -> Span:
        """Convert database row to Span model."""
        return Span(
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            source_id=row["source_id"],
            name=row["name"],
            event_type=EventType(row["event_type"]),
            start_time=row["start_time"],
            end_time=row["end_time"],
            duration_ms=row["duration_ms"],
            user_id=row.get("user_id") or "",
            session_id=row.get("session_id") or "",
            channel=row.get("channel") or "",
            model_name=row["model_name"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            tool_name=row["tool_name"],
            skill_name=row["skill_name"],
            mcp_server=row.get("mcp_server"),
            tool_input=json.loads(row["tool_input"])
            if row["tool_input"]
            else None,
            tool_output=row["tool_output"],
            error=row["error"],
        )
