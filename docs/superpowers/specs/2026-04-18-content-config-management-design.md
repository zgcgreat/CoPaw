# CoPaw 引导文案与精选案例配置管理设计文档

> **注意**: 本文档已过时。请参考 [2026-04-27-featured-case-simplify-design.md](./2026-04-27-featured-case-simplify-design.md) 获取最新设计。主要变更：移除了 `case_id` 字段，简化为使用数据库 `id` 作为唯一标识。

## 1. 目标与范围

本方案的目标是为 CoPaw 提供基于 `source_id + bbk_id` 维度的动态配置能力，支持：

> 用户登录时，根据其所属的 source_id 和 bbk_id 精确匹配并展示对应的引导文案和精选案例。

### 1.1 功能范围

**本期实现：**
- 引导文案管理（greeting、subtitle、placeholder 的 CRUD）
- 精选案例管理（案例定义 + 维度关联配置）
- 按 source_id + bbk_id 维度精确匹配查询
- 前端管理页面（控制菜单）
- 前端展示侧动态渲染

**本期不实现：**
- 继承/覆盖机制（每个配置完全独立）
- 默认兜底配置（无匹配则不展示）
- 批量导入导出

---

## 2. 核心概念

### 2.1 维度模型

```
source_id（必填）: 来源标识，如租户、业务渠道
    │
    └── bbk_id（可选）: 业务板块 ID，source_id 的子分组

匹配规则：
- 精确匹配: source_id=X AND bbk_id=Y
- bbk_id 可为 NULL，使用 NULL-safe 比较 (bbk_id <=> %s)
- 无匹配时返回空（不展示内容）
```

### 2.2 配置结构

```
┌─────────────────────────────────────────────────────────────┐
│                 GreetingConfig (引导文案配置)                │
│  - source_id: 来源ID                                         │
│  - bbk_id: 业务板块ID (可空)                                 │
│  - greeting: 欢迎语                                          │
│  - subtitle: 副标题                                          │
│  - placeholder: 输入框占位符                                  │
│  - is_active: 是否启用                                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   FeaturedCase (精选案例)                   │
│  - case_id: 案例唯一标识                                     │
│  - label: 案例标题                                           │
│  - value: 提问内容                                           │
│  - iframe_url: 详情页 URL                                    │
│  - steps: 步骤说明 (JSON)                                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│               FeaturedCaseConfig (案例-维度关联)            │
│  - source_id: 来源ID                                         │
│  - bbk_id: 业务板块ID (可空)                                 │
│  - case_id: 关联的案例ID                                     │
│  - sort_order: 排序序号                                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 数据流

```
用户登录 (iframe)
    ↓
postMessage 传递 source_id + bbk_id
    ↓
iframeStore 存储上下文
    ↓
API 请求携带 X-Source-Id + X-Bbk-Id headers
    ↓
后端精确匹配查询
    ↓
返回配置或空
    ↓
前端渲染（无配置则不展示）
```

---

## 3. 架构设计

### 3.1 模块结构

```
src/swe/app/greeting/               # 引导文案模块
├── __init__.py                     # 导出 greeting_router
├── models.py                       # Pydantic 数据模型
├── store.py                        # 数据库操作层
├── service.py                      # 业务逻辑层
└── router.py                       # API 路由层

src/swe/app/featured_case/          # 精选案例模块
├── __init__.py                     # 导出 featured_case_router
├── models.py                       # Pydantic 数据模型
├── store.py                        # 数据库操作层
├── service.py                      # 业务逻辑层
└── router.py                       # API 路由层

console/src/pages/Control/
├── Greeting/                        # 引导文案管理页面
│   ├── index.tsx
│   └── components/
└── FeaturedCases/                   # 精选案例管理页面
    ├── index.tsx
    └── components/
```

### 3.2 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Router Layer                             │
│  - HTTP 端点定义                                             │
│  - 从 Request headers 提取 source_id/bbk_id                 │
│  - 响应格式化                                                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Service Layer                            │
│  - 业务逻辑封装                                              │
│  - 配置查重验证                                              │
│  - 操作日志记录                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Store Layer                              │
│  - 数据库 CRUD                                               │
│  - SQL 查询封装                                              │
│  - NULL-safe 比较 (<=>)                                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Database (MySQL)                          │
│  - swe_greeting_config                                      │
│  - swe_featured_case                                        │
│  - swe_featured_case_config                                 │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 与现有系统集成

复用现有数据库连接，与 instance 模块和 tracing 模块共用数据库配置：

```python
# router.py
def init_greeting_module(db=None):
    global _store, _service
    if db is None or not getattr(db, "is_connected", False):
        raise RuntimeError("Greeting module requires a connected database.")
    _store = GreetingStore(db)
    _service = GreetingService(_store)
