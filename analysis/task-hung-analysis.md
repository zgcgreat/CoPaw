# CoPaw 任务卡死风险分析报告

> 分析目标：识别项目中 MCP 工具调用、大模型调用、定时任务等执行场景下，任务可能卡死且用户无法感知的问题

---

## 一、总体发现

### 核心模式：连接有超时，运行时无超时

项目中存在一个系统性模式：**在连接/初始化阶段普遍设置了超时（30s~300s），但在运行时执行阶段几乎没有任何超时保护**。这意味着：

| 阶段 | 超时机制 | 典型超时值 | 修复状态 |
|------|---------|-----------|---------|
| MCP 连接建立 | ✅ `asyncio.wait_for` | 30s | 原有 |
| MCP 工具调用 | ✅ `asyncio.wait_for` | 120s | ✅ 已修复 |
| LLM HTTP 连接 | ✅ SDK 默认 | ~10s | 原有 |
| LLM 响应生成 | ✅ `asyncio.wait_for` + 停滞检测 | 600s / 120s | ✅ 已修复 |
| Cron 任务执行 | ✅ `asyncio.wait_for` | 7200s | 原有 |
| Query 全局执行 | ✅ `_enforce_query_timeout` | 1800s | ✅ 已修复 |
| Agent 单轮迭代 | ✅ Watchdog 检测 | 300s | ✅ 已修复 |
| Channel 消息处理 | ✅ `asyncio.wait_for` | 1900s | ✅ 已修复 |

---

## 二、高风险卡死点（严重程度：🔴 高）

### 1. MCP `call_tool()` — 无超时保护

**文件**: `src/swe/app/mcp/stateful_client.py`
**位置**: 第 301 行

```python
result = await self.session.call_tool(name, arguments or {})
```

**问题**: MCP 工具调用是外部进程/服务调用，`call_tool()` 完全没有 `asyncio.wait_for` 包裹。如果外部 MCP Server 卡死（进程挂起、网络中断、死锁），当前协程将永远等待。

**影响范围**: 所有使用 MCP 工具的 Agent 执行链路都会被阻塞。

**对比**: 同文件的连接建立有 30s 超时（第 199 行），但运行时调用反而没有。

---

### 2. MCP `list_tools()` — 无超时保护

**文件**: `src/swe/app/mcp/stateful_client.py`
**位置**: 第 280 行

```python
tools_result = await self.session.list_tools()
```

**问题**: 与 `call_tool()` 相同，`list_tools()` 也无超时。虽然调用频率低于 `call_tool()`，但每次 Agent 启动时都会触发，如果 MCP Server 响应慢，会阻塞整个初始化流程。

---

### 3. Query Handler — 全局无超时

**文件**: `src/swe/app/runner/runner.py`
**位置**: 第 477-804 行 (`query_handler`)

```python
async def query_handler(self, ...):
    # 数百行代码，无任何全局 asyncio.wait_for 包裹
    async for msg in self.stream_printing_messages(...):
        ...
```

**问题**: `query_handler` 是所有用户请求的核心入口，整个函数没有任何全局超时。一个请求理论上可以无限执行——Agent 不断迭代、MCP 工具不断挂起、LLM 不断重试——直到用户手动取消。

**关键循环**: `stream_printing_messages`（第 709-713 行）是核心执行循环，无 watchdog 检测。

---

### 4. LLM Provider 调用 — 最坏情况 ~35 分钟

**文件**: `src/swe/providers/retry_chat_model.py`
**位置**: 第 305 行

```python
response = await self._inner(*args, **kwargs)
```

**问题**: `RetryChatModel` 包装了 LLM 调用，具备重试和退避机制，但 **没有应用层超时上限**。最坏情况计算：

| 阶段 | 超时 |
|------|------|
| 信号量等待 | 300s (`LLM_ACQUIRE_TIMEOUT`) |
| 第 1 次 LLM 调用 | ~600s (SDK 默认) |
| 退避等待 | ~2s |
| 第 2 次 LLM 调用 | ~600s |
| 退避等待 | ~4s |
| 第 3 次 LLM 调用 | ~600s |
| **合计** | **~2130s (约 35 分钟)** |

