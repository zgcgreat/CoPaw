## Context

The current LLM limiter is a module-level singleton in `src/swe/providers/rate_limiter.py`. Every `RetryChatModel` call obtains that singleton, so the semaphore, QPM sliding window, and 429 cooldown are shared by all agents and tenants in the same Python process. Agent-specific running configuration is loaded in `model_factory.py`, but only the first limiter initialization actually applies the supplied limit values.

The runtime already treats an agent as tenant-local rather than globally unique. `MultiAgentManager` keys workspaces by `tenant_id:agent_id`, and request execution sets an agent context before model construction. Therefore a correct agent-scoped limiter key must include both the effective runtime tenant and the agent id.

Current shape:

```text
all LLM calls in one process
        |
        v
global LLMRateLimiter
  - semaphore
  - QPM window
  - 429 cooldown
```

Target shape:

```text
LLM call
  |
  v
resolve scope = (effective_tenant_id, agent_id)
  |
  v
LimiterRegistry
  |-- tenant-a:agent-x -> LLMRateLimiter
  |-- tenant-a:agent-y -> LLMRateLimiter
  `-- tenant-b:default -> LLMRateLimiter
```

## Goals / Non-Goals

**Goals:**

- Isolate LLM concurrency, QPM throttling, and 429 cooldown per tenant-local agent.
- Make each agent's running LLM limiter configuration apply to that agent's limiter instance.
- Prevent different tenants with the same `agent_id` from sharing limiter state.
- Preserve existing retry behavior, call timeout behavior, streaming behavior, and limiter semantics inside each scope.
- Keep the implementation process-local and compatible with the current async runtime.

**Non-Goals:**

- Cross-pod or cluster-wide LLM rate limiting.
- Redis-backed distributed semaphore or distributed QPM accounting.
- Provider-scoped or model-scoped throttling.
- Changing tenant provider configuration isolation.
- Changing token usage accounting or tracing semantics.

## Decisions

### Decision 1: Scope limiter instances by `(effective_tenant_id, agent_id)`

**Choice:** Introduce a stable limiter scope key containing the effective runtime tenant id and agent id. The tenant component should use `get_current_effective_tenant_id()` so default+source isolation remains consistent with runtime storage. Missing tenant ids should normalize to a stable default bucket, and missing agent ids should use the existing active/default agent fallback.

**Rationale:**

- Agent ids are tenant-local in the current runtime, so bare `agent_id` would incorrectly merge `tenant-a/default` and `tenant-b/default`.
- The existing `MultiAgentManager` cache key already encodes the same tenant-local agent identity.
- Keeping the fallback behavior preserves compatibility for code paths that construct a model outside an explicitly scoped request.

**Alternatives considered:**

- Key by `agent_id` only: rejected because same-name agents across tenants would share limiter state.
- Key by tenant only: rejected because it does not satisfy agent-scoped isolation.
- Key by provider or model: useful for future upstream-quota control, but it would not isolate agents and would change a different operational dimension.

### Decision 2: Replace the singleton with a process-local registry

**Choice:** Replace `_global_limiter` with a registry mapping `RateLimiterScopeKey` to scoped limiter entries. The existing `LLMRateLimiter` class should remain the per-scope primitive, while `get_rate_limiter(...)` becomes scope-aware.

**Rationale:**

- The semaphore, QPM window, and cooldown logic are already correct within one limiter instance.
- A registry is the smallest change that fixes scope without rewriting retry behavior.
- Keeping the registry process-local matches the current deployment behavior and avoids introducing a distributed coordination dependency in this change.

**Alternatives considered:**

- Create a new limiter object inside every `RetryChatModel`: rejected because multiple model instances for the same agent would not share state.
- Store limiter instances on `Workspace`: possible, but it would couple provider retry behavior to workspace lifecycle and would miss model calls outside workspace-owned paths.

### Decision 3: Use config fingerprint replacement for runtime config changes

**Choice:** Store a normalized config fingerprint with each registry entry. If a later request for the same scope arrives with different limiter settings, create a new limiter entry for subsequent requests. In-flight calls that already captured the old limiter continue naturally.

**Rationale:**

- Current behavior says "first initialization wins", which makes agent running config misleading.
- Reconfiguring an existing semaphore in place is error-prone when slots are already acquired.
- Swapping the registry entry gives new requests the updated policy without interrupting active calls.

**Alternatives considered:**

- Keep first-init-wins per agent: simpler, but surprising after agent config edits and reloads.
- Mutate the existing semaphore and QPM values in place: difficult to make correct when the old capacity is smaller or larger than current in-flight usage.
- Require process restart for limiter changes: operationally heavy and inconsistent with agent reload behavior.

### Decision 4: Keep 429 cooldown local to the agent scope

**Choice:** `report_rate_limit()` updates only the limiter instance for the current `(effective_tenant_id, agent_id)` scope.

**Rationale:**

- A 429 from one agent should not pause unrelated agents in the same tenant or other tenants.
- This matches the requested isolation model and reduces failure amplification.

**Alternatives considered:**

- Keep a shared global cooldown: protects shared upstream credentials more aggressively, but preserves the current cross-agent coupling.
- Add both global and scoped cooldowns: more complete for provider-wide quotas, but it belongs in a provider-scoped quota design rather than this agent-scoped change.

### Decision 5: Keep streaming slot ownership unchanged

**Choice:** Preserve the existing streaming behavior where the limiter slot is released after the first stream chunk arrives.

**Rationale:**

- This change is about scope, not streaming lifecycle.
- Altering stream slot ownership would change throughput and starvation behavior independently from the scoping fix.

## Risks / Trade-offs

- [Per-agent isolation can increase total process-wide LLM concurrency] -> Set agent defaults conservatively and document that the configured limit is now per agent, not process-wide.
- [Shared provider credentials may still have provider-level quotas] -> Keep this change agent-scoped; consider a later provider-scoped or tenant-provider quota layer if upstream quota protection needs to be shared across agents.
- [Registry can grow with many short-lived agents] -> Track last-used time and provide a cleanup helper for idle entries with no in-flight calls.
- [Fallback to default agent can hide missing context] -> Keep fallback compatibility but add tests and logs around resolved scope keys so accidental default bucketing is visible.
- [Config replacement can leave old limiter objects alive briefly] -> Allow old instances to drain naturally; they become unreachable from the registry after replacement and are released once active calls finish.

## Migration Plan

1. Introduce scope key and scoped registry around the existing `LLMRateLimiter`.
2. Pass the resolved tenant-local agent scope from model creation into `RetryChatModel`.
3. Update `RetryChatModel` to acquire the scope-specific limiter for non-streaming calls and stream retries.
4. Add focused tests for same-scope sharing, cross-agent isolation, cross-tenant isolation, scoped 429 cooldown, and config replacement.
5. Update config descriptions and resource-control documentation to remove the "shared across all agents / first initialization wins" semantics.
6. Roll back by restoring the old global singleton lookup if scoped behavior causes unexpected operational pressure; no persistent data migration is required.

## Open Questions

- Should the idle limiter cleanup run opportunistically on registry access, or as an explicit maintenance helper called from tests and future service lifecycle hooks?
- Should logs include the resolved limiter scope on initialization only, or also on timeout/error paths for easier production diagnosis?
