# -*- coding: utf-8 -*-
-- ============================================================
-- CoPaw 精选案例配置管理数据库表（简化版）
-- 创建时间: 2026-04-27
-- 说明: 移除 case_id 字段，使用数据库 id 作为唯一标识
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------
-- 表: swe_featured_case
-- 说明: 精选案例表
-- 变更: 移除 case_id 字段，移除唯一约束
-- -----------------------------------------------------------
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

-- -----------------------------------------------------------
-- 表: swe_greeting_config
-- 说明: 引导文案配置表（保留不变）
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_greeting_config` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `source_id` VARCHAR(64) NOT NULL COMMENT '来源ID（必填）',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK ID（可选，source_id 子分组）',
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

SET FOREIGN_KEY_CHECKS = 1;
