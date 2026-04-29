import { fetchSuggestions, fetchQAContent } from "@/api/modules/suggestions";
import { extractCopyableText, extractUserMessageText } from "@/pages/Chat/utils";
import { useCallback, useRef, useEffect } from "react";
import { useContextSelector } from "use-context-selector";
import { ChatAnywhereSessionsContext } from "../../Context/ChatAnywhereSessionsContext";
import { useChatAnywhereOptions } from "../../Context/ChatAnywhereOptionsContext";

/**
 * 猜你想问建议获取 Hook
 *
 * 在响应完成后请求外部接口，并更新到当前响应中
 */
export default function useSuggestionsPolling(options: {
  currentQARef: React.MutableRefObject<{
    request?: any;
    response?: any;
    abortController?: AbortController;
  }>;
  updateMessage: (message: any) => void;
}) {
  const { currentQARef, updateMessage } = options;

  const currentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.currentSessionId,
  );

  const sessionApi = useChatAnywhereOptions((v) => v.session?.api);

  const sessionIdRef = useRef(currentSessionId);
  const activePollResponseIdRef = useRef<string | null>(null);

  useEffect(() => {
    sessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  const pollSuggestions = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) {
      console.debug("[Suggestions] No session ID available");
      return;
    }

    const currentRequest = currentQARef.current.request;
    const currentResponse = currentQARef.current.response;
    const turnId = currentResponse?.id;
    if (!turnId) {
      console.debug("[Suggestions] No response ID available");
      return;
    }

    activePollResponseIdRef.current = turnId;

    // 获取 chatId
    try {
      await (sessionApi as any)?.getSessionList?.();
    } catch (error) {
      console.debug("[Suggestions] getSessionList failed:", error);
    }
    const chatId = (sessionApi as any)?.getRealIdForSession?.(sessionId) ?? sessionId;

    // 提取用户问题
    const userMessage = extractUserMessageText(
      currentRequest?.cards?.[0]?.data?.input?.[0] ?? {},
    ).trim();

    if (!userMessage) {
      console.debug("[Suggestions] No user message available");
      return;
    }

    console.debug(
      "[Suggestions] Fetching for chatId:",
      chatId,
      "userMessage:",
      userMessage.slice(0, 50),
    );

    try {
      // Step 1: 从后端获取 Q&A 内容
      const qaResponse = await fetchQAContent({ chatId, userMessage });

      let qaContent = qaResponse.qa_content;

      // Fallback: 后端无内容时使用本地提取
      if (!qaContent) {
        console.debug("[Suggestions] Backend Q&A not found, using local extraction");
        const assistantMessage = extractCopyableText(
          currentResponse?.cards?.[0]?.data ?? {},
        ).trim();

        if (!assistantMessage) {
          console.debug("[Suggestions] Missing assistant response text");
          return;
        }

        qaContent = {
          user_message: userMessage,
          assistant_response: assistantMessage,
        };
      }

      // Step 2: 调用外部 API 生成 suggestions
      const suggestions = await fetchSuggestions({
        chatId,
        turnId,
        userMessage: qaContent.user_message,
        assistantMessage: qaContent.assistant_response,
      });

      // 检查是否已被新的请求覆盖
      if (activePollResponseIdRef.current !== turnId) {
        console.debug(
          "[Suggestions] Request cancelled, responseId mismatch. Expected:",
          turnId,
          "Active:",
          activePollResponseIdRef.current,
        );
        return;
      }

      if (!suggestions.length) {
        return;
      }

      const latestResponse = currentQARef.current.response;
      if (latestResponse?.id !== turnId) {
        console.debug(
          "[Suggestions] Response ID mismatch, skipping update. Expected:",
          turnId,
          "Current:",
          latestResponse?.id,
        );
        return;
      }

      // 更新响应
      if (latestResponse?.cards?.[0]?.data) {
        const updatedCards = [
          {
            ...latestResponse.cards[0],
            data: {
              ...latestResponse.cards[0].data,
              suggestions,
            },
          },
          ...latestResponse.cards.slice(1),
        ];

        currentQARef.current.response = {
          ...latestResponse,
          cards: updatedCards,
        };

        updateMessage(currentQARef.current.response);
      }
    } catch (error) {
      console.debug("[Suggestions] Fetch failed:", error);
    }
  }, [currentQARef, updateMessage, sessionApi]);

  return { pollSuggestions };
}