```

---

## 4. 数据库设计

### 4.1 表结构

#### swe_greeting_config (引导文案配置表)

```sql
CREATE TABLE IF NOT EXISTS `swe_greeting_config` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `source_id` VARCHAR(64) NOT NULL COMMENT '来源ID（必填）',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK ID（可选）',
    `greeting` VARCHAR(512) NOT NULL COMMENT '欢迎语',
    `subtitle` VARCHAR(512) DEFAULT NULL COMMENT '副标题',
    `placeholder` VARCHAR(256) DEFAULT NULL COMMENT '输入框占位符',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_source_bbk` (`source_id`, `bbk_id`),
    INDEX `idx_source_id` (`source_id`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='引导文案配置表';
```

#### swe_featured_case (精选案例定义表)

```sql
CREATE TABLE IF NOT EXISTS `swe_featured_case` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `case_id` VARCHAR(64) NOT NULL COMMENT '案例唯一标识',
    `label` VARCHAR(512) NOT NULL COMMENT '案例标题',
    `value` TEXT NOT NULL COMMENT '提问内容',
    `image_url` VARCHAR(1024) DEFAULT NULL COMMENT '案例图片 URL',
    `iframe_url` VARCHAR(1024) DEFAULT NULL COMMENT 'iframe 详情页 URL',
    `iframe_title` VARCHAR(256) DEFAULT NULL COMMENT 'iframe 标题',
    `steps` JSON DEFAULT NULL COMMENT '步骤说明（JSON 数组）',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_case_id` (`case_id`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='精选案例定义表';
```

#### swe_featured_case_config (案例-维度关联表)

```sql
CREATE TABLE IF NOT EXISTS `swe_featured_case_config` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `source_id` VARCHAR(64) NOT NULL COMMENT '来源ID（必填）',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK ID（可选）',
    `case_id` VARCHAR(64) NOT NULL COMMENT '案例ID',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_source_bbk_case` (`source_id`, `bbk_id`, `case_id`),
    INDEX `idx_source_bbk` (`source_id`, `bbk_id`),
    INDEX `idx_case_id` (`case_id`),
    CONSTRAINT `fk_case_config_case`
        FOREIGN KEY (`case_id`)
        REFERENCES `swe_featured_case` (`case_id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='案例-维度关联表';
```

### 4.2 NULL-safe 查询

使用 `<=>` 操作符处理 bbk_id 可能为 NULL 的情况：

```sql
-- 精确匹配 source_id 和 bbk_id（包括 bbk_id 为 NULL）
SELECT * FROM swe_greeting_config
WHERE source_id = %s AND bbk_id <=> %s AND is_active = 1;

-- <=> 是 NULL-safe 等值比较：
-- NULL <=> NULL → TRUE
-- NULL <=> 'value' → FALSE
-- 'value' <=> 'value' → TRUE
```

### 4.3 索引策略

| 表 | 索引 | 用途 |
|---|------|------|
| swe_greeting_config | `uk_source_bbk` | 精确匹配查询（主查询） |
| swe_greeting_config | `idx_source_id` | 按来源筛选 |
| swe_featured_case | `uk_case_id` | 案例唯一约束 |
| swe_featured_case_config | `uk_source_bbk_case` | 唯一约束 + 查询 |
| swe_featured_case_config | `idx_source_bbk` | 按维度查询案例列表 |

---

## 5. API 设计

### 5.1 引导文案端点

| 方法 | 路径 | 说明 | Headers |
|-----|------|------|---------|
| GET | `/api/greeting/display` | 获取当前维度文案 | X-Source-Id (必填), X-Bbk-Id (可选) |
| GET | `/api/greeting/admin/list` | 配置列表（分页） | - |
| POST | `/api/greeting/admin` | 创建配置 | - |
| PUT | `/api/greeting/admin/{id}` | 更新配置 | - |
| DELETE | `/api/greeting/admin/{id}` | 删除配置 | - |

#### GET /api/greeting/display

**请求：**
```http
GET /api/greeting/display
X-Source-Id: source-001
X-Bbk-Id: bbk-001
```

**响应（有配置）：**
```json
{
    "greeting": "你好，欢迎来到智能助手！",
    "subtitle": "我可以帮你分析数据、撰写报告",
    "placeholder": "输入你的问题..."
}
```

**响应（无配置）：**
```json
null
```

#### POST /api/greeting/admin

**请求：**
```json
{
    "source_id": "source-001",
    "bbk_id": "bbk-001",
    "greeting": "你好，欢迎来到智能助手！",
    "subtitle": "我可以帮你分析数据、撰写报告",
    "placeholder": "输入你的问题..."
}
```

**响应：**
```json
{
    "success": true,
    "data": {
        "id": 1,
        "source_id": "source-001",
        "bbk_id": "bbk-001",
        "greeting": "你好，欢迎来到智能助手！",
        "subtitle": "我可以帮你分析数据、撰写报告",
        "placeholder": "输入你的问题...",
        "is_active": true,
        "created_at": "2026-04-18T08:00:00Z"
    }
}
```

### 5.2 精选案例端点

| 方法 | 路径 | 说明 |
|-----|------|------|
| GET | `/api/featured-cases` | 获取当前维度案例列表 |
| GET | `/api/featured-cases/{case_id}` | 获取案例详情 |
| GET | `/api/featured-cases/admin/cases` | 案例定义列表 |
| POST | `/api/featured-cases/admin/cases` | 创建案例定义 |
| PUT | `/api/featured-cases/admin/cases/{case_id}` | 更新案例定义 |
| DELETE | `/api/featured-cases/admin/cases/{case_id}` | 删除案例定义 |
| GET | `/api/featured-cases/admin/configs` | 维度配置列表 |
| GET | `/api/featured-cases/admin/configs/detail` | 维度配置详情 |
| PUT | `/api/featured-cases/admin/configs` | 创建/更新维度配置 |
| DELETE | `/api/featured-cases/admin/configs` | 删除维度配置 |

#### GET /api/featured-cases

**请求：**
```http
GET /api/featured-cases
X-Source-Id: source-001
X-Bbk-Id: bbk-001
```

**响应：**
```json
[
    {
        "id": "case-deposit-maturity",
        "label": "我要做存款经营...",
        "value": "我要做存款经营...",
        "image_url": null,
        "sort_order": 1,
        "detail": {
            "iframe_url": "",
            "iframe_title": "他行存款到期潜力客户名单",
            "steps": [
                {"title": "步骤1", "content": "..."}
            ]
        }
    }
]
```

#### PUT /api/featured-cases/admin/configs

**请求：**
```json
{
    "source_id": "source-001",
    "bbk_id": "bbk-001",
    "case_ids": [
        {"case_id": "case-deposit-maturity", "sort_order": 1},
        {"case_id": "case-fund-sales", "sort_order": 2}
    ]
}
```

**响应：**
```json
{
    "success": true
}
```

---

## 6. 前端集成

### 6.1 Headers 传递

**修改** `console/src/api/authHeaders.ts`：

```typescript
export function buildAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};
    // ... existing headers

    // 5. Source ID（来自 iframe context）
    if (iframeContext.source) {
        headers["X-Source-Id"] = iframeContext.source;
    }

    // 6. BBK ID（新增）
    if (iframeContext.bbk) {
        headers["X-Bbk-Id"] = iframeContext.bbk;
    }

    return headers;
}
```

### 6.2 展示侧改造

**WelcomeCenterLayout** (`console/src/components/agentscope-chat/WelcomeCenterLayout/index.tsx`)：

```typescript
const [greetingConfig, setGreetingConfig] = useState<{
    greeting?: string;
    subtitle?: string;
    placeholder?: string;
} | null>(null);

