import { useContextSelector } from "use-context-selector";
import { ChatAnywhereMessagesContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereMessagesContext";
import { ChatAnywhereSessionsContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereSessionsContext";
import { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat";
import { useMemo, useState, useEffect } from "react";
import { extractQuestionText } from "../types";

interface QuestionInfo {
  id: string;
  index: number;
  text: string;
}

/**
 * 获取用户问题消息列表（只包含已加载到DOM的消息）
 *
 * @param minQuestions 最小问题数量才显示（默认 1）
 * @returns QuestionInfo 数组和显示状态
 */
export function useQuestionMessages(minQuestions = 1) {
  const messages = useContextSelector(
    ChatAnywhereMessagesContext,
    (v) => v.messages,
  );

  const isSessionLoading = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.isSessionLoading,
  );

  // 使用useState存储已加载的问题列表
  const [loadedQuestions, setLoadedQuestions] = useState<QuestionInfo[]>([]);

  // 从messages中提取所有用户消息
  const allUserMessages = useMemo(() => {
    return messages.filter(
      (msg: IAgentScopeRuntimeWebUIMessage) => msg.role === "user",
    );
  }, [messages]);

  // 监听DOM变化，检查哪些消息已加载
  useEffect(() => {
    const checkLoadedMessages = () => {
      const questions: QuestionInfo[] = [];
      let loadedIndex = 0;

      for (const msg of allUserMessages) {
        const text = extractQuestionText(msg);
        if (!text) continue;

        // 检查消息是否已加载到DOM
        const messageElement = document.getElementById(msg.id);
        if (messageElement) {
          loadedIndex++;
          questions.push({
            id: msg.id,
            index: loadedIndex,
            text: text.length > 100 ? text.substring(0, 100) + "..." : text,
          });
        }
      }

      setLoadedQuestions(questions);
    };

    // 初始检查
    checkLoadedMessages();

    // 监听DOM变化（消息列表加载）
    const observer = new MutationObserver(() => {
      checkLoadedMessages();
    });

    const messageContainer = document.querySelector('[class*="bubble-list-scroll"]');
    if (messageContainer) {
      observer.observe(messageContainer, {
        childList: true,
        subtree: true,
      });
    }

    return () => {
      observer.disconnect();
    };
  }, [allUserMessages]);

  const shouldShow = useMemo(() => {
    if (isSessionLoading) return false;
    if (loadedQuestions.length < minQuestions) return false;
    return true;
  }, [isSessionLoading, loadedQuestions.length, minQuestions]);

  return {
    questions: loadedQuestions,
    shouldShow,
    total: loadedQuestions.length,
  };
}