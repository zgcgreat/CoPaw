import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat";

/**
 * 问题信息结构
 */
export interface QuestionInfo {
  id: string;              // 消息 ID，用于跳转定位
  index: number;           // 问题序号（1, 2, 3...）
  text: string;            // 问题文本（截断后）
  timestamp?: number;      // 消息时间戳
}

/**
 * ConversationQuickNav 组件 Props
 */
export interface ConversationQuickNavProps {
  /** 最小问题数量才显示（默认 1） */
  minQuestions?: number;
}

/**
 * 提取用户问题文本
 */
export function extractQuestionText(message: IAgentScopeRuntimeWebUIMessage): string {
  if (message.role !== "user") return "";

  const card = message.cards?.[0];
  if (!card || card.code !== "AgentScopeRuntimeRequestCard") return "";

  const data = card.data;
  if (!data?.input?.[0]?.content) return "";

  // 提取 text 类型内容
  const textContent = data.input[0].content
    .filter((c: { type: string }) => c.type === "text")
    .map((c: { text?: string }) => c.text || "")
    .join("\n");

  return textContent;
}