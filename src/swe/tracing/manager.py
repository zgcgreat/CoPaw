# -*- coding: utf-8 -*-
"""Trace manager module.

Provides the TraceManager for event collection, batching, and storage.
"""
import asyncio
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any, Optional

from .config import TracingConfig
from ..database import DatabaseConnection
from .models import EventType, Span, Trace, TraceStatus
from .store import TraceStore
from .sanitizer import sanitize_dict, sanitize_string

logger = logging.getLogger(__name__)

# Context variable for current trace
_current_trace: ContextVar[Optional["TraceContext"]] = ContextVar(
    "current_trace",
    default=None,
)


class TraceContext:
    """Context for the current trace."""

    def __init__(
        self,
        trace_id: str,
        user_id: str,
        session_id: str,
        channel: str,
        source_id: str,
    ):
        self.trace_id = trace_id
        self.user_id = user_id
        self.session_id = session_id
        self.channel = channel
        self.source_id = source_id
        self.start_time = datetime.now()
        self.trace: Optional[Trace] = None
        self._span_stack: list[str] = []
        self._active_skills: list[str] = []  # Active skill context stack
        self.skill_detector: Optional[Any] = None  # SkillInvocationDetector
        self.enabled_skills: list[str] = []  # Skills enabled for this trace

    def push_span(self, span_id: str) -> None:
        """Push a span ID onto the stack."""
        self._span_stack.append(span_id)

    def pop_span(self) -> Optional[str]:
        """Pop a span ID from the stack."""
        return self._span_stack.pop() if self._span_stack else None

    @property
    def current_span_id(self) -> Optional[str]:
        """Get current span ID."""
        return self._span_stack[-1] if self._span_stack else None

    def push_skill(self, skill_name: str) -> None:
        """Push a skill onto the active skill stack."""
        self._active_skills.append(skill_name)

    def pop_skill(self) -> Optional[str]:
        """Pop a skill from the active skill stack."""
        return self._active_skills.pop() if self._active_skills else None

    @property
    def current_skill(self) -> Optional[str]:
        """Get the currently active skill (top of stack)."""
        return self._active_skills[-1] if self._active_skills else None

    @property
    def active_skills(self) -> list[str]:
        """Get all active skills in the stack (copy)."""
        return list(self._active_skills)

    def set_skill_detector(
        self,
        detector: Any,
        enabled_skills: list[str],
    ) -> None:
        """Set the skill invocation detector.

        Args:
            detector: SkillInvocationDetector instance
            enabled_skills: List of enabled skill names
        """
        self.skill_detector = detector
        self.enabled_skills = enabled_skills


def get_current_trace() -> Optional[TraceContext]:
    """Get the current trace context."""
    return _current_trace.get()


def set_current_trace(ctx: Optional[TraceContext]) -> None:
    """Set the current trace context."""
    _current_trace.set(ctx)


