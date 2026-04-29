## ADDED Requirements

### Requirement: LLM concurrency SHALL be separated by workload inside a tenant-local agent
The system SHALL maintain separate LLM concurrency pools for chat and scheduler workloads within each `(effective_tenant_id, agent_id)` scope.

#### Scenario: Chat and cron use different concurrency pools
- **GIVEN** tenant `tenant-a` agent `agent-x` has chat LLM concurrency of 1 and cron LLM concurrency of 1
- **AND** one chat LLM call is already holding the chat concurrency slot
- **WHEN** a cron-originated LLM call starts for the same tenant and agent
- **THEN** the cron-originated call SHALL attempt to acquire the cron concurrency pool
- **AND** it SHALL NOT wait for the chat concurrency slot to be released

#### Scenario: Same workload shares its own pool
- **GIVEN** tenant `tenant-a` agent `agent-x` has chat LLM concurrency of 1
- **AND** one chat LLM call is already holding the chat concurrency slot
- **WHEN** another chat LLM call starts for the same tenant and agent
- **THEN** the later chat call SHALL wait for the chat concurrency pool

### Requirement: Scheduler-originated model calls SHALL use the cron workload
The system SHALL classify scheduled cron execution, manual cron `run_job`, and heartbeat execution as the `cron` workload for LLM concurrency purposes.

#### Scenario: Scheduled cron execution uses cron workload
- **WHEN** a scheduler-originated cron job performs an LLM call
- **THEN** the LLM call SHALL acquire from the cron workload concurrency pool

#### Scenario: Manual run_job uses cron workload
- **WHEN** an operator manually triggers `run_job` and that job performs an LLM call
- **THEN** the LLM call SHALL acquire from the cron workload concurrency pool

#### Scenario: Heartbeat execution uses cron workload
- **WHEN** heartbeat execution performs an LLM call
- **THEN** the LLM call SHALL acquire from the cron workload concurrency pool

### Requirement: Chat-originated model calls SHALL use the chat workload by default
The system SHALL classify normal user-facing HTTP, console, and channel request execution as the `chat` workload for LLM concurrency purposes. Model calls without explicit workload context SHALL default to `chat`.

#### Scenario: Channel chat uses chat workload
- **WHEN** a channel-originated user message performs an LLM call
- **THEN** the LLM call SHALL acquire from the chat workload concurrency pool

#### Scenario: Direct unbound model call defaults to chat workload
- **GIVEN** an LLM call starts without an explicit workload context
- **WHEN** the call resolves its limiter workload
- **THEN** the call SHALL use the chat workload concurrency pool

### Requirement: Workload concurrency configuration SHALL preserve existing defaults
The system SHALL allow chat and cron workload LLM concurrency and acquire-timeout values to be configured separately. If a workload-specific value is not configured, the system SHALL use the existing tenant-agent `llm_max_concurrent` or `llm_acquire_timeout` value for that workload.

#### Scenario: Workload-specific concurrency overrides default
- **GIVEN** tenant `tenant-a` agent `agent-x` has `llm_max_concurrent=5`
- **AND** the same agent has `llm_cron_max_concurrent=2`
- **WHEN** cron-originated LLM calls start for that tenant and agent
- **THEN** the cron workload concurrency pool SHALL allow at most 2 in-flight LLM calls

#### Scenario: Missing workload-specific concurrency falls back to existing value
- **GIVEN** tenant `tenant-a` agent `agent-x` has `llm_max_concurrent=5`
- **AND** the same agent has no chat-specific LLM concurrency value configured
- **WHEN** chat-originated LLM calls start for that tenant and agent
- **THEN** the chat workload concurrency pool SHALL allow at most 5 in-flight LLM calls

#### Scenario: Workload-specific acquire timeout is applied
- **GIVEN** tenant `tenant-a` agent `agent-x` has `llm_cron_acquire_timeout=120`
- **WHEN** a cron-originated LLM call waits for a cron concurrency slot
- **THEN** the call SHALL use 120 seconds as its acquire timeout

### Requirement: QPM and rate-limit cooldown SHALL remain shared by tenant-local agent
The system SHALL keep QPM sliding-window state and 429 cooldown state shared at `(effective_tenant_id, agent_id)` scope unless a future provider-quota design explicitly changes that behavior.

#### Scenario: Cron 429 cooldown applies to later chat call in same tenant-agent
- **GIVEN** tenant `tenant-a` agent `agent-x` receives a 429 response during a cron-originated LLM call
- **WHEN** a later chat-originated LLM call starts for the same tenant and agent before the cooldown expires
- **THEN** the chat-originated call SHALL observe the shared tenant-agent cooldown

#### Scenario: Chat QPM usage counts against cron in same tenant-agent
- **GIVEN** tenant `tenant-a` agent `agent-x` has a positive `llm_max_qpm`
- **AND** chat-originated LLM calls have filled the tenant-agent QPM window
- **WHEN** a cron-originated LLM call starts for the same tenant and agent
- **THEN** the cron-originated call SHALL wait for the shared tenant-agent QPM window

#### Scenario: Shared cooldown remains isolated across agents
- **GIVEN** tenant `tenant-a` agent `agent-x` receives a 429 response
- **WHEN** tenant `tenant-a` agent `agent-y` starts an LLM call
- **THEN** agent `agent-y` SHALL NOT wait on agent `agent-x`'s cooldown

### Requirement: Limiter diagnostics SHALL include workload identity
The system SHALL include the resolved workload identity in LLM limiter initialization, replacement, cleanup, and acquire-timeout diagnostics.

#### Scenario: Acquire timeout identifies workload
- **GIVEN** a cron-originated LLM call times out waiting for a concurrency slot
- **WHEN** the timeout error is reported
- **THEN** the diagnostic SHALL identify the tenant id, agent id, and workload `cron`