useEffect(() => {
    greetingApi.getDisplayGreeting()
        .then(setGreetingConfig)
        .catch(() => setGreetingConfig(null));
}, []);

// 使用动态配置或默认值
const greeting = greetingConfig?.greeting || "你好，你的专属小龙虾，前来报到！";
const placeholder = greetingConfig?.placeholder || "任何要求，尽管提…";
```

**FeaturedCases** (`console/src/components/agentscope-chat/FeaturedCases/index.tsx`)：

```typescript
// 改用新的 API（自动带 X-Source-Id + X-Bbk-Id headers）
useEffect(() => {
    featuredCasesApi.listCases()
        .then(setCases)
        .catch(() => setCases([]))
        .finally(() => setLoading(false));
}, []);
```

### 6.3 管理页面

#### 引导文案管理

```
控制 → 引导文案管理
├── 配置列表（表格）
│   ├── 列: source_id | bbk_id | 欢迎语 | 副标题 | 占位符 | 状态 | 操作
│   └── 操作: 编辑 | 删除
└── 新建配置（Drawer）
    └── 表单: source_id* | bbk_id | greeting* | subtitle | placeholder
```

#### 精选案例管理

```
控制 → 精选案例管理
├── Tab 1: 案例定义
│   ├── 案例列表（表格）
│   │   ├── 列: case_id | 标题 | 提问内容 | iframe_url | 状态 | 操作
│   │   └── 操作: 编辑 | 删除
│   └── 新建案例（Drawer）
│       └── 表单: case_id* | label* | value* | image_url | iframe_url | iframe_title | steps
└── Tab 2: 维度配置
    ├── 配置列表（表格）
    │   ├── 列: source_id | bbk_id | 案例数 | 操作
    │   └── 操作: 配置 | 删除
    └── 配置详情（Drawer）
        └── 表单: source_id* | bbk_id | 案例勾选（排序）
