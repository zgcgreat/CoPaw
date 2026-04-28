# 用户操作统计模块设计

## 背景

运营分析需要统计用户维度的操作数据，包括：
- 创建技能数
- 编辑技能数
- 创建定时任务数

这些数据用于：
- 运营分析：管理层查看平台使用情况
- 用户维度聚合：分析用户活跃度、Top 操作用户排行
- 时间趋势分析：近 N 天操作趋势图

## 方案选择

### 前端埋点 vs 后端记录

| 维度 | 前端埋点 | 后端记录 |
|------|---------|---------|
| 数据准确性 | 一般（网络失败可能丢失） | 高（服务端保证落地） |
| 租户隔离 | 需额外处理 | 天然支持 |
| 与现有系统集成 | 独立体系 | 可复用 Token Usage / Tracing 模式 |

**选择：后端记录**

理由：
- 运营统计要求数据准确可靠
- 项目已有 Token Usage 和 Tracing 模块，可复用设计模式
- 天然支持租户隔离

### 操作日志 vs 预设指标

| 维度 | 操作日志 | 预设指标 |
|------|---------|---------|
| 扩展性 | 高 — 新增指标无需改结构 | 低 — 每增加指标都要改代码 |
| 灵活性 | 高 — 可任意聚合 | 低 — 只能查询预设指标 |
| 追溯能力 | 有 — 可查用户操作历史 | 无 — 只有汇总数 |

**选择：操作日志**

理由：
- 当前三个指标可从日志聚合得出
- 运营分析可能需要更多维度（删除、启用/禁用等）
- 支持审计需求（追溯用户具体操作）

### 存储方案

**选择：MySQL 独立统计模块**

理由：
- 与定时任务定义存储方式一致
- 便于复杂查询（聚合、关联）
- 支持事务保证数据一致性

## 操作类型定义

### 技能相关

| 操作类型 | 说明 | 触发时机 |
|---------|------|---------|
| `skill_create` | 创建技能 | 用户主动创建技能成功 |
| `skill_receive` | 接收广播技能 | 用户接收他人广播的技能 |
| `skill_edit` | 编辑技能 | 用户编辑技能成功（不区分来源） |
| `skill_delete` | 删除技能 | 用户删除技能成功 |
| `skill_import` | 导入技能 | 用户从技能库导入技能成功 |

### 定时任务相关

| 操作类型 | 说明 | 触发时机 |
|---------|------|---------|
| `cron_create` | 创建定时任务 | 用户创建定时任务成功 |
| `cron_edit` | 编辑定时任务 | 用户编辑定时任务成功 |
| `cron_delete` | 删除定时任务 | 用户删除定时任务成功 |
| `cron_enable` | 启用定时任务 | 用户启用定时任务 |
| `cron_disable` | 禁用定时任务 | 用户禁用定时任务 |

## 数据模型

### 操作日志表

```sql
CREATE TABLE user_operation_log (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id VARCHAR(64) NOT NULL COMMENT '租户ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    operation VARCHAR(32) NOT NULL COMMENT '操作类型',
    resource_type VARCHAR(32) NOT NULL COMMENT '资源类型: skill/cron',
    resource_id VARCHAR(64) DEFAULT NULL COMMENT '资源ID（技能名或任务ID）',
    extra JSON DEFAULT NULL COMMENT '扩展信息（如技能来源、变更摘要等）',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '操作时间',

    INDEX idx_tenant_user_time (tenant_id, user_id, created_at),
    INDEX idx_tenant_operation_time (tenant_id, operation, created_at),
    INDEX idx_tenant_resource (tenant_id, resource_type, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户操作日志';
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `tenant_id` | VARCHAR(64) | 租户隔离，支持多租户查询 |
| `user_id` | VARCHAR(64) | 用户ID，用于用户维度聚合 |
| `operation` | VARCHAR(32) | 操作类型，见上方定义 |
| `resource_type` | VARCHAR(32) | 资源类型：skill / cron |
| `resource_id` | VARCHAR(64) | 资源标识，便于追溯具体资源 |
| `extra` | JSON | 扩展字段，如 `{"source": "broadcast", "from_user": "alice"}` |
| `created_at` | DATETIME(6) | 操作时间，支持微秒精度 |

## 模块设计

### 目录结构

```
src/swe/user_operation/
├── __init__.py           # 模块入口，导出公共接口
├── models.py             # Pydantic 模型定义
├── manager.py            # 操作日志管理器
├── router.py             # FastAPI 路由
└── repo/
    ├── __init__.py
    ├── base.py           # 抽象仓库接口
    └── mysql.py          # MySQL 实现
```

### 核心类设计

```python
# models.py
from enum import Enum
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any

class OperationType(str, Enum):
    # 技能相关
    SKILL_CREATE = "skill_create"
    SKILL_RECEIVE = "skill_receive"
    SKILL_EDIT = "skill_edit"
    SKILL_DELETE = "skill_delete"
    SKILL_IMPORT = "skill_import"
    # 定时任务相关
    CRON_CREATE = "cron_create"
    CRON_EDIT = "cron_edit"
    CRON_DELETE = "cron_delete"
    CRON_ENABLE = "cron_enable"
    CRON_DISABLE = "cron_disable"

class ResourceType(str, Enum):
    SKILL = "skill"
    CRON = "cron"

class OperationLog(BaseModel):
    id: Optional[int] = None
    tenant_id: str
    user_id: str
    operation: OperationType
    resource_type: ResourceType
    resource_id: Optional[str] = None
    extra: Optional[dict[str, Any]] = None
    created_at: datetime

