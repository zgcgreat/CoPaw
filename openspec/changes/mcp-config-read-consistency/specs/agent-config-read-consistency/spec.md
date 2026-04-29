## ADDED Requirements

### Requirement: Agent-scoped control APIs SHALL resolve a stable target agent
The system SHALL resolve the target agent for agent-scoped control APIs using one stable priority order: explicit route-scoped agent identifier first, explicit request-scoped agent identifier second, and tenant `active_agent` fallback last. Repeated requests under the same tenant context and the same explicit inputs MUST resolve to the same target agent.

#### Scenario: Route-scoped agent takes precedence
- **WHEN** a request targets `/api/agents/{agentId}/...`
- **THEN** the control API SHALL use `{agentId}` as the target agent even if tenant `active_agent` differs

#### Scenario: Active agent fallback is stable without explicit agent id
- **WHEN** a request targets an agent-scoped control API without route agent id and without `X-Agent-Id`
- **THEN** the control API SHALL resolve the target agent from the current tenant's `active_agent`
- **AND** repeated requests in the same tenant context SHALL keep resolving to that same `active_agent` until tenant config changes

### Requirement: Agent configuration reads SHALL use tenant-scoped agent.json as the authoritative source
For agent-scoped control APIs that read agent-level configuration, the system SHALL treat tenant-scoped `workspace/agent.json` as the authoritative source of the returned configuration view. In-memory workspace caches MAY exist for runtime services, but control API responses MUST NOT be sourced solely from a stale process-local cache when the authoritative `agent.json` differs.

#### Scenario: MCP list reads authoritative agent configuration
- **WHEN** a client requests `GET /api/mcp` for a resolved tenant and agent
- **THEN** the response SHALL reflect the MCP client definitions stored in that tenant and agent's `workspace/agent.json`
- **AND** the response SHALL NOT return an older process-local MCP snapshot if the authoritative file has already changed

#### Scenario: Tool or running-config reads authoritative agent configuration
- **WHEN** a client requests another agent-scoped control read that exposes agent-level config such as tools or running config
- **THEN** the response SHALL reflect the resolved tenant and agent's authoritative `workspace/agent.json`

### Requirement: Agent configuration mutations SHALL perform tenant-aware reload
Any API path that persists agent-level configuration and schedules or performs agent reload SHALL use the tenant-scoped runtime identity of the mutated agent. The system MUST pass the correct `tenant_id` when reloading or scheduling reload for a tenant-scoped agent runtime.

#### Scenario: Scheduled reload uses tenant-scoped runtime identity
- **WHEN** a config mutation endpoint persists changes for an agent in tenant `tenant-a`
- **THEN** the endpoint SHALL schedule reload using the runtime identity `(tenant-a, agent-id)`
- **AND** the reload SHALL NOT target the global or tenant-less cache entry for the same `agent-id`

#### Scenario: Direct reload uses tenant-scoped runtime identity
- **WHEN** the system directly invokes `MultiAgentManager.reload_agent` after mutating tenant-scoped agent config
- **THEN** it SHALL pass the effective tenant id of the mutated agent

### Requirement: Control APIs SHALL provide stable read-after-write visibility for the mutated tenant and agent
After an agent-scoped control API successfully persists agent configuration for a resolved tenant and agent, subsequent reads for that same tenant and agent SHALL converge on the newly persisted configuration rather than alternating between old and new snapshots across repeated requests.

#### Scenario: MCP configuration does not oscillate after mutation
- **WHEN** a client successfully creates, updates, toggles, or deletes an MCP client for a resolved tenant and agent
- **THEN** subsequent `GET /api/mcp` calls for that same tenant and agent SHALL converge on the new MCP configuration
- **AND** the API SHALL NOT alternate between pre-change and post-change results solely because requests are served by different runtime instances

#### Scenario: Same-tenant reads remain isolated from other tenants
- **WHEN** one tenant mutates an agent configuration and another tenant performs reads for an agent with the same agent id
- **THEN** each tenant's control API responses SHALL remain isolated to that tenant's authoritative configuration