更严重的是：**流式响应如果停止产出 token 但不关闭连接，不会触发重试**（重试仅在 `RETRYABLE_STATUS_CODES` 时触发，第 350-465 行）。

---

## 三、中风险卡死点（严重程度：🟡 中）

### 5. Agent ReAct 循环 — 单轮无时间限制

**文件**: `src/swe/agents/react_agent.py`
**位置**: `max_iters`（第 169 行）限制迭代次数

**问题**: `max_iters` 限制了迭代次数（默认值），但 **单次迭代没有时间限制**。一次迭代中可能包含：
- LLM 推理（可卡 ~35 分钟，见上）
- 工具调用（MCP 可卡 ∞）
- 内存搜索（1s 超时，第 1092-1098 行 — 这是少数正确设置了超时的操作）

另外，`_ROUND_END_NOTICE`（第 915-920 行）仅在达到迭代上限时通知用户，**不通知当前迭代已执行了多久**。

---

### 6. Cron 任务超时 — 用户无感知

**文件**: `src/swe/app/crons/executor.py`
**位置**: 第 240-243 行

```python
result = await asyncio.wait_for(
    self._run_cron_query(cron, context), timeout=timeout
)
```

**问题**: Cron 有超时保护（默认 7200s = 2 小时），但超时处理（第 162-168 行）只是 `log.warning` 并重新抛出异常。用户不会收到"定时任务超时"的明确通知。

更关键的是：**2 小时内没有任何中间进度反馈**。如果 Agent 在第 1 分钟就卡住了，用户要等 2 小时才会知道。

相关文件：
- `src/swe/app/crons/heartbeat.py`（第 214、228 行）— heartbeat 超时也只 log warning
- `src/swe/app/crons/manager.py`（`_task_done_cb`，第 1061-1093 行）— 失败时推送错误到 console，但超时不一定触发此回调

---

### 7. Channel 消息消费 — 无超时

**文件**: `src/swe/app/channels/manager.py`
**位置**: 第 396-445 行（消费循环）

**问题**: Channel 消费循环处理单条消息时无超时。如果消息处理涉及 Agent 执行（必然会），整个消费循环都会被阻塞。

**对比**: 入队操作有 30s 超时（第 327 行），但出队处理没有。

---

## 四、低风险/辅助问题（严重程度：🟢 低）

### 8. 任务清理操作 — 无超时

**文件**: `src/swe/app/runner/runner.py`
**位置**: 第 812-850 行（finally 块）

**问题**: `query_handler` 的 finally 块执行清理（保存会话、落盘等），这些操作本身也没有超时保护。如果清理阶段卡住（如数据库不可达），整个请求将永远无法完成。

---

### 9. Agent `interrupt()` — 无超时

**文件**: `src/swe/agents/react_agent.py`
**位置**: 第 1123-1137 行

**问题**: `interrupt()` 方法等待任务完成，但没有设置 `asyncio.wait_for`。如果 Agent 无法正常停止（如 MCP 工具调用卡住），`interrupt()` 也会卡住。

---

## 五、缺失能力汇总

当前项目 **完全缺失** 以下机制：

| 能力 | 说明 | 影响 | 修复状态 |
|------|------|------|---------|
| **Watchdog/卡死检测** | 无独立定时器检测"Agent 已 N 秒无输出" | 卡死后无人知道 | ✅ 已修复 |
| **执行进度反馈** | LLM 思考中、工具执行中无心跳 | 用户以为系统崩溃 | ⬜ 未实现 |
| **全局 Query 超时** | 无"单次请求最大执行时间" | 请求可无限执行 | ✅ 已修复 |
| **MCP 运行时超时** | 连接有超时，调用无超时 | 工具调用可永久挂起 | ✅ 已修复 |
| **超时用户通知** | Cron/LLM 超时只 log 不通知 | 用户不知道任务已失败 | ✅ 已修复 |
| **清理操作超时** | finally 块无超时 | 清理可二次卡死 | ✅ 已修复 |

---

## 六、改进建议

按优先级排列：

### P0 — 必须修复

