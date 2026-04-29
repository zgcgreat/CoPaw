## Why

当前 MCP 页面会出现重复调用 `/api/mcp` 后返回结果反复变化的问题。根因不在单一接口本身，而在于 agent 配置读取、tenant-aware reload、以及进程内 workspace 配置缓存之间缺少统一的一致性约束，导致不同请求可能读到不同的 agent 配置快照。

## What Changes

- 为 agent-scoped 控制接口定义统一的配置读取规则，明确哪些接口必须以磁盘中的 `workspace/agent.json` 为权威来源，哪些缓存只允许作为执行期对象缓存而不是配置真源
- 为不显式传入 `X-Agent-Id` 的控制接口定义稳定的 agent 解析规则，避免 UI 当前选择、tenant `active_agent`、路径注入和运行时缓存之间出现语义分裂
- 收敛 tenant-aware reload 的调用契约，要求所有 agent 配置变更路径在 reload 时传入正确的 tenant scope
- 约束 MCP 配置读接口与 MCP 配置写接口在多实例和多租户场景下的可见性行为，避免同一租户同一 agent 的连续读取出现旧新配置来回切换
- 为 MCP 页面症状补充后端一致性测试和必要的前端契约说明，但不在本 change 中扩展完整的 console agent switching 产品流程

## Capabilities

### New Capabilities
- `agent-config-read-consistency`: 定义 agent 控制接口在 agent 解析、配置读取、缓存使用和 reload 可见性上的一致性要求

### Modified Capabilities
- None.

## Impact

- Affected backend modules: `src/swe/app/agent_context.py`, `src/swe/app/multi_agent_manager.py`, `src/swe/app/utils.py`, `src/swe/app/routers/mcp.py`, `src/swe/app/routers/config.py`, `src/swe/app/routers/tools.py`, `src/swe/app/routers/skills.py`, `src/swe/app/routers/agent.py`, `src/swe/app/routers/agents.py`, `src/swe/app/runner/daemon_commands.py`
- Affected runtime behavior: MCP client list reads, agent-scoped control API reads after config mutation, tenant-scoped zero-downtime reload behavior
- Affected frontend contract: `console/src/pages/Agent/MCP/useMCP.ts` and related control pages must not assume repeated GETs can safely tolerate backend agent/config source drift
- Relationship to existing changes: complements `complete-console-agent-switching` by fixing backend config consistency guarantees, but does not introduce or redesign the console active-agent UX contract itself
