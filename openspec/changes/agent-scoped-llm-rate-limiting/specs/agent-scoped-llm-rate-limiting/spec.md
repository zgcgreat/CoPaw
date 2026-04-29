## ADDED Requirements

### Requirement: LLM limiter state SHALL be isolated by tenant-local agent
The system SHALL maintain LLM concurrency, QPM, and rate-limit cooldown state separately for each `(effective_tenant_id, agent_id)` scope within a backend process.

#### Scenario: Same tenant and same agent share limiter state
- **GIVEN** two LLM calls resolve to tenant `tenant-a` and agent `agent-x`
- **WHEN** both calls acquire LLM execution slots
- **THEN** both calls SHALL use the same scoped limiter state

#### Scenario: Same tenant and different agents do not share limiter state
- **GIVEN** one LLM call resolves to tenant `tenant-a` and agent `agent-x`
- **AND** another LLM call resolves to tenant `tenant-a` and agent `agent-y`
- **WHEN** both calls acquire LLM execution slots
- **THEN** the calls SHALL use different scoped limiter state

#### Scenario: Different tenants and same agent id do not share limiter state
- **GIVEN** one LLM call resolves to tenant `tenant-a` and agent `default`
- **AND** another LLM call resolves to tenant `tenant-b` and agent `default`
- **WHEN** both calls acquire LLM execution slots
- **THEN** the calls SHALL use different scoped limiter state

### Requirement: Agent running configuration SHALL apply to that agent's limiter
The system SHALL apply an agent's configured LLM limiter values to the limiter instance for that agent scope.

#### Scenario: Agent-specific concurrency limit is enforced in its own scope
- **GIVEN** tenant `tenant-a` agent `agent-x` has `llm_max_concurrent=1`
- **AND** tenant `tenant-a` agent `agent-y` has `llm_max_concurrent=3`
- **WHEN** both agents perform LLM calls in the same backend process
- **THEN** agent `agent-x` SHALL be limited by a one-slot limiter
- **AND** agent `agent-y` SHALL be limited by a three-slot limiter

#### Scenario: Agent limiter configuration changes apply to later requests
- **GIVEN** tenant `tenant-a` agent `agent-x` has an existing scoped limiter
- **WHEN** agent `agent-x` limiter configuration changes and a later LLM call starts
- **THEN** the later call SHALL use limiter state initialized from the updated configuration
- **AND** already in-flight calls SHALL NOT be interrupted by the configuration change

### Requirement: Rate-limit cooldown SHALL remain inside the agent scope
The system SHALL apply a rate-limit cooldown triggered by a 429 response only to the scoped limiter for the agent that received the response.

#### Scenario: Agent 429 cooldown does not pause another agent
- **GIVEN** tenant `tenant-a` agent `agent-x` receives an upstream 429 response
- **AND** tenant `tenant-a` agent `agent-y` has not received a 429 response
- **WHEN** both agents attempt later LLM calls
- **THEN** agent `agent-x` SHALL observe its scoped cooldown
- **AND** agent `agent-y` SHALL NOT wait on agent `agent-x`'s cooldown

#### Scenario: Agent 429 cooldown does not pause another tenant's same-name agent
- **GIVEN** tenant `tenant-a` agent `default` receives an upstream 429 response
- **AND** tenant `tenant-b` agent `default` has not received a 429 response
- **WHEN** both agents attempt later LLM calls
- **THEN** tenant `tenant-a` agent `default` SHALL observe its scoped cooldown
- **AND** tenant `tenant-b` agent `default` SHALL NOT wait on tenant `tenant-a`'s cooldown

### Requirement: Unscoped model calls SHALL use a stable default agent scope
The system SHALL continue to support model calls that do not receive an explicit agent id by resolving them through the existing current-agent or active-agent fallback.

#### Scenario: Missing explicit agent uses fallback scope
- **GIVEN** an LLM call starts without an explicit agent id
- **WHEN** the runtime has a current agent context or active agent configuration
- **THEN** the call SHALL resolve a stable agent id through the existing fallback behavior
- **AND** the call SHALL use the limiter scope for that resolved agent id

### Requirement: Scoped limiting SHALL preserve existing per-call retry semantics
The system SHALL preserve existing retry, timeout, streaming slot-release, and QPM behavior inside each scoped limiter.

#### Scenario: Streaming call releases scoped slot after first chunk
- **GIVEN** an agent-scoped streaming LLM call has acquired a limiter slot
- **WHEN** the first stream chunk is received
- **THEN** the system SHALL release the limiter slot for that same agent scope using the existing streaming behavior

#### Scenario: QPM window is counted inside the scoped limiter
- **GIVEN** an agent has a configured `llm_max_qpm` greater than zero
- **WHEN** that agent performs LLM calls
- **THEN** the QPM sliding window SHALL count requests only for that agent scope