| # | 改进项 | 具体做法 | 影响文件 |
|---|--------|---------|---------|
| 1 | **MCP 工具调用超时** | `call_tool()` / `list_tools()` 包裹 `asyncio.wait_for`，默认 120s | `stateful_client.py` |
| 2 | **Query 全局超时** | `query_handler` 外层加 `asyncio.wait_for`，默认 1800s（30 分钟），超时主动通知用户 | `runner.py` |
| 3 | **LLM 调用超时上限** | `RetryChatModel.__call__` 加 `asyncio.wait_for`，默认 600s，且检测流式 token 间隔 | `retry_chat_model.py` |

### P1 — 应该修复

| # | 改进项 | 具体做法 | 影响文件 |
|---|--------|---------|---------|
| 4 | **Agent Watchdog** | 在 `ReActAgent` 中加独立定时器，检测"N 秒内无任何 event 产出"，主动中断并通知 | `react_agent.py` |
| 5 | **Cron 超时用户通知** | 超时时推送明确消息到 console，而非仅 log | `executor.py`, `manager.py` |
| 6 | **Channel 消费超时** | 单条消息处理加 `asyncio.wait_for`，默认与 Query 全局超时一致 | `channels/manager.py` |

### P2 — 建议修复

| # | 改进项 | 具体做法 | 影响文件 |
|---|--------|---------|---------|
| 7 | **LLM 心跳检测** | 流式响应中检测 token 间隔，超过 N 秒无新 token 则发送"仍在思考"心跳 | `retry_chat_model.py`, `runner.py` |
| 8 | **清理操作超时** | finally 块中的关键操作加 `asyncio.wait_for`，默认 30s | `runner.py` |
| 9 | **`interrupt()` 超时** | 加 `asyncio.wait_for`，默认 60s | `react_agent.py` |

---

## 七、关键代码路径示意

```
用户请求
  └→ Channel._stream_with_tracker()    [1900s 超时] ← 🟢 已修复 #7
       └→ Runner.query_handler()        [1800s 全局超时 + agent.interrupt()] ← 🟢 已修复 #3
            ├→ ReActAgent.run()
            │    ├→ Watchdog 检测         [300s 无输出中断]  ← 🟢 已修复 #5
            │    └→ 循环: LLM 调用       [600s 超时 + 120s 停滞检测] ← 🟢 已修复 #4
            │         + 工具调用
            │              └→ MCP.call_tool()  [120s 超时] ← 🟢 已修复 #1
            │              └→ MCP.list_tools() [120s 超时] ← 🟢 已修复 #2
            │
            └→ finally: 清理操作         [30s 超时]     ← 🟢 已修复 #8

定时任务
  └→ CronExecutor.execute()             [7200s 超时]
       └→ Runner.query_handler()        [1800s 全局超时]
            └→ (同上链路)
       超时时 → Console 推送通知        [用户可感知]   ← 🟢 已修复 #6
```

---

## 八、修复总结（2026-04-24 完成）

### 8.1 新增超时常量

在 `src/swe/constant.py` 新增以下环境变量可配置的超时常量：

| 常量名 | 默认值 | 说明 | 环境变量 |
|--------|--------|------|----------|
| `MCP_CALL_TIMEOUT` | 120s | MCP 工具调用/列表超时 | `SWE_MCP_CALL_TIMEOUT` |
| `QUERY_TIMEOUT_SECONDS` | 1800s | Query 全局执行超时 | `SWE_QUERY_TIMEOUT_SECONDS` |
| `LLM_CALL_TIMEOUT` | 600s | 单次 LLM 调用超时 | `SWE_LLM_CALL_TIMEOUT` |
| `LLM_STREAM_STALL_TIMEOUT` | 120s | 流式响应停滞检测 | `SWE_LLM_STREAM_STALL_TIMEOUT` |
| `AGENT_WATCHDOG_TIMEOUT` | 300s | Agent 无输出检测 | `SWE_AGENT_WATCHDOG_TIMEOUT` |
| `QUERY_CLEANUP_TIMEOUT` | 30s | 清理操作超时 | `SWE_QUERY_CLEANUP_TIMEOUT` |
| `AGENT_INTERRUPT_TIMEOUT` | 60s | Agent 中断等待超时 | `SWE_AGENT_INTERRUPT_TIMEOUT` |
| `CHANNEL_CONSUME_TIMEOUT` | 1900s | Channel 消息消费超时 | `SWE_CHANNEL_CONSUME_TIMEOUT` |

