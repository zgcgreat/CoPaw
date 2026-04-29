-- ============================================================
-- Tracing Tables Cleanup - Remove Unused Fields
-- Date: 2026-04-28
-- Description: Remove unused fields from tracing tables
--
-- Analysis Result:
-- 1. parent_span_id: Written but never queried, timeline uses time-based inference
-- 2. metadata: Defined for reading but never written, always NULL in practice
--
-- These fields were designed for future features but never fully implemented.
-- Safe to remove without data loss.
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------
-- swe_tracing_spans 表清理
-- -----------------------------------------------------------

-- 1. 删除 parent_span_id 字段（未使用的预留字段）
-- 层级关系通过时间顺序+事件类型推断，不依赖此字段
ALTER TABLE `swe_tracing_spans`
DROP COLUMN IF EXISTS `parent_span_id`;

-- 2. 删除 metadata 字段（从未写入的预留字段）
-- confidence 和 trigger_reason 使用默认值，metadata 始终为 NULL
ALTER TABLE `swe_tracing_spans`
DROP COLUMN IF EXISTS `metadata`;

-- -----------------------------------------------------------
-- 验证删除结果
-- -----------------------------------------------------------
SHOW COLUMNS FROM `swe_tracing_spans`;

-- -----------------------------------------------------------
-- 相关清理说明
-- -----------------------------------------------------------
-- 如果需要同步清理代码，需修改以下文件：
--
-- 1. src/swe/tracing/models.py
--    - 移除 Span.parent_span_id 字段定义
--    - 移除 Span.metadata 字段定义
--
-- 2. src/swe/tracing/store.py
--    - create_span: 移除 parent_span_id 和 metadata 列
--    - update_span: 移除 metadata 更新
--    - batch_create_spans: 移除 parent_span_id 和 metadata
--    - _row_to_span: 移除 parent_span_id 和 metadata 解析
--
-- 3. src/swe/tracing/manager.py
--    - emit_span: 移除 parent_span_id 参数和逻辑
--    - update_span: 移除 metadata 参数
--    - _update_span_fields: 移除 metadata 参数
--
-- 4. tests/unit/tracing/*.py
--    - 更新测试用例中的 Span 构造

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- 执行前请确认：
-- 1. 已备份数据库
-- 2. 已在测试环境验证
-- 3. 确认无自定义代码依赖这些字段
-- ============================================================