```

---

## 7. 数据迁移

### 7.1 迁移脚本

从现有的 `cases.json` + `user_cases.json` 迁移到数据库：

```python
# scripts/migrate_cases_to_db.py

async def migrate_cases(working_dir: str, db) -> None:
    cases_file = Path(working_dir) / "cases.json"
    user_cases_file = Path(working_dir) / "user_cases.json"

    # 1. 迁移案例定义
    if cases_file.exists():
        with open(cases_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for case in data.get("cases", []):
            await db.execute("""
                INSERT INTO swe_featured_case
                    (case_id, label, value, iframe_url, iframe_title, steps, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE label = VALUES(label)
            """, (
                case["id"], case["label"], case["value"],
                case.get("detail", {}).get("iframe_url"),
                case.get("detail", {}).get("iframe_title", ""),
                json.dumps(case.get("detail", {}).get("steps", [])),
                int(case.get("is_active", True))
            ))

    # 2. 迁移用户-案例映射
    if user_cases_file.exists():
        with open(user_cases_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # user_cases: {"default": ["case-1"], "userId": ["case-2"]}
        for user_id, case_ids in data.get("user_cases", {}).items():
            source_id = user_id  # userId 作为 source_id（向后兼容）
            for idx, case_id in enumerate(case_ids):
                await db.execute("""
                    INSERT INTO swe_featured_case_config
                        (source_id, bbk_id, case_id, sort_order, is_active)
                    VALUES (%s, %s, %s, %s, 1)
                """, (source_id, None, case_id, idx))
```

### 7.2 迁移策略

| 场景 | 处理方式 |
|------|---------|
| 新部署 | 直接使用新表结构和 API |
| 现有环境 | 运行迁移脚本后切换前端 |

---

## 8. 错误处理

### 8.1 错误码

| HTTP 状态码 | 错误场景 |
|------------|---------|
| 400 | 配置已存在 / 参数校验失败 |
| 400 | 案例 ID 已存在 |
| 404 | 配置不存在 / 案例不存在 |

### 8.2 业务错误消息

```python
# 引导文案
"配置 (source_id={source_id}, bbk_id={bbk_id}) 已存在"
"配置不存在"

# 精选案例
"案例 {case_id} 已存在"
"案例不存在"

# 维度配置
"无效的案例 ID: {case_id}"
```

---

## 9. 测试覆盖

### 9.1 单元测试

| 测试类 | 覆盖内容 |
|-------|---------|
| TestGreetingStore | 存储层 CRUD + NULL-safe 查询 |
| TestGreetingService | 业务逻辑 + 重复检测 |
| TestGreetingRouter | API 端点 + headers 提取 |
| TestFeaturedCaseStore | 案例存储 + 关联查询 |
| TestFeaturedCaseService | 案例业务逻辑 |
| TestFeaturedCaseRouter | 案例 API 端点 |

### 9.2 运行测试

```bash
venv/bin/python -m pytest tests/unit/app/test_greeting.py -v
venv/bin/python -m pytest tests/unit/app/test_featured_case.py -v
```

---

## 10. 部署注意事项

### 10.1 数据库初始化

```bash
mysql -u root -p copaw < scripts/sql/content_config_tables.sql
```

### 10.2 环境变量

复用现有数据库配置：

```bash
SWE_DB_HOST=localhost
SWE_DB_PORT=3306
SWE_DB_USER=copaw
SWE_DB_PASSWORD=secret
SWE_DB_NAME=copaw
```

### 10.3 模块初始化

在 `_app.py` lifespan 中添加：

```python
from .greeting.router import init_greeting_module
from .featured_case.router import init_featured_case_module

if db_connection:
    init_greeting_module(db_connection)
    init_featured_case_module(db_connection)
```

---

## 11. 版本历史

| 版本 | 日期 | 变更内容 |
|-----|------|---------|
| 1.0.0 | 2026-04-18 | 初始版本，支持引导文案和精选案例的动态配置管理 |