### 8.2 各文件修复详情

#### 1. `src/swe/app/mcp/stateful_client.py`
- 新增 `_call_with_timeout()` 辅助方法，使用 `asyncio.wait_for` 包裹 MCP 调用
- `StdIOStatefulClient` 和 `HttpStatefulClient` 的 `list_tools()` / `call_tool()` 方法均添加 `timeout` 参数（默认 `MCP_CALL_TIMEOUT`）

#### 2. `src/swe/app/runner/runner.py`
- 新增 `_enforce_query_timeout()` 异步生成器方法，对 `stream_printing_messages()` 进行全局超时控制
- `_enforce_query_timeout()` 新增 `agent` 参数，超时时主动调用 `agent.interrupt()` 中断 Agent 执行，防止超时后 Agent 仍在后台运行消耗资源
- `agent.interrupt()` 调用包裹 `try/except`，避免中断本身失败导致超时通知也无法发出
- 修改 `_safe_cleanup()`，对会话保存、Chat 更新、MCP 清理三个操作分别添加 `asyncio.wait_for` 超时保护
- 清理遗留的 `print("passthrough_headers", passthrough_headers)` 调试语句

#### 3. `src/swe/providers/retry_chat_model.py`
- 非流式调用添加 `asyncio.wait_for(timeout=self._call_timeout)`
- 流式调用添加 `asyncio.wait_for` 包裹
- 新增流式响应停滞检测：`_consume_stream_with_slot()` 中跟踪 `last_chunk_time`，超过 `LLM_STREAM_STALL_TIMEOUT` 则抛出 `TimeoutError`
- `_is_retryable()` 新增 `TimeoutError` 作为可重试异常

#### 4. `src/swe/agents/react_agent.py`
- 新增 Watchdog 机制：`_start_watchdog()` / `_reset_watchdog()` / `_stop_watchdog()` 三个方法
- `reply()` 方法添加 `try/finally` 包裹，启动和停止 Watchdog
- `print()` 方法每次调用时重置 Watchdog
- `interrupt()` 方法添加 `asyncio.wait_for` 超时保护，并先停止 Watchdog

#### 5. `src/swe/app/crons/executor.py`
- 新增 `_notify_timeout()` 方法，超时后通过 `push_store_append()` 向 Console 推送双语超时通知
- `asyncio.TimeoutError` 捕获块中调用 `_notify_timeout()` 后再重新抛出

#### 6. `src/swe/app/channels/manager.py`
- `_consume_queue()` 中 `_process_batch()` 调用添加 `asyncio.wait_for(timeout=CHANNEL_CONSUME_TIMEOUT)`
- 超时后记录 error 日志，包含 channel、session、batch_size 信息

### 8.3 验证建议

| 验证场景 | 方法 |
|----------|------|
| Cron 超时通知 | 临时修改 `timeout=5`，创建耗时 Agent 任务，观察 Console 是否收到超时消息 |
| Channel 消费超时 | 临时修改 `CHANNEL_CONSUME_TIMEOUT=10`，发送卡住请求，观察日志 |
| LLM 流式停滞 | 使用模拟慢响应的 LLM Provider，验证是否触发停滞检测 |

### 8.4 注意事项

1. **环境变量覆盖**：所有超时常量均支持通过环境变量覆盖，无需修改代码即可调整
2. **向后兼容**：新增代码均为新增方法或新增参数，对原有调用逻辑无侵入性变更
3. **错误处理**：所有超时操作均有详细的日志记录，便于排查问题
4. **Query 超时后 Agent 中断**：`_enforce_query_timeout()` 在超时时会主动调用 `agent.interrupt()`，确保 Agent 不会在后台继续运行消耗 LLM token 和 MCP 资源
5. **未实现的 P2 项**：LLM 心跳检测（改进建议 #7）暂未实现，流式响应停滞检测已覆盖了核心场景

