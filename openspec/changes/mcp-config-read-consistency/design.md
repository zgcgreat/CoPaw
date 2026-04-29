## Context

当前 agent-scoped 控制接口同时依赖三类状态来源：

- tenant 根 `config.json` 中的 `agents.active_agent` 与 `agents.profiles`
- workspace 目录下的 `agent.json`
- `MultiAgentManager` / `Workspace` 进程内缓存

其中，`/api/mcp`、`/api/tools`、`/api/config`、`/api/agent/running-config`、部分 skills 路由都通过 `get_agent_for_request()` 先拿到一个 `Workspace`，随后直接读取 `workspace.config`。`Workspace.config` 是惰性加载并长期缓存的，而 query 执行路径又会在请求时重新 `load_agent_config()` 从磁盘读 `agent.json`。这导致同一 agent 在不同 API 路径和不同 pod 之间可能读到不同配置快照。

另一个问题是 reload 契约不完整。`schedule_agent_reload()` 和 `MultiAgentManager.reload_agent()` 都支持 tenant-aware scope，但多数调用点没有传入 `tenant_id`，导致多租户场景下 reload 可能命中错误 cache key，或者直接跳过正在服务请求的 tenant-scoped workspace。

当前症状在 MCP 页面上最明显，因为它既频繁触发 GET `/api/mcp`，又依赖写后马上可见的配置结果；但问题本质上是通用的 agent 控制配置一致性问题，而不只是 MCP 功能问题。

## Goals / Non-Goals

**Goals:**

- 为 agent-scoped 控制接口定义单一且稳定的 agent 解析规则
- 明确 `agent.json` 与 `Workspace.config` 的职责边界，避免磁盘配置与进程内缓存互相越权
- 要求所有 agent 配置写路径在 reload 时传入正确 tenant scope
- 保证同一 tenant 同一 agent 的控制接口具备稳定的读后写可见性
- 将 MCP 页面当前暴露出的配置“横跳”现象收敛为可验证的后端一致性规则

**Non-Goals:**

- 不在本 change 中设计完整的 console `selectedAgent` 与后端 `active_agent` 同步产品流程
- 不在本 change 中引入 Redis、数据库或新的跨 pod 配置存储
- 不在本 change 中重构所有运行时对象的生命周期管理
- 不改变 query 执行时“按请求重新读取 agent 配置”的总体模型

## Decisions

### Decision 1: 将 `workspace/agent.json` 设为 agent 控制配置的权威来源

控制接口在解析出目标 agent 后，凡是读取 agent 级配置的接口，都必须以 `load_agent_config(..., tenant_id=...)` 的结果作为权威视图，而不是直接依赖 `Workspace.config` 缓存对象。

Rationale:

- `agent.json` 已经是当前 agent 级配置的主存储位置
- query 执行路径本来就按该文件读取配置
- 继续让 GET 控制接口直接读 `Workspace.config` 会放大跨 pod 缓存漂移

Alternatives considered:

- 继续使用 `Workspace.config` 作为 GET 接口返回源，并扩展 watcher 主动刷新缓存
  - 放弃原因：依赖进程内 watcher 无法解决多 pod 读取不一致，且当前 watcher 只覆盖 channels / heartbeat
- 将所有读取都改成根 `config.json`
  - 放弃原因：与现有多 agent 设计相违背，且 `mcp` 等字段已迁移到 `agent.json`

### Decision 2: 将 `Workspace.config` 限定为运行时对象初始化缓存，而非控制接口真源

`Workspace.config` 仍可用于运行时组件装配和局部内存变更，但控制接口不能假设它总是最新磁盘状态。写接口在更新完成后可以继续同步更新当前 `workspace.config`，但接口的稳定读取必须可脱离该缓存独立成立。

Rationale:

- 可以减少对现有运行时对象的侵入性改造
- 将一致性边界收敛到“读接口读磁盘，运行时按需缓存”
- 避免必须先统一 watcher 才能得到正确控制面行为

Alternatives considered:

- 删除 `Workspace.config` 缓存，每次运行时都从磁盘重新加载
  - 放弃原因：会影响现有 runtime 组件依赖方式，改动面过大

### Decision 3: 统一 tenant-aware reload 契约

所有调用 `schedule_agent_reload()` 的 agent 配置写路径都必须传入显式 `tenant_id`。所有直接调用 `MultiAgentManager.reload_agent()` 的路径也必须传入 tenant scope；如调用上下文当前拿不到 tenant scope，则需要先补齐上下文对象，再允许 reload。

Rationale:

- `MultiAgentManager` 的 cache key 已经是 `tenant_id:agent_id`
- 不传 tenant scope 会导致 reload 命中错误实例或错误地认为实例未加载
- 这是当前多租户错位行为最直接的代码缺陷

Alternatives considered:

- 在 `schedule_agent_reload()` 内部从 request 自动推断 tenant_id
  - 保留为可选兜底，但不作为主契约；显式调用更清晰，也更容易测试

### Decision 4: 在无 `X-Agent-Id` 的控制接口上保持稳定回退规则，但不在本 change 中扩展前端同步协议

如果请求未显式指定 agent，则控制接口仍按当前 tenant 的 `active_agent` 解析目标 agent。该规则在本 change 中只要求“稳定且一致”，不要求前端立即新增 active-agent 同步 API。

Rationale:

- 与现有 `get_agent_for_request()` 解析顺序兼容
- 可以让本 change 聚焦在后端一致性，而不是和 `complete-console-agent-switching` 重叠

Alternatives considered:

- 强制所有控制接口必须显式带 `X-Agent-Id`
  - 放弃原因：与当前前端调用方式和现有兼容路径不符，变更过大

## Risks / Trade-offs

- [读取改为磁盘权威后，部分接口延迟略升高] -> Mitigation: 仅对控制面 GET/写后校验路径这样做，query 执行路径保持现状
- [当前实例内存中的 `workspace.config` 与磁盘仍可能短暂不一致] -> Mitigation: 写接口在持久化后继续更新当前内存对象，同时把 GET 接口改为磁盘权威视图
- [未覆盖到的 reload 调用点仍可能残留租户错位] -> Mitigation: 为所有 `schedule_agent_reload` / `reload_agent` 调用点增加测试与代码审计
- [与 `complete-console-agent-switching` 的边界不清可能造成重复改动] -> Mitigation: 本 change 只约束后端解析与一致性，不引入新的 active-agent UI 契约

## Migration Plan

1. 先补充一致性测试，覆盖 tenant-scoped reload、无 `X-Agent-Id` 读取、MCP 读后写稳定性
2. 收敛 `schedule_agent_reload()` 与直接 `reload_agent()` 的 tenant 传参
3. 将 MCP、tools、config、agent 运行配置等控制接口改为显式按 tenant 读取 `agent.json`
4. 保留 `Workspace.config` 给运行时装配使用，但不再作为控制接口的唯一读取来源
5. 验证单实例和多实例部署下连续 GET `/api/mcp` 的返回稳定性

Rollback:

- 若新读取路径引发不可接受的回归，可先回退到原有接口实现
- tenant-aware reload 传参补齐属于低风险修正，原则上不单独回滚

## Open Questions

- 是否要在 `schedule_agent_reload()` 中增加从 `request.state` 自动兜底推断 tenant 的逻辑，还是只依赖显式调用传参
- 哪些控制接口可以继续接受基于 `active_agent` 的隐式解析，哪些接口需要在后续 change 中升级为显式 agent contract
- 是否需要补一个轻量级 agent config snapshot helper，统一控制接口的读取方式，避免每个路由单独重复调用 `load_agent_config`
