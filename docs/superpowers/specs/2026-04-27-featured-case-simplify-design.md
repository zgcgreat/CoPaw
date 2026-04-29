# 精选案例管理简化设计文档

## 1. 背景

现有 `swe_featured_case` 表采用合并表设计，同时包含：
- `id`: 数据库自增主键
- `case_id`: 业务标识符

经分析，两者作用重复，且业务需求明确：
- 每个维度（source_id + bbk_id）可以有多条案例
- 不需要"同一案例在不同维度下有不同配置"

因此，**移除 `case_id` 字段，简化数据模型**。

---

## 2. 数据库变更

### 2.1 表结构（简化后）

```sql
CREATE TABLE IF NOT EXISTS `swe_featured_case` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '案例ID（唯一标识）',
    `source_id` VARCHAR(64) NOT NULL COMMENT '来源ID（从 X-Source-Id 获取）',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK ID（可选）',
    `label` VARCHAR(512) NOT NULL COMMENT '案例标题',
    `value` TEXT NOT NULL COMMENT '提问内容',
    `image_url` VARCHAR(1024) DEFAULT NULL COMMENT '案例图片 URL',
    `iframe_url` VARCHAR(1024) DEFAULT NULL COMMENT 'iframe 详情页 URL',
    `iframe_title` VARCHAR(256) DEFAULT NULL COMMENT 'iframe 标题',
    `steps` JSON DEFAULT NULL COMMENT '步骤说明（JSON 数组）',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_source_bbk` (`source_id`, `bbk_id`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='精选案例表';
```

### 2.2 变更对比

| 项目 | 变更前 | 变更后 |
|------|--------|--------|
| case_id 字段 | 存在 | 移除 |
| 唯一约束 | `uk_source_bbk_case (source_id, bbk_id, case_id)` | 无（id 自增唯一） |
| API 标识 | 使用 case_id | 使用数据库 id |

---

## 3. 后端变更

### 3.1 数据模型 (models.py)

```python
# 移除 case_id 相关字段

class FeaturedCase(BaseModel):
    id: Optional[int] = None
    source_id: str = Field(..., min_length=1, max_length=64)
    bbk_id: Optional[str] = Field(None, max_length=64)
    # case_id: str  # 移除
    label: str = Field(..., min_length=1, max_length=512)
    value: str = Field(..., min_length=1)
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FeaturedCaseCreate(BaseModel):
    bbk_id: Optional[str] = Field(None, max_length=64)
    # case_id: str  # 移除
    label: str = Field(..., min_length=1, max_length=512)
    value: str = Field(..., min_length=1)
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: int = 0


class FeaturedCaseUpdate(BaseModel):
    bbk_id: Optional[str] = Field(None, max_length=64)
    label: Optional[str] = Field(None, min_length=1, max_length=512)
    value: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1024)
    iframe_url: Optional[str] = Field(None, max_length=1024)
    iframe_title: Optional[str] = Field(None, max_length=256)
    steps: Optional[List[CaseStep]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
```

### 3.2 API 路由变更 (router.py)

| 端点 | 变更前 | 变更后 |
|------|--------|--------|
| 获取案例详情 | `GET /featured-cases/{case_id}` | `GET /featured-cases/{id}` |
| 更新案例 | `PUT /admin/cases/{case_id}` | `PUT /admin/cases/{id}` |
| 删除案例 | `DELETE /admin/cases/{case_id}` | `DELETE /admin/cases/{id}` |

### 3.3 存储层变更 (store.py)

- `get_case_by_id(case_id)` → `get_case_by_id(id)`
- `update_case(case_id, ...)` → `update_case(id, ...)`
- `delete_case(case_id)` → `delete_case(id)`
- `check_case_exists(source_id, case_id, bbk_id)` → 移除（不再需要按 case_id 查重）

### 3.4 服务层变更 (service.py)

- 创建案例时不再检查 case_id 是否已存在
- 直接按数据库 id 进行更新/删除

---

## 4. 前端变更

### 4.1 类型定义 (types/featuredCases.ts)

```typescript
export interface FeaturedCase {
  id: number;  // 数据库主键，唯一标识
  source_id: string;
  bbk_id?: string | null;
  // case_id: string;  // 移除
  label: string;
  value: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
  sort_order: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface FeaturedCaseCreate {
  bbk_id?: string | null;
  // case_id: string;  // 移除
  label: string;
  value: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
  sort_order?: number;
}
```

### 4.2 API 模块 (modules/featuredCases.ts)

```typescript
// 更新案例：使用 id 而非 case_id
adminUpdateCase: (id: number, caseItem: FeaturedCaseUpdate) =>
  request<{ success: boolean; data: FeaturedCase }>(
    `/featured-cases/admin/cases/${id}`,
    { method: "PUT", body: JSON.stringify(caseItem) }
  ),

// 删除案例：使用 id 而非 case_id
adminDeleteCase: (id: number) =>
  request<{ success: boolean }>(
    `/featured-cases/admin/cases/${id}`,
    { method: "DELETE" }
  ),
```

### 4.3 管理页面变更 (Control/FeaturedCases)

- `index.tsx`: `handleDelete(id)` 参数类型从 string 改为 number
- `columns.tsx`: 操作列使用 `record.id` 而非 `record.case_id`
- `CaseDrawer.tsx`: 移除 case_id 表单字段

### 4.4 展示组件变更 (components/agentscope-chat)

- `FeaturedCases/index.tsx`: 卡片 key 使用 `caseItem.id`
- `CaseDetailDrawer`: 接收的 caseData.id 类型为 number

---

## 5. 测试修复

### 5.1 需要移除的测试

- `TestModels.test_case_config_item`
- `TestModels.test_case_config_create`
- `TestModels.test_case_config_create_without_bbk_id`
- `TestFeaturedCaseStoreWithMockDb.test_list_configs_with_db`
- `TestFeaturedCaseStoreWithMockDb.test_get_config_cases`
- `TestFeaturedCaseStoreWithMockDb.test_upsert_config_with_db`
- `TestFeaturedCaseStoreWithMockDb.test_upsert_config_empty_list`
- `TestFeaturedCaseStoreWithMockDb.test_delete_config_with_db`
- `TestFeaturedCaseService.test_upsert_config_*`
- `TestFeaturedCaseService.test_delete_config_*`

### 5.2 需要修改的测试

- 所有 `case_id` 引用改为 `id`
- `check_case_exists` 相关测试移除
- 创建/更新/删除测试使用数字 id

---

## 6. 数据迁移

如需从旧表结构迁移：

```sql
-- 1. 备份原表
CREATE TABLE swe_featured_case_backup AS SELECT * FROM swe_featured_case;

-- 2. 删除原表
DROP TABLE swe_featured_case;

-- 3. 创建新表（使用简化结构）
-- 执行 content_config_tables.sql

-- 4. 迁移数据（无 case_id）
INSERT INTO swe_featured_case
    (id, source_id, bbk_id, label, value, image_url, iframe_url, iframe_title, steps, sort_order, is_active, created_at, updated_at)
SELECT
    id, source_id, bbk_id, label, value, image_url, iframe_url, iframe_title, steps, sort_order, is_active, created_at, updated_at
FROM swe_featured_case_backup;

-- 5. 确认无误后删除备份
-- DROP TABLE swe_featured_case_backup;
```

---

## 7. 实现检查清单

- [ ] 数据库表结构更新
- [ ] 后端 models.py 更新
- [ ] 后端 store.py 更新
- [ ] 后端 service.py 更新
- [ ] 后端 router.py 更新
- [ ] 前端类型定义更新
- [ ] 前端 API 模块更新
- [ ] 前端管理页面更新
- [ ] 前端展示组件更新
- [ ] 测试代码修复
- [ ] 设计文档同步更新
