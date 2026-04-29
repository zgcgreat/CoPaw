-- ============================================================
-- Tracing Tables Field Comments
-- Date: 2026-04-28
-- Description: Add field comments to swe_tracing_traces and swe_tracing_spans
-- ============================================================

SET NAMES utf8mb4;

-- -----------------------------------------------------------
-- swe_tracing_traces 表字段注释
-- -----------------------------------------------------------

ALTER TABLE `swe_tracing_traces`
    MODIFY COLUMN `id` BIGINT AUTO_INCREMENT COMMENT '自增主键',
    MODIFY COLUMN `trace_id` VARCHAR(36) NOT NULL COMMENT '追踪唯一标识，UUID格式',
    MODIFY COLUMN `source_id` VARCHAR(64) NOT NULL COMMENT '数据源标识，用于多租户数据隔离',
    MODIFY COLUMN `user_id` VARCHAR(128) DEFAULT NULL COMMENT '用户标识，发起请求的用户ID',
    MODIFY COLUMN `session_id` VARCHAR(36) DEFAULT NULL COMMENT '会话标识，同一会话的多次请求共享此ID',
    MODIFY COLUMN `channel` VARCHAR(32) DEFAULT NULL COMMENT '通道来源，如 console/webhook/api 等',
    MODIFY COLUMN `start_time` DATETIME DEFAULT NULL COMMENT '追踪开始时间，用户请求发起时刻',
    MODIFY COLUMN `end_time` DATETIME DEFAULT NULL COMMENT '追踪结束时间，请求完成时刻',
    MODIFY COLUMN `duration_ms` INT DEFAULT NULL COMMENT '总耗时（毫秒），从开始到结束的时长',
    MODIFY COLUMN `model_name` VARCHAR(64) DEFAULT NULL COMMENT '主要使用的模型名称，如 gpt-4/claude-3',
    MODIFY COLUMN `total_input_tokens` INT DEFAULT 0 COMMENT '输入Token总数，所有LLM调用的输入累计',
    MODIFY COLUMN `total_output_tokens` INT DEFAULT 0 COMMENT '输出Token总数，所有LLM调用的输出累计',
    MODIFY COLUMN `total_tokens` INT DEFAULT 0 COMMENT 'Token总数，等于输入+输出',
    MODIFY COLUMN `tools_used` JSON DEFAULT NULL COMMENT '使用的工具列表，JSON数组格式',
    MODIFY COLUMN `skills_used` JSON DEFAULT NULL COMMENT '使用的技能列表，JSON数组格式',
    MODIFY COLUMN `status` VARCHAR(16) DEFAULT 'running' COMMENT '追踪状态：running/completed/error/cancelled',
    MODIFY COLUMN `error` TEXT DEFAULT NULL COMMENT '错误信息，失败时记录的错误描述',
    MODIFY COLUMN `user_message` TEXT DEFAULT NULL COMMENT '用户输入消息，截断后的摘要内容';

-- -----------------------------------------------------------
-- swe_tracing_spans 表字段注释
-- -----------------------------------------------------------

ALTER TABLE `swe_tracing_spans`
    MODIFY COLUMN `id` BIGINT AUTO_INCREMENT COMMENT '自增主键',
    MODIFY COLUMN `span_id` VARCHAR(36) NOT NULL COMMENT 'Span唯一标识，UUID格式',
    MODIFY COLUMN `trace_id` VARCHAR(36) NOT NULL COMMENT '所属追踪ID，关联 swe_tracing_traces.trace_id',
    MODIFY COLUMN `source_id` VARCHAR(64) NOT NULL COMMENT '数据源标识，用于多租户数据隔离',
    MODIFY COLUMN `parent_span_id` VARCHAR(36) DEFAULT NULL COMMENT '父SpanID，用于构建嵌套调用层级',
    MODIFY COLUMN `name` VARCHAR(128) DEFAULT NULL COMMENT 'Span名称/操作名称，如工具名或事件描述',
    MODIFY COLUMN `event_type` VARCHAR(32) NOT NULL COMMENT '事件类型：llm_input/llm_output/tool_call_start/tool_call_end/skill_invocation',
    MODIFY COLUMN `start_time` DATETIME NOT NULL COMMENT 'Span开始时间',
    MODIFY COLUMN `end_time` DATETIME DEFAULT NULL COMMENT 'Span结束时间',
    MODIFY COLUMN `duration_ms` INT DEFAULT NULL COMMENT '耗时（毫秒）',
    MODIFY COLUMN `user_id` VARCHAR(128) DEFAULT '' COMMENT '用户标识，冗余存储便于直接查询',
    MODIFY COLUMN `session_id` VARCHAR(36) DEFAULT '' COMMENT '会话标识，冗余存储便于直接查询',
    MODIFY COLUMN `channel` VARCHAR(32) DEFAULT '' COMMENT '通道来源，冗余存储便于直接查询',
    MODIFY COLUMN `model_name` VARCHAR(64) DEFAULT NULL COMMENT '模型名称，仅LLM事件使用',
    MODIFY COLUMN `input_tokens` INT DEFAULT NULL COMMENT '输入Token数，仅LLM事件使用',
    MODIFY COLUMN `output_tokens` INT DEFAULT NULL COMMENT '输出Token数，仅LLM事件使用',
    MODIFY COLUMN `tool_name` VARCHAR(64) DEFAULT NULL COMMENT '工具名称，仅工具事件使用',
    MODIFY COLUMN `skill_name` VARCHAR(128) DEFAULT NULL COMMENT '技能名称，用于工具归属和技能事件',
    MODIFY COLUMN `mcp_server` VARCHAR(64) DEFAULT NULL COMMENT 'MCP服务器名，标识MCP工具来源',
    MODIFY COLUMN `tool_input` JSON DEFAULT NULL COMMENT '工具输入参数，脱敏后的JSON格式',
    MODIFY COLUMN `tool_output` TEXT DEFAULT NULL COMMENT '工具输出结果，截断后的摘要',
    MODIFY COLUMN `error` TEXT DEFAULT NULL COMMENT '错误信息，失败时记录',
    MODIFY COLUMN `metadata` JSON DEFAULT NULL COMMENT '元数据，存储置信度、触发原因等扩展信息';

-- -----------------------------------------------------------
-- 验证注释是否生效
-- -----------------------------------------------------------
-- 查看 swe_tracing_traces 表结构
SHOW FULL COLUMNS FROM `swe_tracing_traces`;

-- 查看 swe_tracing_spans 表结构
SHOW FULL COLUMNS FROM `swe_tracing_spans`;