## Context

`agent-scoped-llm-rate-limiting` replaced the process-global LLM limiter with a process-local registry keyed by `(effective_tenant_id, agent_id)`. That fixed cross-tenant and cross-agent interference, but every model call inside the same tenant-local agent still competes for the same concurrency semaphore, QPM window, and 429 cooldown.

The runtime has at least two workload classes with different service expectations:

```text
tenant-local agent
  |-- chat: HTTP, console, and channel-originated user requests
  `-- cron: scheduler callbacks, manual run_job, and heartbeat work
```

Cron already has `job.runtime.max_concurrency`, but that controls execution of a single cron job, not model-call concurrency across all scheduler-originated LLM calls in the agent. A single agent can therefore have several cron/heartbeat model calls consume the same slots that user chat needs.

## Goals / Non-Goals

**Goals:**

- Separate chat and scheduler LLM concurrency inside each tenant-local agent.
- Preserve backwards compatibility for agents that only configure `llm_max_concurrent` and `llm_acquire_timeout`.
- Preserve shared QPM and 429 cooldown protection per tenant-local agent by default.
- Make workload identity visible in timeout/log diagnostics.
- Keep the implementation process-local and aligned with the existing limiter registry.

**Non-Goals:**

- Distributed or Redis-backed LLM concurrency.
- Provider-scoped, model-scoped, or API-key-scoped quota enforcement.
- Changing cron job execution semantics beyond LLM concurrency classification.
- Strict once-per-tick scheduler execution behavior.
- Reworking token usage, tracing, or session persistence.

## Decisions

### Decision 1: Add a workload dimension only to concurrency acquisition

**Choice:** Introduce a workload identity for LLM calls, with initial values `chat` and `cron`. The concurrency pool is selected by `(effective_tenant_id, agent_id, workload)`, while QPM and 429 cooldown continue to be enforced at `(effective_tenant_id, agent_id)`.

**Rationale:**

- The user-visible problem is chat starvation caused by scheduler work consuming all agent slots.
- QPM windows and 429 cooldowns are usually responses to shared upstream quota. Splitting them by workload could allow cron and chat to bypass each other's provider backpressure.
- This keeps the first iteration focused: isolate responsiveness without weakening provider protection.

**Alternatives considered:**

- Split the entire limiter by workload: simpler mechanically, but duplicates QPM/cooldown state and can amplify upstream 429s.
- Keep one limiter and add priority queueing: more complex and still allows cron to hold all active slots once admitted.
- Add only a cron semaphore outside provider code: would not cover model calls from shared wrappers or future scheduler paths consistently.

### Decision 2: Classify scheduler-originated work broadly as `cron`

**Choice:** Scheduled cron callbacks, manual `run_job`, and heartbeat execution all use workload `cron` for LLM concurrency.

**Rationale:**

- Manual `run_job` is operator-triggered, but it still executes the task pipeline and should not consume user-chat slots.
- Heartbeat is scheduler-managed background work and should follow the same background concurrency budget.
- Keeping only two workload classes makes configuration understandable.

**Alternatives considered:**

- Add a separate `heartbeat` workload: useful if heartbeat load becomes operationally distinct, but unnecessary for the first iteration.
- Treat manual `run_job` as chat: would preserve immediate operator intent, but it can still starve actual conversational traffic.

### Decision 3: Use context propagation for workload identity

**Choice:** Add a context variable/helper for current LLM workload. Chat entry points bind or default to `chat`; cron and heartbeat execution bind `cron`. `RetryChatModel` resolves workload at call time and passes it to the limiter registry.

**Rationale:**

- Model construction can happen before the final execution source is known in some paths. Resolving at call time avoids baking the wrong workload into a reusable model wrapper.
- Context propagation matches existing tenant and agent context patterns.
- It keeps direct model calls compatible: no explicit workload means `chat`.

**Alternatives considered:**

- Pass workload through every `create_model_and_formatter()` call: explicit but invasive and easy to miss.
- Store workload on `AgentRunner`: insufficient because scheduler code can enter through the same runner object as chat.

### Decision 4: Keep compatibility through fallback config values

**Choice:** Add optional workload-specific fields such as `llm_chat_max_concurrent`, `llm_cron_max_concurrent`, `llm_chat_acquire_timeout`, and `llm_cron_acquire_timeout`. If a workload-specific value is unset, use the existing `llm_max_concurrent` or `llm_acquire_timeout`.

**Rationale:**

- Existing tenant-agent configs keep their current behavior until operators choose separate budgets.
- Flat fields match the current `AgentsRunningConfig` style.
- Separate acquire timeouts let chat fail faster while cron can wait longer if desired.

**Alternatives considered:**

- Introduce a nested `llm_concurrency` object: cleaner long-term, but a larger config/API migration.
- Change the meaning of existing `llm_max_concurrent` to a total cap plus add workload caps: stronger resource control, but surprising and harder to roll out safely.

### Decision 5: Preserve cron job runtime concurrency

**Choice:** `JobRuntimeSpec.max_concurrency` remains the per-job execution concurrency gate. The new cron LLM pool is an additional model-call budget shared across scheduler-originated LLM calls for the tenant-local agent.

**Rationale:**

- Per-job execution concurrency and LLM model-call concurrency protect different resources.
- Keeping both avoids changing cron scheduling behavior.

## Risks / Trade-offs

- [Total tenant-agent LLM concurrency can increase when both chat and cron pools are configured above the old single limit] -> Keep defaults compatible by using existing values unless workload-specific settings are configured, and document that workload values are additive unless a future total cap is introduced.
- [Shared QPM/cooldown can still delay chat after cron triggers upstream rate limiting] -> This is intentional provider protection; operators can reduce cron concurrency if it repeatedly causes cooldown.
- [Missing workload binding could put background work into the chat pool] -> Add tests around cron executor, manual run, heartbeat, and default direct model calls.
- [Context variables can leak if manually set without reset] -> Provide a context manager helper and avoid raw set/reset at call sites.
- [Future workload classes may need different treatment] -> Keep workload values typed/centralized so adding `maintenance` or `heartbeat` later is local.

## Migration Plan

1. Add workload context helpers with `chat` as the default.
2. Extend rate-limiter scope/config structures to distinguish shared agent state from workload concurrency state.
3. Add optional workload-specific agent running config fields with fallback to existing values.
4. Bind `cron` workload around cron executor, manual job execution, and heartbeat execution; keep chat/default paths on `chat`.
5. Add regression tests for chat/cron concurrency isolation, shared cooldown/QPM behavior, config fallback, and diagnostics.
6. Roll back by ignoring workload-specific config and resolving all calls to the existing tenant-agent concurrency pool.

## Open Questions

- Should a later change add an optional tenant-agent total LLM cap above the two workload pools?
- Should API/admin UI expose workload-specific LLM settings immediately, or can the first implementation be config-file only?