class OperationStats(BaseModel):
    operation: OperationType
    count: int

class UserOperationSummary(BaseModel):
    user_id: str
    stats: list[OperationStats]
    total: int

class DailyOperationStats(BaseModel):
    date: str
    operation: OperationType
    count: int
```

```python
# manager.py
class UserOperationManager:
    """用户操作日志管理器"""

    _instance: "UserOperationManager | None" = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, tenant_id: str) -> "UserOperationManager":
        """获取租户级单例"""
        ...

    async def record(
        self,
        user_id: str,
        operation: OperationType,
        resource_type: ResourceType,
        resource_id: str | None = None,
        extra: dict | None = None,
    ) -> None:
        """记录操作日志"""
        ...

    async def get_user_stats(
        self,
        user_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> UserOperationSummary:
        """获取用户操作统计"""
        ...

    async def get_daily_stats(
        self,
        start_date: date,
        end_date: date,
        operations: list[OperationType] | None = None,
    ) -> list[DailyOperationStats]:
        """获取每日操作统计（趋势分析）"""
        ...

    async def get_top_users(
        self,
        operation: OperationType,
        limit: int = 10,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[UserOperationSummary]:
        """获取操作数 Top 用户"""
        ...
```

### 记录时机

在以下后端 API 中调用 `UserOperationManager.record()`：

| API | 记录操作 |
|-----|---------|
| `POST /skills/workspace/{agent_id}` | `skill_create` |
| `PUT /skills/workspace/{agent_id}/{skill_name}` | `skill_edit` |
| `DELETE /skills/workspace/{agent_id}/{skill_name}` | `skill_delete` |
| `POST /skills/pool/import` | `skill_import` |
| 技能广播接收逻辑 | `skill_receive` |
| `POST /crons` | `cron_create` |
| `PUT /crons/{job_id}` | `cron_edit` |
| `DELETE /crons/{job_id}` | `cron_delete` |
| `PUT /crons/{job_id}/enable` | `cron_enable` |
| `PUT /crons/{job_id}/disable` | `cron_disable` |

## API 设计

### 获取用户操作统计

```
GET /user-operation/stats/users/{user_id}
```

Query 参数：
- `start_date`: 开始日期 (YYYY-MM-DD)
- `end_date`: 结束日期 (YYYY-MM-DD)

响应：
```json
{
  "user_id": "alice",
  "stats": [
    {"operation": "skill_create", "count": 15},
    {"operation": "skill_edit", "count": 42},
    {"operation": "cron_create", "count": 8}
  ],
  "total": 65
}
```

### 获取每日操作趋势

```
GET /user-operation/stats/daily
```

Query 参数：
- `start_date`: 开始日期 (必填)
- `end_date`: 结束日期 (必填)
- `operations`: 操作类型列表 (可选，逗号分隔)

响应：
```json
{
  "data": [
    {"date": "2026-04-01", "operation": "skill_create", "count": 120},
    {"date": "2026-04-01", "operation": "skill_edit", "count": 350},
    {"date": "2026-04-02", "operation": "skill_create", "count": 135},
    ...
  ]
}
```

### 获取 Top 用户排行

```
GET /user-operation/stats/top-users
```

Query 参数：
- `operation`: 操作类型 (必填)
- `limit`: 返回数量 (默认 10)
- `start_date`: 开始日期 (可选)
- `end_date`: 结束日期 (可选)

响应：
```json
{
  "items": [
    {"user_id": "alice", "count": 156},
    {"user_id": "bob", "count": 98},
    ...
  ]
}
```

## 性能分析

### 写入性能

- 单条 INSERT，毫秒级延迟
- 不阻塞主业务流程
- **结论：无明显影响**

### 存储空间

估算：
- 单用户日操作约 20 次
- 1000 活跃用户/月 ≈ 60 万条 ≈ 300MB
- **结论：存储压力很小**

### 查询性能

优化措施：
1. 复合索引 `(tenant_id, user_id, created_at)` 支持用户维度查询
2. 复合索引 `(tenant_id, operation, created_at)` 支持操作类型聚合
3. 时间范围查询走索引，避免全表扫描

可选优化（后期）：
- 增加预聚合汇总表 `user_operation_daily_stats`
- 每日定时任务聚合一次
- 统计查询直接读汇总表

## 扩展性

### 新增操作类型

只需：
1. 在 `OperationType` 枚举中添加新类型
2. 在对应 API 中调用 `record()`
3. 无需修改表结构

### 新增统计维度

`extra` JSON 字段支持灵活扩展：
```json
{
  "source": "broadcast",
  "from_user": "alice",
  "skill_version": "1.2.0"
}
```

后续可按 `extra` 字段做二次聚合。

## 与现有系统集成

### 复用模式

与 Token Usage 模块保持一致的设计风格：
- 单例管理器
- 租户级实例
- 异步写入
- Pydantic 模型

### 前端展示

在 Analytics 页面新增统计卡片：
- 用户操作趋势图
- Top 操作用户排行
- 各操作类型占比

可复用 `BusinessOverview` 页面的图表组件。

## 实施步骤

1. **创建数据库表** — 执行建表 SQL
2. **实现后端模块** — models、manager、repo、router
3. **集成记录逻辑** — 在各 API 成功后调用 record()
4. **实现查询 API** — 支持统计查询
5. **前端展示** — Analytics 页面新增统计模块
6. **测试验证** — 单元测试 + 集成测试
