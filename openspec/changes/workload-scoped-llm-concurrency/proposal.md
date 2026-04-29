## Why

LLM limiting is now isolated per tenant-local agent, but chat traffic and scheduler-originated work inside the same agent still share one concurrency pool. A burst of cron, manual job, or heartbeat model calls can therefore consume all agent slots and delay user-facing chat, even though the two workload classes have different latency expectations.

## What Changes

- Add workload-aware LLM concurrency inside each `(effective_tenant_id, agent_id)` scope.
- Classify normal user/channel/HTTP chat execution as `chat` workload.
- Classify scheduled cron execution, manual cron `run_job`, and heartbeat execution as `cron` workload for LLM concurrency purposes.
- Add chat-specific and cron-specific LLM concurrency and acquire-timeout configuration, falling back to the existing agent values when unset.
- Preserve shared tenant-agent QPM and 429 cooldown behavior by default so workload concurrency isolation does not bypass upstream provider quota protection.
- Include workload identity in limiter diagnostics and acquire-timeout errors.

## Capabilities

### New Capabilities
- `workload-scoped-llm-concurrency`: Separates chat and scheduler LLM concurrency pools within a tenant-local agent while preserving shared quota and cooldown protection.

### Modified Capabilities
- None.

## Impact

- Affected provider paths: `src/swe/providers/rate_limiter.py`, `src/swe/providers/retry_chat_model.py`.
- Affected model construction/config paths: `src/swe/agents/model_factory.py`, `src/swe/config/config.py`, `src/swe/constant.py`.
- Affected workload context paths: `src/swe/app/runner/runner.py`, `src/swe/app/channels/base.py`, `src/swe/app/crons/executor.py`, `src/swe/app/crons/manager.py`, heartbeat execution paths.
- Tests should cover chat/cron concurrency isolation, shared QPM/cooldown behavior, default compatibility, and workload diagnostics.
