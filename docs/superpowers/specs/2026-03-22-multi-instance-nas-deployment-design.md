# CoPaw 多实例容器化部署设计文档 (Redis 集群 + Redlock)

**日期**: 2026-03-30
**版本**: v1.2
**状态**: 已评审

---

## 1. 背景与目标

### 1.1 背景

CoPaw 当前支持单实例部署，所有数据存储在本地文件系统。随着用户规模增长，需要支持多实例水平扩展，并使用统一的 NAS 存储所有数据。

### 1.2 目标

- 支持 5-10 个 CoPaw 实例同时运行
- 使用统一 NAS 存储所有持久化数据
- **使用 Redis 集群 + Redlock 算法实现分布式锁**，解决定时任务并发执行问题
- 支持动态 Redis 集群节点扩缩容
- 不使用 IM 通道（QQ/飞书/钉钉等），无需处理 WebSocket 长连接
- 负载均衡无需会话亲和性

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        负载均衡器 (任意策略)                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
      ┌────┴────┐      ┌────┴────┐      ┌────┴────┐
      │ 实例 1  │      │ 实例 2  │  ... │ 实例 N  │  (5-10 实例)
      │         │      │         │      │         │
      │ ┌─────┐ │      │ ┌─────┐ │      │ ┌─────┐ │
      │ │AP   │ │      │ │AP   │ │      │ │AP   │ │
      │ │调度 │ │      │ │调度 │ │      │ │调度 │ │
      │ │器   │ │      │ │器   │ │      │ │器   │ │
      │ └──┬──┘ │      │ └──┬──┘ │      │ └──┬──┘ │
      │    │    │      │    │    │      │    │    │
      │ 获取锁 │      │ 获取锁 │      │ 获取锁 │
      └────┼────┘      └────┼────┘      └────┼────┘
           │                │                │
           └────────────────┼────────────────┘
                            │
                    ┌───────┴───────┐
                    │  Redis Cluster │  ← 分布式锁 (Redlock)
                    │  (多主节点)     │
                    └───────────────┘
                            │
                    ┌───────┴───────┐
                    │     NAS       │  ← 任务配置、状态、会话
                    │  (统一存储)    │
                    └───────────────┘
