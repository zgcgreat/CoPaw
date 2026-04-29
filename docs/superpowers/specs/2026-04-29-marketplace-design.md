# 应用市场功能设计文档

> 创建时间：2026-04-29
> 状态：已确认

---

## 一、需求概述

新建应用市场功能，包含**技能（Skills）**和 **MCP** 两部分。本期实现技能部分，MCP 部分留空占位由其他开发人员负责。

### 核心需求

| 功能点 | 说明 |
|--------|------|
| Source-ID 隔离 | 市场条目按 source-id 隔离，用户只能看到匹配自己 source-id 的条目 |
| bbk_id 过滤 | 总行（bbk_id=100）可见全部；分行用户只见总行技能和本分行技能 |
| 管理员分发 | 每个 source-id 有自己的管理员（manager 标识），可将技能分发到用户工作目录 |
| 应用市场页 | 所有用户可浏览，管理员额外拥有上架、下架、分发操作 |
| 技能菜单 | 新建技能菜单，左侧树状展示"我创建的"和"我接收的" |
| MCP 菜单 | 新建 MCP 菜单，留空占位 |
| 编辑权限 | 只有"我创建的"技能支持编辑保存 |

---

## 二、架构总览

### 存储层

**文件系统（内容存储）**

```
~/.swe.marketplace/
└── <source_id>/
    ├── index.json              # 市场条目索引
    └── skills/
        └── <item_id>/          # 技能完整快照
            ├── skill.json
            └── SKILL.md
```

**数据库（操作日志）**

新增 `marketplace_operation_logs` 表，记录所有写操作，支持分发记录查询和数据分析。

### 服务层

新增 `MarketplaceService`，职责：
- 市场技能 CRUD（管理员操作）
- 按 source-id + bbk-id 过滤内容
- 分发：将市场内容写入目标用户的 `~/.swe/<user_id>/` 目录
- 写操作同步记录日志到数据库

### API 层

在 `src/swe/app/routers/` 新增 `marketplace_router.py`，通过请求头 `X-Source-Id` 和 `manager` 标识做权限校验。

### 前端层

- 新增**应用市场**页面（所有用户可见）：技能 tab + MCP tab（留空）
- 新增**技能**菜单（所有用户可见）：我创建的 / 我接收的
- 新增**MCP** 菜单（留空占位）

---

## 三、数据模型

### 3.1 市场条目索引（index.json）

```json
{
  "items": [
    {
      "item_id": "uuid",
      "item_type": "skill",
      "name": "技能名称",
      "description": "描述",
      "version": "1.0.0",
      "creator_id": "user_id",
      "bbk_ids": [],
      "status": "active",
      "created_at": "ISO8601",
      "updated_at": "ISO8601"
    }
  ]
}
```

字段说明：
- `bbk_ids`：空数组表示对该 source_id 全员可见；非空时表示仅对指定 bbk_id 可见
- `status`：`active` 上架中；`inactive` 已下架

### 3.2 用户技能 skill.json 扩展字段

在现有 `skill.json` 基础上新增：

```json
{
  "source": "marketplace:{item_id}",
  "distributed_by": "user_id"
}
```

分类判断逻辑：
- **我创建的**：`source` 不含 `marketplace:` 前缀
- **我接收的**：`source` 含 `marketplace:` 前缀

### 3.3 数据库日志表

```sql
CREATE TABLE marketplace_operation_logs (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  source_id       VARCHAR(64)  NOT NULL,
  operator_id     VARCHAR(64)  NOT NULL,
  operation       VARCHAR(32)  NOT NULL,
  item_type       VARCHAR(16)  NOT NULL,
  item_id         VARCHAR(64)  NOT NULL,
  item_name       VARCHAR(256),
  target_user_id  VARCHAR(64),
  target_bbk_id   VARCHAR(64),
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_source_id (source_id),
  INDEX idx_item_id (item_id),
  INDEX idx_target_user_id (target_user_id)
);
```

字段说明：
- `operation`：`create` / `edit` / `delete` / `distribute`
- `item_type`：`skill` / `mcp`
- `target_user_id`：分发时展开到用户粒度，每个用户一条记录
- `target_bbk_id`：分发时快照目标用户所属机构，用于机构维度聚合统计

