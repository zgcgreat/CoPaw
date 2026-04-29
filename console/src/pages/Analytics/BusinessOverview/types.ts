/**
 * BusinessOverview 工具函数和类型定义
 */

// ============================================================
// 类型定义
// ============================================================

export interface StatCard {
  value: number;
  label: string;
  change?: number;
  suffix?: string;
  prefix?: string;
}

export interface PieChartData {
  name: string;
  value: number;
}

export interface LineChartData {
  date: string;
  value: number;
}

export interface BarChartData {
  name: string;
  value: number;
}

export interface UserRow {
  userId: string;
  name: string;
  calls: number;
  tokens: number;
  lastActive: string;
}

export interface SkillRow {
  name: string;
  calls: number;
  tokens: number;
}

export interface TrendData {
  date: string;
  calls: number;
  tokens: number;
  users: number;
}

export interface MetricCardData {
  totalCalls: number;
  callsGrowth: number;
  totalTokens: number;
  tokensGrowth: number;
  avgResponseTime: number;
  responseTimeGrowth: number;
  avgDuration: number;
  durationGrowth: number;
  sessionCount: number;
  sessionGrowth: number;
}

export type TimeRange = "day" | "week" | "month" | "custom";

// ============================================================
// 工具函数
// ============================================================

/**
 * 格式化数字（大数字用K/M表示）
 */
export function formatNumber(value: number | undefined | null, decimals: number = 1): string {
  // 确保是数字，非数字类型转为 0
  const numValue = typeof value === "number" && !isNaN(value) ? value : 0;
  if (numValue >= 1000000) {
    return `${(numValue / 1000000).toFixed(decimals)}M`;
  }
  if (numValue >= 1000) {
    return `${(numValue / 1000).toFixed(decimals)}K`;
  }
  return numValue.toString();
}

/**
 * 格式化Token数量
 */
export function formatTokens(value: number | undefined | null): string {
  // 确保是数字，非数字类型转为 0
  const numValue = typeof value === "number" && !isNaN(value) ? value : 0;
  if (numValue >= 1000000000) {
    return `${(numValue / 1000000000).toFixed(2)}B`;
  }
  if (numValue >= 1000000) {
    return `${(numValue / 1000000).toFixed(1)}M`;
  }
  if (numValue >= 1000) {
    return `${(numValue / 1000).toFixed(0)}K`;
  }
  return numValue.toString();
}

/**
 * 格式化百分比变化
 */
export function formatChange(value: number | undefined | null): string {
  // 确保是数字，如果是 undefined/null/对象等非数字类型则使用 0
  const numValue = typeof value === "number" && !isNaN(value) ? value : 0;
  const sign = numValue > 0 ? "+" : "";
  return `${sign}${numValue.toFixed(1)}%`;
}

/**
 * 格式化响应时间
 */
export function formatDuration(seconds: number | undefined | null): string {
  // 确保是数字，非数字类型转为 0
  const numValue = typeof seconds === "number" && !isNaN(seconds) ? seconds : 0;
  if (numValue < 1) {
    return `${(numValue * 1000).toFixed(0)}ms`;
  }
  return `${numValue.toFixed(1)}s`;
}

/**
 * 截断长名称，保持固定长度
 * @param name 原始名称
 * @param maxLength 最大长度，默认20
 * @returns 截断后的名称，超出部分显示为...
 */
export function truncateName(name: string, maxLength: number = 20): string {
  if (!name) return "";
  if (name.length <= maxLength) return name;
  return name.slice(0, maxLength) + "...";
}