```

### 2.2 组件职责

| 组件 | 职责 |
|-----|------|
| 负载均衡器 | HTTP 请求分发，无需会话保持 |
| CoPaw 实例 | 处理 API 请求，执行定时任务（抢锁执行） |
| **Redis Cluster** | **提供分布式锁服务（Redlock 算法）** |
| NAS | 统一存储所有持久化数据 |

---

## 3. 存储设计

### 3.1 存储分层

| 数据类型 | 存储位置 | 说明 |
|---------|---------|-----|
| **分布式锁** | Redis Cluster | **仅定时任务调度使用 Redlock**（用户级锁） |
| **临时数据** | Redis Hash + TTL | `console_push`, `download_tasks`，**无锁** |
| **任务配置** | NAS `{user_dir}/jobs.json` | 现有实现，无需修改 |
| **任务状态** | NAS `{user_dir}/jobs_state.json` | 持久化任务状态 |
| **会话数据** | NAS `{user_dir}/sessions/*.json` | 现有实现 |
| **配置数据** | NAS `{user_dir}/config.json` | 现有实现 |
| **记忆数据** | NAS `{user_dir}/memory/` | 现有实现 |
| **备份任务** | NAS `{user_dir}/backup_tasks.json` | 现有实现 |

### 3.2 临时数据改用 Redis（关键变更）

**原因**: `console_push_store` 和 `download_task_store` 具有以下特点：
- 生命周期短（console_push 仅60秒有效期）
- 读写频繁
- consume-once 语义要求高
- 无需持久化
- **无需分布式锁**（仅定时任务调度使用 Redlock）

**方案**: 改用 Redis Hash + TTL，避免 NAS 文件锁竞争。

```python
# console_push_store 使用 Redis Hash + TTL
KEY = f"copaw:push:{user_id}"
TTL = 60  # 60秒过期

# download_task_store 使用 Redis Hash + TTL
KEY = f"copaw:download:{task_id}"
TTL = 3600  # 1小时过期
```

**注意**: 这些 Key **不使用 Hash Tag**（如 `{user_id}`），因为它们不需要与 Redlock Key 在同一 slot。

### 3.3 NAS 路径结构

```
/nas/copaw/
├── {user_id}/
│   ├── config.json              # 用户配置
│   ├── jobs.json                # 定时任务配置
│   ├── jobs_state.json          # 定时任务状态
│   ├── HEARTBEAT.md             # 心跳查询文件
│   ├── backup_tasks.json        # 备份任务状态
│   ├── envs.json                # 环境变量
│   ├── sessions/                # 会话目录
│   │   └── {session_id}.json
│   ├── memory/                  # 记忆数据
│   ├── active_skills/           # 激活的技能
│   ├── customized_skills/       # 自定义技能
│   └── models/                  # 本地模型
```

---

## 4. 分布式锁设计 (Redlock 算法)

### 4.1 架构概述

针对 **Redis 集群模式**（动态节点数量），采用 **Redlock 算法** 实现分布式锁：

```
┌─────────────────────────────────────────────────────────────┐
│                    RedlockDistributedLock                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  节点发现器 (ClusterNodeDiscovery)                       ││
│  │  - 种子节点: 2-3 个固定节点                               ││
│  │  - 刷新间隔: 60 秒 (偶尔扩缩容场景)                        ││
│  │  - 缓存节点列表，平滑处理节点变更                          ││
│  └─────────────────────────────────────────────────────────┘│
│                           │                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Redlock 算法实现                                        ││
│  │  - Quorum: N/2 + 1                                       ││
│  │  - 时钟漂移因子: 1%                                        ││
│  │  - 单节点超时: 50ms                                        ││
│  │  - 失败自动释放                                            ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────┴────┐           ┌────┴────┐           ┌────┴────┐
   │ Master 1│           │ Master 2│     ...   │ Master N│
   │ :6379   │           │ :6380   │           │ :63xx   │
   └─────────┘           └─────────┘           └─────────┘
```

### 4.2 锁粒度

**用户级锁**：同一用户的任务串行执行，不同用户的任务并行执行。

```python
# 锁 Key 格式（使用 Hash Tag 确保同一 slot）
KEY = f"copaw:cron:user:{{{user_id}}}"

# 示例
"copaw:cron:user:{alice}"  # alice 的所有任务竞争这把锁
"copaw:cron:user:{bob}"    # bob 的所有任务竞争这把锁
```

### 4.3 锁参数

| 参数 | 默认值 | 说明 | 可配置 |
|-----|-------|-----|-------|
| `REDIS_MODE` | `cluster` | Redis 模式: `single`/`cluster` | 是 |
| `REDIS_SEEDS` | - | 种子节点列表，逗号分隔 | 是 |
| `REDIS_CLUSTER_DISCOVERY_INTERVAL` | 60 (秒) | 节点发现间隔 | 是 |
| `CRON_LOCK_TTL` | 600 (秒) | 锁超时时间 | 是 |
| `CRON_LOCK_PREFIX` | `copaw:cron:user:` | 锁 Key 前缀 | 是 |
| `CRON_LOCK_RENEW_INTERVAL` | 300 (秒) | 锁续期间隔（TTL/2） | 否，固定 TTL/2 |
| `CRON_LOCK_JITTER` | 2000 (毫秒) | 抢锁随机延迟 | 是 |
| `REDIS_LOCK_SINGLE_TIMEOUT` | 50 (毫秒) | 单节点获取超时 | 是 |
| `REDIS_LOCK_RETRY_COUNT` | 3 | 重试次数 | 是 |
| `REDIS_LOCK_RETRY_DELAY` | 100 (毫秒) | 重试间隔 | 是 |
| `REDIS_LOCK_DRIFT_FACTOR` | 0.01 (1%) | 时钟漂移因子 | 是 |

### 4.4 Redlock 算法实现

#### 4.4.1 节点发现器

```python
class ClusterNodeDiscovery:
    """
    自动发现 Redis 集群主节点

    策略:
    - 维护种子节点列表 (2-3 个)，用于初始连接
    - 定期执行 CLUSTER NODES 获取完整拓扑
    - 缓存主节点列表，节点变更时平滑过渡
    - 发现失败时回退到缓存列表

    容错:
    - 种子节点部分不可用时仍可工作
    - 节点扩缩容期间使用旧列表，不影响现有锁
    """

    def __init__(self, seeds: List[str], discovery_interval: int = 60):
        self.seeds = seeds
        self.discovery_interval = discovery_interval
        self._masters: List[Redis] = []
        self._last_discovery: float = 0

    async def get_masters(self) -> List[Redis]:
        """获取当前所有主节点"""
        now = time.time()
        if now - self._last_discovery > self.discovery_interval:
            await self._refresh_nodes()
        return self._masters

    async def _refresh_nodes(self):
        """刷新节点列表"""
        for seed in self.seeds:
            try:
                nodes = await self._discover_from_seed(seed)
                if nodes:
                    self._masters = nodes
                    self._last_discovery = time.time()
                    return
            except Exception as e:
                logger.warning(f"Failed to discover from {seed}: {e}")

        # 全部失败，使用缓存（如果有）
        if not self._masters:
            raise RedisClusterError("Cannot discover any master nodes")
```

#### 4.4.2 Redlock 获取锁

```python
class RedlockDistributedLock:
    """
    分布式锁实现（Redlock 算法）

    算法步骤:
    1. 记录开始时间
    2. 向所有节点顺序尝试获取锁（单节点超时）
    3. 计算成功数 >= quorum 且总耗时 < TTL 剩余时间
    4. 成功则返回锁，失败则向所有节点释放
    """

    CLOCK_DRIFT_FACTOR = 0.01  # 1% 时钟漂移容差

    async def acquire(
        self,
        resource: str,
        ttl: int
    ) -> Optional[LockToken]:
        """
        获取分布式锁

        Args:
            resource: 锁资源标识
            ttl: 锁超时时间（毫秒）

        Returns:
            LockToken 如果成功，None 如果失败
        """
        lock_value = self._generate_unique_value()
        masters = await self.node_discovery.get_masters()
        quorum = len(masters) // 2 + 1

        for retry in range(self.retry_count):
            start_time = time.monotonic()
            locked_nodes = []

            # 向所有节点尝试获取锁
            for node in masters:
                try:
                    if await self._lock_single(node, resource, lock_value, ttl):
                        locked_nodes.append(node)
                except Exception:
                    continue

            # 计算耗时
            elapsed = (time.monotonic() - start_time) * 1000
            validity = ttl - elapsed - ttl * self.CLOCK_DRIFT_FACTOR

            # 检查是否满足条件
            if len(locked_nodes) >= quorum and validity > 0:
                return LockToken(
                    resource=resource,
                    value=lock_value,
                    validity=validity,
                    nodes=locked_nodes
                )

            # 失败，释放所有已获取的锁
            await self._unlock_all(masters, resource, lock_value)

            if retry < self.retry_count - 1:
                await asyncio.sleep(self.retry_delay_ms / 1000)

        return None

    async def _lock_single(
        self,
        node: Redis,
        resource: str,
        value: str,
        ttl: int
    ) -> bool:
        """向单个节点获取锁"""
        try:
            result = await asyncio.wait_for(
                node.set(
                    resource,
                    value,
                    nx=True,  # 仅当不存在
                    px=ttl    # 毫秒过期
                ),
                timeout=self.single_node_timeout_ms / 1000
            )
            return result is True
        except asyncio.TimeoutError:
            return False

    async def release(self, token: LockToken) -> None:
        """释放锁（向所有节点发送删除命令）"""
        masters = await self.node_discovery.get_masters()
        for node in masters:
            try:
                # 使用 Lua 脚本确保原子性检查
                await node.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('del', KEYS[1]) else return 0 end",
                    keys=[token.resource],
                    args=[token.value]
                )
            except Exception as e:
                logger.warning(f"Failed to release lock on {node}: {e}")
```

### 4.5 Lua 脚本（集群兼容）

```lua
-- release_lock.lua
-- 释放锁，仅当持有者匹配时才删除
-- 注意：在集群模式下，Key 通过 Hash Tag 确保在同一 slot
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0

-- extend_lock.lua
-- 续期锁，仅当持有者匹配时才续期
-- 用于 Redlock 续期（需要向所有已获取的节点续期）
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
```

### 4.6 Redlock 锁续期机制

**Redlock 续期策略**:
- 需要向获取锁的 **所有已成功节点** 续期
- 任一节点续期失败则标记为不健康
- 连续 3 次失败后放弃（与单实例一致）
- 使用 Lua 脚本确保原子性检查

```python
class RedlockRenewalTask:
    """Redlock 后台锁续期任务"""

    EXTEND_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('pexpire', KEYS[1], ARGV[2])
    end
    return 0
    """

    def __init__(
        self,
        node_discovery: ClusterNodeDiscovery,
        lock_token: LockToken,
        ttl_ms: int
    ):
        self.node_discovery = node_discovery
        self.lock_token = lock_token
        self.ttl_ms = ttl_ms
        self.interval = ttl_ms / 2000  # TTL/2 时续期（转换为秒）
        self._stop_event = asyncio.Event()
        self._task = None
        self._failed_renewals = 0
        self._max_failed_renewals = 3

    async def start(self):
        self._task = asyncio.create_task(self._renew_loop())

    async def stop(self):
        self._stop_event.set()
        if self._task:
            await self._task

    async def _renew_loop(self):
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval
                )
                break  # 收到停止信号
            except asyncio.TimeoutError:
                success = await self._extend()
                if not success:
                    self._failed_renewals += 1
                    logger.warning(
                        f"Redlock renewal failed ({self._failed_renewals}/{self._max_failed_renewals}) "
                        f"for key={self.lock_token.resource}"
                    )
                    if self._failed_renewals >= self._max_failed_renewals:
                        logger.error("Redlock renewal failed too many times, lock may be lost")
                        break
                else:
                    self._failed_renewals = 0

    async def _extend(self) -> bool:
        """向所有已获取的节点续期"""
        success_count = 0
        masters = await self.node_discovery.get_masters()
        quorum = len(masters) // 2 + 1

        # 向原持有锁的节点续期
        for node in self.lock_token.nodes:
            try:
                result = await node.eval(
                    self.EXTEND_SCRIPT,
                    keys=[self.lock_token.resource],
                    args=[self.lock_token.value, self.ttl_ms]
                )
                if result == 1:
                    success_count += 1
            except Exception as e:
                logger.debug(f"Failed to extend lock on node: {e}")

        # Redlock 续期策略：需要多数节点成功
        return success_count >= quorum

    def is_healthy(self) -> bool:
        return self._failed_renewals < self._max_failed_renewals
```

### 4.7 Redlock 使用流程（含续期和防惊群）

```python
async def _scheduled_callback(self, user_id: str, job_id: str):
    # 1. 随机延迟防止惊群效应
    jitter_ms = random.randint(0, CRON_LOCK_JITTER)
    await asyncio.sleep(jitter_ms / 1000)

    # 2. 检查 Redis 连接（Fail-Fast）
    if not await self._check_redis_cluster():
        logger.error(f"Redis cluster unavailable, skipping job for user={user_id}")
        return

    # 3. 尝试获取 Redlock
    lock_key = f"copaw:cron:user:{{{user_id}}}"
    ttl_ms = CRON_LOCK_TTL * 1000

    lock_token = await redlock.acquire(lock_key, ttl=ttl_ms)
    if not lock_token:
        logger.debug(f"Redlock held by another instance for user={user_id}")
        return

    # 4. 获取锁成功，启动 Redlock 续期任务
    renewal = RedlockRenewalTask(
        node_discovery,
        lock_token,
        ttl_ms
    )
    await renewal.start()

    try:
        # 5. 加载用户任务状态
        states = await self._load_user_states(user_id)
        self._states[user_id] = states

        # 6. 执行该用户的所有待运行任务
        await self._execute_user_pending_jobs(user_id)

        # 7. 持久化任务状态到 NAS
        await self._save_user_states(user_id)
    finally:
        # 8. 停止续期任务
        await renewal.stop()
        # 9. 释放 Redlock
        await redlock.release(lock_token)
```

### 4.8 容错设计

| 场景 | 处理方案 |
|-----|---------|
| 持有锁的节点下线 | 锁在 TTL 后过期，其他实例可获取（满足 quorum 即可） |
| 集群扩缩容 | 节点发现器 60 秒后刷新，不影响现有锁 |
| 时钟漂移 | 1% 因子保护（600s TTL 允许 6s 漂移） |
| 续期失败 | 多数节点续期失败则放弃，主任务感知后释放资源 |

---

## 5. NAS 文件锁设计

### 5.1 文件锁使用场景

虽然临时数据移到了 Redis，但 NAS 上的文件仍需要文件锁保护：

| 文件 | 锁类型 | 说明 |
|-----|-------|-----|
| `jobs.json` | 写锁 | 修改任务配置时 |
| `jobs_state.json` | 读写锁 | 读取和更新任务状态时 |
| `config.json` | 写锁 | 保存配置时 |
| `sessions/*.json` | 无锁 | 单会话只被一个实例处理 |

### 5.2 文件锁实现

使用 `portalocker` 库实现跨平台文件锁。

```python
import portalocker
from contextlib import asynccontextmanager

@asynccontextmanager
async def file_lock(path: Path, mode: str = "r"):
    """文件锁上下文管理器（异步包装）

    Args:
        path: 文件路径
        mode: 'r' 读锁(共享), 'w' 写锁(独占)
    """
    lock_mode = portalocker.LOCK_SH if mode == "r" else portalocker.LOCK_EX
    lock_mode |= portalocker.LOCK_NB  # 非阻塞

    # 写模式下确保文件存在
    if mode == "w":
        await asyncio.to_thread(_ensure_file_exists, path)

    fd = None
    try:
        fd = await asyncio.to_thread(open, path, "r+" if mode == "w" else "r")
        await asyncio.to_thread(portalocker.lock, fd, lock_mode)
        yield fd
    finally:
        if fd:
            await asyncio.to_thread(portalocker.unlock, fd)
            await asyncio.to_thread(fd.close)


def _ensure_file_exists(path: Path) -> None:
    """确保文件存在（同步方法，在线程中执行）"""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
```

### 5.3 任务状态读写流程

```python
async def _load_user_states(self, user_id: str) -> Dict[str, CronJobState]:
    """加载用户任务状态（带文件锁）"""
    state_path = get_user_state_path(user_id)

    if not state_path.exists():
        return {}

    async with file_lock(state_path, mode="r"):
        data = json.loads(state_path.read_text())
        return {k: CronJobState(**v) for k, v in data.items()}

async def _save_user_states(self, user_id: str) -> None:
    """保存用户任务状态（带文件锁）"""
    state_path = get_user_state_path(user_id)
    states = self._states.get(user_id, {})

    async with file_lock(state_path, mode="w"):
        # 原子写入
        tmp_path = state_path.with_suffix(".tmp")
        data = {k: v.model_dump() for k, v in states.items()}
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(state_path)
```

---

## 6. Redis 故障处理

### 6.1 故障检测

```python
async def check_redis_cluster() -> bool:
    """检查 Redis 集群连接状态"""
    try:
        masters = await node_discovery.get_masters()
        # 至少需要 quorum 个节点可用
        quorum = len(masters) // 2 + 1
        available = 0
        for node in masters:
            try:
                await asyncio.wait_for(node.ping(), timeout=1.0)
                available += 1
            except Exception:
                pass
        return available >= quorum
    except Exception:
        return False
```

### 6.2 故障模式

**采用 Fail-Fast 策略**：Redis 集群不可用时，所有实例跳过任务执行。

```python
async def _scheduled_callback(self, user_id: str, job_id: str):
    # 检查 Redis 集群连接
    if not await self._check_redis_cluster():
        logger.error(f"Redis cluster unavailable, skipping job for user={user_id}")
        return  # 不执行，等待 Redis 恢复

    # 正常流程...
```

**原因**:
1. Redis 集群可用性高，Fail-Fast 避免复杂降级逻辑
2. 任务可配置 misfire_grace_time，错过的任务会在 Redis 恢复后补执行
3. Redlock 算法天然处理部分节点故障（只需 quorum）

### 6.3 健康检查

```python
@app.get("/health")
async def health_check():
    """健康检查端点"""
    redis_ok = await check_redis()
    nas_ok = check_nas_writable()

    status = "healthy" if redis_ok and nas_ok else "unhealthy"
    code = 200 if status == "healthy" else 503

    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "redis": "connected" if redis_ok else "disconnected",
            "nas": "writable" if nas_ok else "not_writable",
            "instance_id": INSTANCE_ID,
        }
    )

@app.get("/ready")
async def readiness_check():
    """就绪检查端点（用于 Kubernetes）"""
    # 检查关键依赖
    if not await check_redis():
        raise HTTPException(status_code=503, detail="Redis not ready")
    if not check_nas_writable():
        raise HTTPException(status_code=503, detail="NAS not ready")
    return {"ready": True}
```

---

## 7. 实例标识

### 7.1 实例 ID 生成

```python
import socket
import uuid

# 优先级: 环境变量 > 主机名 > UUID
INSTANCE_ID = (
    os.environ.get("COPAW_INSTANCE_ID") or
    socket.gethostname() or
    str(uuid.uuid4())[:8]
)
```

### 7.2 环境变量配置

```bash
# Docker Compose（独立模式）
# 注意：在独立 Docker Compose 中，所有容器共享相同 hostname
# 建议留空让应用自动生成 UUID，或使用容器名称
  - COPAW_INSTANCE_ID=  # 留空，自动生成

# Docker Swarm 模式（推荐用于生产）
  - COPAW_INSTANCE_ID={{.Task.Name}}  # 使用 Swarm 任务名称

# Kubernetes
  - COPAW_INSTANCE_ID=$(POD_NAME)  # 使用 Pod 名称
```

# Kubernetes
env:
  - name: COPAW_INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.name  # Pod 名称
```

---

## 8. 改造清单

### 8.1 新增文件

| 文件 | 说明 |
|-----|------|
| `src/copaw/lock/redis_lock.py` | Redis 分布式锁抽象层 |
| `src/copaw/lock/redlock.py` | Redlock 算法实现（Redis 集群） |
| `src/copaw/lock/cluster_discovery.py` | Redis 集群节点发现器 |
| `src/copaw/lock/file_lock.py` | NAS 文件锁实现（封装 portalocker） |
| `src/copaw/lock/__init__.py` | 锁模块导出 |
| `src/copaw/store/redis_store.py` | Redis 版 console_push/download 存储 |

### 8.2 修改文件

| 文件 | 改造内容 |
|-----|---------|
| `src/copaw/app/crons/manager.py` | 1. 使用 Redlock 替换单节点锁<br>2. 添加随机延迟防惊群<br>3. 状态持久化到 NAS<br>4. Redis 集群故障检测 |
| `src/copaw/app/console_push_store.py` | 改用 Redis Hash + TTL（无锁） |
| `src/copaw/app/download_task_store.py` | 改用 Redis Hash + TTL（无锁） |
| `src/copaw/config/config.py` | 新增 Redis 集群配置、Redlock 配置 |
| `src/copaw/constant.py` | 新增 Redis 集群相关常量 |
| `src/copaw/app/_app.py` | 添加 `/health` 和 `/ready` 端点 |
| `deploy/docker-compose.yml` | 添加 Redis Cluster 服务，配置多实例部署 |
| `deploy/Dockerfile` | 添加 redis、portalocker 依赖 |
| `pyproject.toml` | 添加依赖 |

### 8.3 配置变更

#### 环境变量

```bash
# Redis 集群配置
COPAW_REDIS_MODE=cluster                        # single | cluster
COPAW_REDIS_SEEDS=node1:6379,node2:6379,node3:6379  # 种子节点列表
COPAW_REDIS_CLUSTER_DISCOVERY_INTERVAL=60       # 节点发现间隔（秒）
COPAW_REDIS_PASSWORD=                           # 密码（如需要）
COPAW_REDIS_SSL=false                           # 是否启用 SSL

# Redlock 分布式锁配置
COPAW_CRON_LOCK_TTL=600                         # 锁超时时间（秒）
COPAW_CRON_LOCK_JITTER=2000                     # 抢锁随机延迟（毫秒）
COPAW_REDIS_LOCK_SINGLE_TIMEOUT=50              # 单节点获取超时（毫秒）
COPAW_REDIS_LOCK_RETRY_COUNT=3                  # 重试次数
COPAW_REDIS_LOCK_RETRY_DELAY=100                # 重试间隔（毫秒）
COPAW_REDIS_LOCK_DRIFT_FACTOR=0.01              # 时钟漂移因子（1%）

# 实例标识
COPAW_INSTANCE_ID=                              # 自动生成（主机名或UUID）

# 工作目录（指向 NAS）
COPAW_WORKING_DIR=/nas/copaw
COPAW_SECRET_DIR=/nas/copaw/.secret
```

---

## 9. 部署方案

### 9.1 Docker Compose (Redis 集群模式)

```yaml
version: '3.8'

services:
  # Redis 集群 - 3 主 3 从
  redis-master-1:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_master_1:/data
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru

  redis-master-2:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_master_2:/data
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru

  redis-master-3:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_master_3:/data
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru

  # 集群初始化（仅首次运行）
  redis-cluster-init:
    image: redis:7-alpine
    depends_on:
      - redis-master-1
      - redis-master-2
      - redis-master-3
    command: >
      sh -c "
        sleep 5 &&
        redis-cli --cluster create
          redis-master-1:6379
          redis-master-2:6379
          redis-master-3:6379
          --cluster-replicas 0
          --cluster-yes
      "
    deploy:
      restart_policy:
        condition: on-failure
        max_attempts: 3

  copaw:
    image: copaw:latest
    restart: unless-stopped
    deploy:
      replicas: 5
    environment:
      - COPAW_WORKING_DIR=/nas/copaw
      - COPAW_SECRET_DIR=/nas/copaw/.secret
      # Redis 集群配置
      - COPAW_REDIS_MODE=cluster
      - COPAW_REDIS_SEEDS=redis-master-1:6379,redis-master-2:6379,redis-master-3:6379
      - COPAW_REDIS_CLUSTER_DISCOVERY_INTERVAL=60
      # Redlock 配置
      - COPAW_CRON_LOCK_TTL=600
      - COPAW_CRON_LOCK_JITTER=2000
      - COPAW_REDIS_LOCK_SINGLE_TIMEOUT=50
      - COPAW_REDIS_LOCK_RETRY_COUNT=3
      # 实例标识
      - COPAW_INSTANCE_ID={{.Task.Name}}
    volumes:
      - /mnt/nas/copaw:/nas/copaw:rw
    depends_on:
      - redis-cluster-init
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8088/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  redis_master_1:
  redis_master_2:
  redis_master_3:
```

### 9.2 NAS 挂载选项

```yaml
# Docker Compose 高级挂载选项
volumes:
  - type: bind
    source: /mnt/nas/copaw
    target: /nas/copaw
    bind:
      propagation: rshared
    # 或 NFS 直接挂载
  - type: nfs
    source: nas-server:/copaw
    target: /nas/copaw
```

**推荐挂载参数**（NFSv4）:
```bash
mount -t nfs4 -o
  vers=4.0,
  hard,
  intr,
  timeo=600,
  retrans=3,
  nolock,  # 禁用 NFS 客户端锁，使用应用层锁
  nas-server:/copaw /mnt/nas/copaw
```

---

## 10. 迁移方案

### 10.1 从单实例迁移到多实例 (Redis 集群)

**步骤**:

1. **准备 Redis 集群**
   ```bash
   # 使用 docker-compose 启动 Redis 集群
   docker-compose -f docker-compose.redis-cluster.yml up -d
   ```

2. **停止单实例**
   ```bash
   docker-compose down
   # 或 systemctl stop copaw
   ```

3. **迁移数据到 NAS**
   ```bash
   # 假设原数据在 ~/.copaw
   rsync -av ~/.copaw/ /mnt/nas/copaw/
   ```

4. **更新配置**
   - 设置 `COPAW_WORKING_DIR=/nas/copaw`
   - 配置 Redis 集群连接:
     ```bash
     COPAW_REDIS_MODE=cluster
     COPAW_REDIS_SEEDS=redis-node-1:6379,redis-node-2:6379,redis-node-3:6379
     ```

5. **启动多实例**
   ```bash
   docker-compose -f docker-compose.multi.yml up -d
   ```

6. **验证 Redlock 工作正常**
   - 检查日志中无重复执行
   - 测试节点扩缩容不影响锁获取

### 10.2 数据兼容性

| 数据 | 迁移影响 | 处理 |
|-----|---------|------|
| `config.json` | 无影响 | 直接使用 |
| `jobs.json` | 无影响 | 直接使用 |
| `sessions/` | 无影响 | 直接使用 |
| `memory/` | 无影响 | 直接使用 |
| `console_push` | **从内存移至 Redis** | **60秒 TTL，重启后重建** |
| `download_tasks` | **从内存移至 Redis** | **1小时 TTL，重启后重建** |
| `jobs_state` | 重置 | 重新加载后重建 |
| **定时任务锁** | **新增** | **使用 Redlock 算法** |

---

## 11. 容错设计

### 11.1 故障场景处理

| 场景 | 处理方案 |
|-----|---------|
| 实例宕机时持有锁 | 锁 TTL 过期后自动释放（默认10分钟） |
| 任务执行超时 | 锁自动过期，其他实例可接管 |
| **Redis 集群部分节点下线** | **Redlock 算法容忍少数节点故障（需满足 quorum）** |
| **Redis 集群全部不可用** | **Fail-Fast，所有实例跳过任务执行，等待恢复** |
| **集群扩缩容** | **节点发现器 60 秒后刷新，不影响现有锁** |
| NAS 不可写 | 任务执行失败，健康检查失败 |
| 锁续期失败 | 立即停止任务执行，释放资源 |
| 惊群效应 | 随机延迟 0-2 秒避免 |
| **时钟漂移** | **1% 漂移因子保护，600s TTL 允许 6s 漂移** |

### 11.2 监控指标

| 指标 | 类型 | 说明 |
|-----|------|------|
| `cron_lock_acquire_total` | Counter | 锁获取尝试次数 |
| `cron_lock_acquire_failed` | Counter | 锁获取失败次数 |
| `cron_lock_acquire_quorum_failed` | Counter | **Redlock quorum 不足次数** |
| `cron_lock_renewal_total` | Counter | 锁续期次数 |
| `cron_lock_renewal_failed` | Counter | 锁续期失败次数 |
| `cron_job_execution_time` | Histogram | 任务执行耗时 |
| `cron_job_execution_status` | Counter | 任务执行成功/失败数 |
| `redis_cluster_nodes_total` | Gauge | **Redis 集群节点总数** |
| `redis_cluster_nodes_available` | Gauge | **Redis 集群可用节点数** |
| `redis_cluster_discovery_errors` | Counter | **节点发现错误次数** |
| `nas_write_latency` | Histogram | NAS 写入延迟 |

---

## 12. 测试计划

### 12.1 功能测试

- [ ] 多实例下定时任务正常触发
- [ ] 同一用户任务不会重复执行（Redlock 防重）
- [ ] 不同用户任务并行执行
- [ ] Console Push 消息正常收发
- [ ] 下载任务状态同步正常
- [ ] 会话数据读写正常
- [ ] Redlock 获取锁成功（满足 quorum）
- [ ] **Redlock 容忍少数节点故障（< quorum）**
- [ ] **Redlock 节点自动发现正常工作**
- [ ] Redlock 续期机制正常工作

### 12.2 容错测试

- [ ] 实例宕机后锁自动释放
- [ ] **Redis 集群部分节点下线不影响锁获取**
- [ ] **Redis 集群全部不可用后 Fail-Fast**
- [ ] NAS 断开后恢复自动重连
- [ ] 长时间任务锁续期正常
- [ ] **集群扩缩容后节点发现正常**

### 12.3 性能测试

- [ ] 10 个实例并发运行稳定
- [ ] 100 个用户定时任务正常调度
- [ ] **Redlock 获取延迟 < 100ms（单节点 50ms 超时）**
- [ ] **Redlock 扩缩容期间无锁丢失**
| 惊群效应下无重复执行

---

## 13. 附录

### 13.1 依赖项

```toml
# pyproject.toml 新增依赖
[project.optional-dependencies]
redis = [
    "redis>=5.0.0",           # 支持 Redis Cluster
    "portalocker>=2.7.0",
]
```

### 13.2 术语表

| 术语 | 说明 |
|-----|------|
| NAS | Network Attached Storage，网络附加存储 |
| TTL | Time To Live，生存时间 |
| Lua | 轻量级脚本语言，Redis 支持原子操作 |
| APScheduler | Python 定时任务调度库 |
| 惊群效应 | 多个实例同时竞争资源导致性能下降 |
| **Redlock** | **Redis 分布式锁算法，用于多主节点集群环境** |
| **Quorum** | **多数节点，N/2 + 1，Redlock 获取锁的最小成功数** |

### 13.3 参考文档

- [Redis 分布式锁](https://redis.io/docs/manual/patterns/distributed-locks/)
- **[Redlock 算法](https://redis.io/docs/manual/patterns/distributed-locks/#the-redlock-algorithm)**
- **[Redis 集群教程](https://redis.io/docs/management/scaling/)**
- [Portalocker 文档](https://github.com/WoLpH/portalocker)
- [APScheduler 文档](https://apscheduler.readthedocs.io/)
- [CoPaw CLAUDE.md](../../CLAUDE.md)

---

## 14. 变更记录

| 版本 | 日期 | 变更内容 |
|-----|------|---------|
| v1.0 | 2026-03-22 | 初始版本 |
| v1.1 | 2026-03-22 | 修订版：添加锁续期、文件锁、Redis 存储临时数据、防惊群、健康检查、实例 ID 生成 |
| v1.2 | 2026-03-30 | **Redis 集群支持**：添加 Redlock 算法、节点自动发现、集群故障检测、Hash Tag Key 设计 |

---

**文档状态**: 评审中
**最后更新**: 2026-03-30