常用查询：
```sql
-- 某技能分发给了多少人
SELECT COUNT(DISTINCT target_user_id) FROM marketplace_operation_logs
WHERE item_id = ? AND operation = 'distribute';

-- 某 bbk_id 下收到了多少技能
SELECT COUNT(DISTINCT item_id) FROM marketplace_operation_logs
WHERE target_bbk_id = ? AND operation = 'distribute';

-- 某用户收到了哪些技能
SELECT * FROM marketplace_operation_logs
WHERE target_user_id = ? AND operation = 'distribute';
```

---

## 四、bbk_id 过滤规则

```python
if user.bbk_id == "100":
    # 总行用户，看该 source_id 下所有技能
    items where source_id == user.source_id
else:
    # 分行用户，看全员可见 + 总行技能 + 本分行技能
    items where source_id == user.source_id
      and (bbk_ids == [] or "100" in bbk_ids or user.bbk_id in bbk_ids)
```

---

## 五、API 设计

### 权限说明

- 所有接口从请求头读取 `X-Source-Id`
- 管理员操作额外校验 `manager` 标识

### 管理员 API

```
POST   /api/marketplace/skills                          # 上架技能
PUT    /api/marketplace/skills/{item_id}                # 编辑市场技能
DELETE /api/marketplace/skills/{item_id}                # 下架技能
POST   /api/marketplace/skills/{item_id}/distribute     # 分发技能
```

分发请求体：
```json
{
  "target_type": "all | bbk_id | user_id",
  "target_values": ["bbk_001", "bbk_002"]
}
```

字段说明：
- `target_type=all`：`target_values` 为空，分发给该 source_id 下所有用户
- `target_type=bbk_id`：`target_values` 为 bbk_id 列表，后端展开为对应用户列表
- `target_type=user_id`：`target_values` 为 user_id 列表，直接分发

分发逻辑：后端根据 `target_type` 展开目标用户列表，逐用户写文件 + 写日志（每用户一条，记录 `target_bbk_id` 快照）。

### 用户 API

```
GET    /api/marketplace/skills                  # 浏览市场技能列表（按 source_id + bbk_id 过滤）
GET    /api/marketplace/skills/{item_id}        # 预览技能详情

GET    /api/skills/mine                         # 我创建的技能（新增接口，按 source 字段过滤）
GET    /api/skills/received                     # 我接收的技能（新增接口，按 source 字段过滤）
PUT    /api/skills/{skill_name}                 # 编辑我创建的技能（复用现有接口）
DELETE /api/skills/{skill_name}                 # 删除技能（复用现有接口）
```

---

## 六、前端页面设计

### 菜单结构

```
侧边栏
├── 应用市场（所有用户可见）
│   ├── tab: 技能
│   └── tab: MCP（留空占位）
├── 技能（所有用户可见）
│   ├── 我创建的
│   └── 我接收的
└── MCP（所有用户可见，留空占位）
```

### 应用市场 - 技能 tab

共用同一页面，根据 `manager` 标识控制操作按钮显示：

| 操作 | 管理员 | 普通用户 |
|------|--------|----------|
| 浏览列表 | ✓ | ✓ |
| 预览详情 | ✓ | ✓ |
| 上架 | ✓ | - |
| 编辑 | ✓ | - |
| 下架 | ✓ | - |
| 分发 | ✓ | - |

**分发弹窗**：多选叠加模式
- 全员：勾选后禁用其他选项
- 按机构：多选下拉，列表从 `console/src/constants/bbk.ts` 静态读取
- 按用户：多选输入，支持搜索 user_id

### 技能菜单 - 我创建的

左侧树状列表 + 右侧详情面板：
- 技能内容预览（SKILL.md 渲染）
- 编辑：可修改技能内容和配置，保存后写回文件
- 启用/禁用：切换技能激活状态
- 删除：从用户工作目录移除

### 技能菜单 - 我接收的

左侧树状列表 + 右侧详情面板：
- 技能内容预览（只读）
- 启用/禁用：切换技能激活状态
- 删除：从用户工作目录移除
- 无编辑入口

---

## 七、本期范围

| 模块 | 本期 | 留空/后续 |
|------|------|-----------|
| 应用市场 - 技能 tab | 完整实现 | - |
| 应用市场 - MCP tab | 留空占位 | 其他开发人员 |
| 技能菜单 | 完整实现 | - |
| MCP 菜单 | 留空占位 | 其他开发人员 |
| 同步到市场 | - | 后续迭代 |
| 历史数据迁移 | - | 后续迭代 |
