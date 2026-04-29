## 1. Limiter Scope and Registry

- [x] 1.1 Add a tenant-local agent scope key for LLM limiting using effective tenant id and resolved agent id.
- [x] 1.2 Replace the module-level global limiter singleton with a process-local registry keyed by the scope key.
- [x] 1.3 Store normalized limiter configuration fingerprints in registry entries and replace entries when later requests use changed config.
- [x] 1.4 Track last-used state and expose a safe cleanup path for idle limiter entries with no in-flight calls.

## 2. Model Call Integration

- [x] 2.1 Pass the resolved tenant id and agent id from model creation into `RetryChatModel`.
- [x] 2.2 Update non-streaming model calls to acquire and release the scoped limiter.
- [x] 2.3 Update streaming calls and stream retries to use the same scoped limiter while preserving first-chunk slot release.
- [x] 2.4 Keep missing-agent fallback behavior aligned with the current active/default agent resolution.

## 3. Configuration and Documentation

- [x] 3.1 Update `llm_max_concurrent`, `llm_max_qpm`, pause, jitter, and acquire-timeout descriptions to state that they are agent-scoped.
- [x] 3.2 Update resource-control documentation that currently describes LLM limiting as global or shared across all agents.
- [x] 3.3 Add logging or diagnostics that include limiter scope when scoped limiter entries are initialized, replaced, or time out.

## 4. Tests

- [x] 4.1 Add unit tests proving same tenant plus same agent shares limiter state.
- [x] 4.2 Add unit tests proving same tenant plus different agents do not share limiter state.
- [x] 4.3 Add unit tests proving different tenants with the same agent id do not share limiter state.
- [x] 4.4 Add unit tests proving a 429 cooldown in one agent scope does not pause another agent scope.
- [x] 4.5 Add unit tests proving limiter config changes affect later requests without interrupting in-flight calls.
- [x] 4.6 Add integration-level coverage for `create_model_and_formatter` or `RetryChatModel` to verify scope and config propagation.

## 5. Verification

- [x] 5.1 Run focused provider and model factory tests with `venv/bin/python -m pytest`.
- [x] 5.2 Run the broader relevant agent/provider test subset.
- [x] 5.3 Run OpenSpec validation for `agent-scoped-llm-rate-limiting`.
