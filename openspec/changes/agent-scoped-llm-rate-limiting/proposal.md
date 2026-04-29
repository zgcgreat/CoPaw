## Why

LLM concurrency and rate-limit control is currently process-global, so one tenant-local agent can consume all in-flight model slots or trigger a cooldown that delays unrelated agents. This conflicts with the multi-agent runtime model where agents are tenant-local execution units with separate runtime configuration.

## What Changes

- Replace the single process-wide LLM rate-limiter singleton with scoped limiter instances keyed by `(effective_tenant_id, agent_id)`.
- Make each agent's `llm_max_concurrent`, `llm_max_qpm`, rate-limit pause, jitter, and acquire-timeout settings apply only to that agent scope.
- Ensure different tenants with the same `agent_id`, including `default`, do not share LLM limiter state.
- Preserve the existing retry, QPM window, semaphore, 429 cooldown, and streaming slot-release behavior within each scoped limiter.
- Keep the first implementation process-local; cross-pod or Redis-backed distributed LLM limiting is explicitly out of scope.

## Capabilities

### New Capabilities

- `agent-scoped-llm-rate-limiting`: Model-call concurrency, QPM throttling, and 429 cooldown isolation per tenant-local agent.

### Modified Capabilities

- None.

## Impact

- Affected model-call paths: `src/swe/providers/rate_limiter.py`, `src/swe/providers/retry_chat_model.py`, `src/swe/agents/model_factory.py`
- Affected context/config paths: `src/swe/app/agent_context.py`, `src/swe/config/context.py`, `src/swe/config/config.py`
- Affected tests: focused unit tests for limiter registry scoping, `RetryChatModel` limiter lookup, and model factory config propagation
- Documentation impact: update resource-control notes that currently describe model-call limiting as global/shared across all agents
