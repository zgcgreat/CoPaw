## 1. Workload Context

- [x] 1.1 Add a typed LLM workload context helper with `chat` as the default and a context-manager API for temporary binding.
- [x] 1.2 Add unit tests proving workload context defaults to `chat`, binds to `cron`, and resets after the context exits.

## 2. Rate Limiter Model

- [x] 2.1 Refactor provider limiter structures so tenant-agent QPM/cooldown state remains shared while concurrency state is selected by workload.
- [x] 2.2 Update `RetryChatModel` to resolve workload at call time and acquire the workload-specific concurrency pool.
- [x] 2.3 Include workload identity in limiter initialization, replacement, cleanup, and acquire-timeout diagnostics.
- [x] 2.4 Add provider tests for chat/cron concurrency isolation within one tenant-agent scope.
- [x] 2.5 Add provider tests proving QPM windows and 429 cooldown remain shared across chat and cron workloads in the same tenant-agent scope.

## 3. Configuration

- [x] 3.1 Add optional chat-specific and cron-specific LLM concurrency configuration fields to agent running config.
- [x] 3.2 Add optional chat-specific and cron-specific LLM acquire-timeout configuration fields to agent running config.
- [x] 3.3 Update model factory runtime-config loading so missing workload-specific values fall back to `llm_max_concurrent` and `llm_acquire_timeout`.
- [x] 3.4 Add config/model-factory tests for workload-specific overrides and default fallback behavior.

## 4. Workload Binding Call Sites

- [x] 4.1 Bind `chat` workload for user-facing HTTP, console, and channel execution paths where an explicit binding is useful for clarity.
- [x] 4.2 Bind `cron` workload around scheduled cron job execution.
- [x] 4.3 Bind `cron` workload around manual cron `run_job` execution.
- [x] 4.4 Bind `cron` workload around heartbeat execution.
- [x] 4.5 Add tests proving scheduled cron, manual `run_job`, and heartbeat model calls resolve workload `cron`.

## 5. Documentation And Verification

- [x] 5.1 Update configuration descriptions and implementation-facing comments to explain chat/cron concurrency separation and shared QPM/cooldown behavior.
- [x] 5.2 Run focused provider, agent model factory, and cron workload-binding tests.
- [x] 5.3 Run the relevant provider unit test directory before marking the change complete.