class TraceManager:
    """Manager for trace lifecycle and event collection.

    Handles:
    - Trace creation and completion
    - Span creation and updates
    - Batch writing for performance
    - Data sanitization
    """

    def __init__(
        self,
        config: TracingConfig,
        db: Optional[DatabaseConnection] = None,
    ):
        """Initialize trace manager.

        Args:
            config: Tracing configuration
            db: Optional database connection (can also be set during initialize).
                If provided, the connection is considered shared and will not be
                closed by this manager.
        """
        self.config = config
        self._store: Optional[TraceStore] = None
        self._db = db
        self._owns_db = db is None  # Only owns DB if we create it ourselves

        # Batch queue for spans
        self._span_queue: list[Span] = []
        self._span_queue_lock = asyncio.Lock()

        # Pending spans cache (for update before flush)
        self._pending_spans: dict[str, Span] = {}

        # Background flush task
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

        # Active traces
        self._active_traces: dict[str, Trace] = {}

    @property
    def store(self) -> TraceStore:
        """Get trace store."""
        if self._store is None:
            raise RuntimeError(
                "TraceManager not initialized or tracing is disabled",
            )
        return self._store

    @property
    def enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self.config.enabled

    @property
    def is_running(self) -> bool:
        """Check if the trace manager is running."""
        return self._running

    async def initialize(self) -> None:
        """Initialize the trace manager.

        If database connection is available, uses database storage.
        Otherwise, runs in log-only mode for debugging.
        """
        if not self.config.enabled:
            logger.info("Tracing is disabled")
            return

        # Try to create database connection if not provided
        if self._db is None and self.config.database:
            try:
                self._db = DatabaseConnection(self.config.database)
                await self._db.connect()
                self._owns_db = True  # We created it, so we own it
                logger.info(
                    "Database connection established: %s",
                    self.config.database.host,
                )
            except Exception as e:
                logger.warning(
                    "Failed to connect to database, using log-only mode: %s",
                    e,
                )
                self._db = None

        # Create store (with or without database)
        self._store = TraceStore(self.config, self._db, owns_db=self._owns_db)
        await self._store.initialize()

        # Start flush task only if we have a database
        self._running = True
        if self._db is not None:
            self._flush_task = asyncio.create_task(self._flush_loop())

        # Start cleanup task if retention is configured
        self._cleanup_task: Optional[asyncio.Task] = None
        if self.config.retention_days > 0:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(
            "TraceManager initialized (database=%s, mode=%s)",
            self.config.database.host if self.config.database else "N/A",
            "database" if self._db else "log-only",
        )

    async def close(self) -> None:
        """Close the trace manager."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        # Final flush
        await self._flush_spans()

        if self._store:
            await self._store.flush()
            await self._store.close()

        logger.info("TraceManager closed")

    # Trace lifecycle

    async def start_trace(
        self,
        user_id: str,
        session_id: str,
        channel: str,
        source_id: str,
        trace_id: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> str:
        """Start a new trace.

        Args:
            user_id: User identifier
            session_id: Session identifier
            channel: Channel identifier
            source_id: Source identifier for data isolation
            trace_id: Optional trace ID (generated if not provided)
            user_message: Optional user's input message

        Returns:
            Trace ID
        """
        if not self.enabled:
            return trace_id or str(uuid.uuid4())

        trace_id = trace_id or str(uuid.uuid4())

        # Sanitize user message
        if self.config.sanitize_output and user_message:
            user_message = sanitize_string(
                user_message,
                self.config.max_output_length,
            )

        trace = Trace(
            trace_id=trace_id,
            source_id=source_id,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            start_time=datetime.now(),
            status=TraceStatus.RUNNING,
            user_message=user_message,
        )

        await self.store.create_trace(trace)
        self._active_traces[trace_id] = trace

        # Create context
        ctx = TraceContext(trace_id, user_id, session_id, channel, source_id)
        ctx.trace = trace
        set_current_trace(ctx)

        return trace_id

    async def setup_skill_detector(
        self,
        trace_id: str,
        enabled_skills: list[str],
    ) -> None:
        """Set up skill invocation detector for a trace.

        This should be called after start_trace() to enable skill
        detection during the trace. Also performs Layer 0 detection
        on the user message if available.

        Args:
            trace_id: Trace identifier
            enabled_skills: List of skill names enabled for this trace
        """
        if not self.enabled:
            return

        ctx = get_current_trace()
        if not ctx or ctx.trace_id != trace_id:
            return

        try:
            from ..agents.skill_invocation_detector import (
                SkillInvocationDetector,
            )
            from ..agents.skill_context_manager import (
                get_skill_context_manager,
            )
            from ..agents.skill_tool_registry import get_skill_tool_registry

            # Create detector with dependencies
            detector = SkillInvocationDetector(
                registry=get_skill_tool_registry(),
                context_manager=get_skill_context_manager(),
                trace_manager=self,
                trace_id=trace_id,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                channel=ctx.channel,
                source_id=ctx.source_id,
            )
            detector.set_enabled_skills(enabled_skills)

            # Attach to context
            ctx.set_skill_detector(detector, enabled_skills)

            # Layer 0: Detect skill from user message
            if ctx.trace and ctx.trace.user_message:
                skill, confidence = detector.detect_from_user_message(
                    ctx.trace.user_message,
                )
                if skill:
                    logger.info(
                        "Layer 0 result: skill='%s', confidence=%.2f",
                        skill,
                        confidence,
                    )
                if skill and confidence >= 0.7:
                    # Start skill through detector to properly track span_id
                    await detector.start_skill(
                        skill_name=skill,
                        trigger_tool="user_message",
                        trigger_reason="declared",
                        confidence=confidence,
                    )
                    logger.info(
                        "Skill started: '%s' (confidence: %.2f)",
                        skill,
                        confidence,
                    )
                elif skill:
                    logger.info(
                        "Skill detected but confidence too low: '%s' (confidence: %.2f < 0.5)",
                        skill,
                        confidence,
                    )
        except Exception as e:
            logger.warning("Failed to setup skill detector: %s", e)

    async def end_trace(
        self,
        trace_id: str,
        status: TraceStatus = TraceStatus.COMPLETED,
        error: Optional[str] = None,
    ) -> None:
        """End a trace.

        Args:
            trace_id: Trace identifier
            status: Final status
            error: Optional error message
        """
        if not self.enabled:
            return

        # Flush pending spans before ending trace
        await self._flush_spans()

        # End skill detection
        ctx = get_current_trace()
        if ctx and ctx.trace_id == trace_id and ctx.skill_detector:
            try:
                await ctx.skill_detector.on_reasoning_end()
            except Exception as e:
                logger.warning("Failed to end skill detection: %s", e)

        trace = self._active_traces.pop(
            trace_id,
            None,
        ) or await self.store.get_trace(trace_id)
        if trace is None:
            logger.warning("Trace not found: %s", trace_id)
            return

        trace.end_time = datetime.now()
        trace.duration_ms = int(
            (trace.end_time - trace.start_time).total_seconds() * 1000,
        )
        trace.status = status
        trace.error = error

        await self.store.update_trace(trace)

        # Clear context
        if ctx and ctx.trace_id == trace_id:
            set_current_trace(None)

    # Span operations

    async def emit_span(
        self,
        trace_id: str,
        event_type: EventType,
        name: str,
        source_id: str,
        user_id: str = "",
        session_id: str = "",
        channel: str = "",
        model_name: Optional[str] = None,
        input_tokens: Optional[int] = None,
        tool_name: Optional[str] = None,
        skill_name: Optional[str] = None,
        tool_input: Optional[dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        mcp_server: Optional[str] = None,
    ) -> str:
        """Emit a new span event.

        Args:
            trace_id: Trace identifier
            event_type: Event type
            name: Span name
            source_id: Source identifier for data isolation
            user_id: User identifier
            session_id: Session identifier
            channel: Channel identifier
            model_name: Optional model name
            input_tokens: Optional input token count
            tool_name: Optional tool name
            skill_name: Optional skill name
            tool_input: Optional tool input (will be sanitized)
            start_time: Optional start time
            mcp_server: Optional MCP server name if this is an MCP tool

        Returns:
            Span ID
        """
        if not self.enabled:
            return str(uuid.uuid4())

        span_id = str(uuid.uuid4())

        # Sanitize tool input if configured
        if self.config.sanitize_output and tool_input:
            tool_input = sanitize_dict(
                tool_input,
                self.config.max_output_length,
            )

        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            source_id=source_id,
            name=name,
            event_type=event_type,
            start_time=start_time or datetime.now(),
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            model_name=model_name,
            input_tokens=input_tokens,
            tool_name=tool_name,
            skill_name=skill_name,
            tool_input=tool_input,
            mcp_server=mcp_server,
        )

        # Update trace statistics (skills_used, tools_used)
        self._update_trace_totals(trace_id, span, None)

        # Add to pending cache and queue atomically
        async with self._span_queue_lock:
            self._pending_spans[span_id] = span
            self._span_queue.append(span)

            # Check if we need to flush
            if len(self._span_queue) >= self.config.batch_size:
                asyncio.create_task(self._flush_spans())

        return span_id

    async def update_span(
        self,
        span_id: str,
        trace_id: str,
        output_tokens: Optional[int] = None,
        input_tokens: Optional[int] = None,
        tool_output: Optional[str] = None,
        error: Optional[str] = None,
        span: Optional[Span] = None,
    ) -> None:
        """Update an existing span.

        Args:
            span_id: Span identifier
            trace_id: Trace identifier
            output_tokens: Optional output token count
            input_tokens: Optional input token count (updates span if provided)
            tool_output: Optional tool output (will be sanitized)
            error: Optional error message
            span: Optional span object (to avoid re-fetching)
        """
        if not self.enabled:
            return

        span = await self._find_span(span_id, trace_id, span)
        if span is None:
            logger.warning("Span not found for update: %s", span_id)
            return

        self._update_span_fields(
            span,
            output_tokens,
            input_tokens,
            tool_output,
            error,
        )
        self._update_trace_totals(trace_id, span, output_tokens)

        # Persist if not in pending cache
        if span_id not in self._pending_spans:
            await self.store.update_span(span)

    async def _find_span(
        self,
        span_id: str,
        trace_id: str,
        span: Optional[Span],
    ) -> Optional[Span]:
        """Find span from cache or store."""
        if span is not None:
            return span

        # Check pending cache first
        span = self._pending_spans.get(span_id)
        if span is not None:
            return span

        # Check store
        spans = await self.store.get_spans(trace_id)
        for s in spans:
            if s.span_id == span_id:
                return s

        return None

    def _update_span_fields(
        self,
        span: Span,
        output_tokens: Optional[int],
        input_tokens: Optional[int],
        tool_output: Optional[str],
        error: Optional[str],
    ) -> None:
        """Update span fields."""
        span.end_time = datetime.now()
        span.duration_ms = int(
            (span.end_time - span.start_time).total_seconds() * 1000,
        )
        span.output_tokens = output_tokens
        if input_tokens is not None and input_tokens > 0:
            span.input_tokens = input_tokens
        span.tool_output = (
            sanitize_string(tool_output, self.config.max_output_length)
            if self.config.sanitize_output
            else tool_output
        )
        span.error = error

    def _update_trace_totals(
        self,
        trace_id: str,
        span: Span,
        output_tokens: Optional[int],
    ) -> None:
        """Update trace statistics from span."""
        trace = self._active_traces.get(trace_id)
        if not trace:
            return

        if output_tokens:
            trace.total_output_tokens += output_tokens
        if span.input_tokens:
            trace.total_input_tokens += span.input_tokens
        if span.model_name:
            trace.model_name = span.model_name
        if span.tool_name and span.tool_name not in trace.tools_used:
            trace.tools_used.append(span.tool_name)
        if span.skill_name and span.skill_name not in trace.skills_used:
            trace.skills_used.append(span.skill_name)

    async def emit_llm_input(
        self,
        trace_id: str,
        model_name: str,
        input_tokens: int,
        source_id: str,
        user_id: str = "",
        session_id: str = "",
        channel: str = "",
    ) -> str:
        """Emit LLM input event.

        Args:
            trace_id: Trace identifier
            model_name: Model name
            input_tokens: Input token count
            source_id: Source identifier for data isolation
            user_id: User identifier
            session_id: Session identifier
            channel: Channel identifier

        Returns:
            Span ID
        """
        return await self.emit_span(
            trace_id=trace_id,
            event_type=EventType.LLM_INPUT,
            name=f"llm_call_{model_name}",
            source_id=source_id,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            model_name=model_name,
            input_tokens=input_tokens,
        )

    async def emit_llm_output(
        self,
        trace_id: str,
        span_id: str,
        output_tokens: int,
        input_tokens: int = 0,
    ) -> None:
        """Emit LLM output event (updates the span).

        Args:
            trace_id: Trace identifier
            span_id: Span identifier from LLM input
            output_tokens: Output token count
            input_tokens: Input token count (updates span if provided)
        """
        await self.update_span(
            span_id=span_id,
            trace_id=trace_id,
            output_tokens=output_tokens,
            input_tokens=input_tokens if input_tokens > 0 else None,
        )

    async def emit_tool_call_start(
        self,
        trace_id: str,
        tool_name: str,
        tool_input: Optional[dict[str, Any]],
        source_id: str,
        user_id: str = "",
        session_id: str = "",
        channel: str = "",
        mcp_server: Optional[str] = None,
    ) -> str:
        """Emit tool call start event with multi-skill attribution.

        This method uses the SkillInvocationDetector to determine skill
        attribution, which combines explicit declarations and inference
        for comprehensive coverage.

        Args:
            trace_id: Trace identifier
            tool_name: Tool name
            tool_input: Tool input
            source_id: Source identifier for data isolation
            user_id: User identifier
            session_id: Session identifier
            channel: Channel identifier
            mcp_server: Optional MCP server name if this is an MCP tool

        Returns:
            Span ID
        """
        # Determine skill attribution using detector
        ctx = get_current_trace()
        primary_skill: Optional[str] = None

        if ctx and ctx.trace_id == trace_id:
            try:
                # Use the detector if available on context
                detector = getattr(ctx, "skill_detector", None)
                if detector:
                    primary_skill, _ = await detector.on_tool_call(
                        tool_name=tool_name,
                        tool_input=tool_input or {},
                        mcp_server=mcp_server,
                    )
                else:
                    # Fallback to registry-based attribution
                    from ..agents.skill_tool_registry import (
                        get_skill_tool_registry,
                    )

                    registry = get_skill_tool_registry()

                    declared_skills = registry.get_skills_for_tool(tool_name)
                    active_skills = ctx.active_skills
                    all_skills = list(set(active_skills + declared_skills))

                    if all_skills:
                        primary_skill = sorted(all_skills)[0]
            except Exception as e:
                logger.warning("Failed to resolve skill attribution: %s", e)

        return await self.emit_span(
            trace_id=trace_id,
            event_type=EventType.TOOL_CALL_START,
            name=f"tool_{tool_name}",
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            source_id=source_id,
            tool_name=tool_name,
            tool_input=tool_input,
            mcp_server=mcp_server,
            skill_name=primary_skill,
        )

    async def emit_tool_call_end(
        self,
        trace_id: str,
        span_id: str,
        tool_output: Optional[str],
        error: Optional[str] = None,
    ) -> None:
        """Emit tool call end event.

        Args:
            trace_id: Trace identifier
            span_id: Span identifier from tool call start
            tool_output: Tool output
            error: Optional error message
        """
        # First, find the span (in pending cache or store)
        span = self._pending_spans.get(span_id)
        if span is None:
            spans = await self.store.get_spans(trace_id)
            for s in spans:
                if s.span_id == span_id:
                    span = s
                    break

        if span is None:
            logger.warning("Span not found for tool_call_end: %s", span_id)
            return

        # Update event_type to TOOL_CALL_END for proper statistics
        span.event_type = EventType.TOOL_CALL_END

        # Update other fields, passing the span object to avoid re-fetching
        await self.update_span(
            span_id=span_id,
            trace_id=trace_id,
            tool_output=tool_output,
            error=error,
            span=span,
        )

    async def emit_skill_invocation(
        self,
        trace_id: str,
        skill_name: str,
        source_id: str,
        user_id: str = "",
        session_id: str = "",
        channel: str = "",
        skill_input: Optional[dict[str, Any]] = None,
    ) -> str:
        """Emit skill invocation event.

        Args:
            trace_id: Trace identifier
            skill_name: Skill name
            source_id: Source identifier for data isolation
            user_id: User identifier
            session_id: Session identifier
            channel: Channel identifier
            skill_input: Optional skill input parameters

        Returns:
            Span ID
        """
        return await self.emit_span(
            trace_id=trace_id,
            event_type=EventType.SKILL_INVOCATION,
            name=f"skill_{skill_name}",
            source_id=source_id,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            skill_name=skill_name,
            tool_input=skill_input,
        )

    async def end_skill_invocation(
        self,
        trace_id: str,
        span_id: str,
        skill_output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """End skill invocation event.

        Args:
            trace_id: Trace identifier
            span_id: Span identifier from skill invocation
            skill_output: Optional skill output
            error: Optional error message
        """
        await self.update_span(
            span_id=span_id,
            trace_id=trace_id,
            tool_output=skill_output,
            error=error,
        )

    # Background flush

    async def _flush_loop(self) -> None:
        """Background loop for flushing queued spans."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval)
                await self._flush_spans()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in flush loop: %s", e)

    async def _flush_spans(self) -> None:
        """Flush queued spans to storage."""
        async with self._span_queue_lock:
            if not self._span_queue:
                return
            spans = self._span_queue.copy()
            self._span_queue.clear()
            # Clear pending cache atomically with queue clear
            for span in spans:
                self._pending_spans.pop(span.span_id, None)

        if spans:
            try:
                if self._db is None:
                    # Log-only mode: output spans directly (only skill-related)
                    for span in spans:
                        if span.skill_name:
                            logger.info(
                                "[SKILL SPAN] skill='%s', type=%s",
                                span.skill_name,
                                span.event_type.value
                                if hasattr(span.event_type, "value")
                                else span.event_type,
                            )
                else:
                    await self.store.batch_create_spans(spans)
            except Exception as e:
                logger.error("Failed to flush spans: %s", e)

    async def _cleanup_loop(self) -> None:
        """Background loop for cleaning up old trace data."""
        # Run cleanup once per day (at startup and then every 24 hours)
        while self._running:
            try:
                # Initial cleanup on startup
                await self._cleanup_old_data()

                # Wait 24 hours between cleanups
                await asyncio.sleep(24 * 60 * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup loop: %s", e)
                # Wait 1 hour before retry on error
                await asyncio.sleep(60 * 60)

    async def _cleanup_old_data(self) -> None:
        """Clean up trace data older than retention period."""
        if self.config.retention_days <= 0:
            return

        try:
            cutoff_date = datetime.now() - timedelta(
                days=self.config.retention_days,
            )
            logger.info(
                "Cleaning up trace data older than %s (retention: %d days)",
                cutoff_date.strftime("%Y-%m-%d"),
                self.config.retention_days,
            )

            # Clean up database data older than retention period
            await self.store.cleanup_old_data(cutoff_date)

        except Exception as e:
            logger.error("Failed to cleanup old data: %s", e)


# Global trace manager instance
_trace_manager: Optional[TraceManager] = None


def get_trace_manager() -> TraceManager:
    """Get the global trace manager.

    Raises:
        RuntimeError: If trace manager not initialized

    Returns:
        TraceManager instance
    """
    if _trace_manager is None:
        raise RuntimeError(
            "TraceManager not initialized. Call init_trace_manager() first.",
        )
    return _trace_manager


def has_trace_manager() -> bool:
    """Check if trace manager is initialized."""
    return _trace_manager is not None


async def init_trace_manager(
    config: Optional[TracingConfig] = None,
    db: Optional[DatabaseConnection] = None,
) -> TraceManager:
    """Initialize the global trace manager.

    Args:
        config: Optional tracing configuration (uses defaults if not provided)
        db: Optional database connection

    Returns:
        TraceManager instance
    """
    global _trace_manager

    if _trace_manager is not None:
        return _trace_manager

    config = config or TracingConfig()
    manager = TraceManager(config, db)
    try:
        await manager.initialize()
        _trace_manager = manager
    except Exception as e:
        # Clean up on failure - don't leave partially initialized manager
        logger.error("Failed to initialize TraceManager: %s", e)
        if manager.is_running:
            await manager.close()
        _trace_manager = None
        raise

    return _trace_manager


async def close_trace_manager() -> None:
    """Close the global trace manager."""
    global _trace_manager

    if _trace_manager is not None:
        await _trace_manager.close()
        _trace_manager = None
