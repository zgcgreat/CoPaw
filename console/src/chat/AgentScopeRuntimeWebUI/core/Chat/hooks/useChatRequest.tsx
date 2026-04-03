import { sleep, Stream } from "@/chat";
import { useCallback, useRef, useEffect } from "react";
import { useContextSelector } from "use-context-selector";
import { useChatAnywhereOptions } from "../../Context/ChatAnywhereOptionsContext";
import { ChatAnywhereInputContext } from "../../Context/ChatAnywhereInputContext";
import AgentScopeRuntimeResponseBuilder from "../../AgentScopeRuntime/Response/Builder";
import { AgentScopeRuntimeRunStatus, AgentScopeRuntimeMessageType, AgentScopeRuntimeContentType, IAgentScopeRuntimeMessage, ITextContent } from "../../AgentScopeRuntime/types";
import { IAgentScopeRuntimeWebUIMessage, ToolProgress } from "@/chat";
import { IAgentScopeRuntimeWebUIInputData } from "../../types";

interface UseChatRequestOptions {
  currentQARef: React.MutableRefObject<{
    request?: IAgentScopeRuntimeWebUIMessage;
    response?: IAgentScopeRuntimeWebUIMessage;
    abortController?: AbortController;
  }>;
  updateMessage: (message: IAgentScopeRuntimeWebUIMessage) => void;
  getCurrentSessionId: () => string;
  onFinish: () => void;
}

/**
 * 提取展示文本（只计算 MESSAGE 类型的文本内容）
 */
function extractDisplayText(output: IAgentScopeRuntimeMessage[]): string {
  let text = '';

  for (const msg of output) {
    if (msg.type === AgentScopeRuntimeMessageType.MESSAGE) {
      for (const content of msg.content || []) {
        if (content.type === AgentScopeRuntimeContentType.TEXT) {
          text += (content as ITextContent).text || '';
        }
      }
    }
  }

  return text;
}

/**
 * 估算 token 数（字符数 / 4）
 */
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

/**
 * 计算工具执行进度
 */
function calculateToolProgress(output: IAgentScopeRuntimeMessage[]): ToolProgress | null {
  const toolMessages = output.filter(msg =>
    [AgentScopeRuntimeMessageType.FUNCTION_CALL,
     AgentScopeRuntimeMessageType.PLUGIN_CALL,
     AgentScopeRuntimeMessageType.MCP_CALL].includes(msg.type)
  );

  if (toolMessages.length === 0) return null;

  return {
    total: toolMessages.length,
    completed: toolMessages.filter(m => m.status === AgentScopeRuntimeRunStatus.Completed).length,
    inProgress: toolMessages.filter(m => m.status === AgentScopeRuntimeRunStatus.InProgress).length,
    failed: toolMessages.filter(m => m.status === AgentScopeRuntimeRunStatus.Failed).length,
  };
}

/**
 * 处理 API 请求和流式响应的 Hook
 */
export default function useChatRequest(options: UseChatRequestOptions) {
  const { currentQARef, updateMessage, getCurrentSessionId, onFinish } = options;
  const apiOptions = useChatAnywhereOptions(v => v.api);
  const setProcessing = useContextSelector(ChatAnywhereInputContext, v => v.setProcessing);

  // 使用 ref 保存最新的 apiOptions，避免闭包陷阱
  const apiOptionsRef = useRef(apiOptions);

  // 节流更新相关 ref
  const lastUpdateTimeRef = useRef(0);
  const pendingUpdateRef = useRef<{ tokenCount: number; toolProgress: ToolProgress | null } | null>(null);
  const processingStartedRef = useRef(false);

  useEffect(() => {
    apiOptionsRef.current = apiOptions;
  }, [apiOptions]);

  // 节流更新处理状态
  const throttledUpdateProcessing = useCallback((tokenCount: number, toolProgress: ToolProgress | null) => {
    const now = Date.now();
    const throttleMs = 300;

    if (now - lastUpdateTimeRef.current >= throttleMs) {
      // 可以立即更新
      lastUpdateTimeRef.current = now;
      setProcessing({ status: 'processing', tokenCount, toolProgress });
    } else {
      // 保存待更新的数据
      pendingUpdateRef.current = { tokenCount, toolProgress };

      // 在剩余时间后更新
      const remainingTime = throttleMs - (now - lastUpdateTimeRef.current);
      setTimeout(() => {
        if (pendingUpdateRef.current) {
          lastUpdateTimeRef.current = Date.now();
          setProcessing({
            status: 'processing',
            tokenCount: pendingUpdateRef.current.tokenCount,
            toolProgress: pendingUpdateRef.current.toolProgress
          });
          pendingUpdateRef.current = null;
        }
      }, remainingTime);
    }
  }, [setProcessing]);


  const mockRequest = useCallback(async (mockdata) => {
    const agentScopeRuntimeResponseBuilder = new AgentScopeRuntimeResponseBuilder({
      id: '',
      status: AgentScopeRuntimeRunStatus.Created,
      created_at: 0,
    });

    for await (const chunk of mockdata) {

      const res = agentScopeRuntimeResponseBuilder.handle(chunk);
      currentQARef.current.response.cards = [
        {
          code: 'AgentScopeRuntimeResponseCard',
          data: res,
        }
      ];

      updateMessage(currentQARef.current.response);

      await sleep(100);

    }
  }, [])


  const request = useCallback(async (historyMessages: any[], biz_params?: IAgentScopeRuntimeWebUIInputData['biz_params']) => {
    // 使用 ref.current 获取最新的 apiOptions
    const currentApiOptions = apiOptionsRef.current;
    const { enableHistoryMessages = false } = currentApiOptions;
    const abortSignal = currentQARef.current.abortController?.signal;

    // 重置处理状态追踪
    processingStartedRef.current = false;
    lastUpdateTimeRef.current = 0;
    pendingUpdateRef.current = null;

    let response
    try {
      response = currentApiOptions.fetch ? await currentApiOptions.fetch({
        input: historyMessages,
        biz_params,
        signal: abortSignal,
      }) : await fetch(currentApiOptions.baseURL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentApiOptions.token || ''}`,
        },
        body: JSON.stringify({
          input: enableHistoryMessages ? historyMessages : historyMessages.slice(-1),
          session_id: getCurrentSessionId(),
          stream: true,
          biz_params,
        }),
        signal: abortSignal,
      });
    } catch (error) {
    }

    if (response && response.body) {
      const agentScopeRuntimeResponseBuilder = new AgentScopeRuntimeResponseBuilder({
        id: '',
        status: AgentScopeRuntimeRunStatus.Created,
        created_at: 0,
      });

      if (!response.ok) {
        response.json().then(data => {
          const res = agentScopeRuntimeResponseBuilder.handle({
            object: 'message',
            type: AgentScopeRuntimeMessageType.ERROR,
            content: [],
            id: 'error',
            role: 'assistant',
            status: AgentScopeRuntimeRunStatus.Failed,
            code: response.status,
            message: JSON.stringify(data),
          });


          currentQARef.current.response.cards = [
            {
              code: 'AgentScopeRuntimeResponseCard',
              data: res,
            }
          ];
          onFinish();
        });
        return;
      }

      try {

        for await (const chunk of Stream({
          readableStream: response.body,
        })) {
          // 检查是否被中断
          if (currentQARef.current.response?.msgStatus === 'interrupted') {
            currentQARef.current.abortController?.abort();
            if (currentApiOptions.cancel) {
              currentApiOptions.cancel({
                session_id: getCurrentSessionId(),
              });
            }

            currentQARef.current.response.cards = [
              {
                code: 'AgentScopeRuntimeResponseCard',
                data: agentScopeRuntimeResponseBuilder.cancel(),
              }
            ];

            updateMessage(currentQARef.current.response);
            break;
          }

          const responseParser = apiOptionsRef.current.responseParser || JSON.parse;
          const chunkData = responseParser(chunk.data);
          const res = agentScopeRuntimeResponseBuilder.handle(chunkData);


          // 跳过空内容
          if (res.status !== AgentScopeRuntimeRunStatus.Failed && !res.output?.[0]?.content?.length) continue;

          if (currentQARef.current.response) {
            currentQARef.current.response.cards = [
              {
                code: 'AgentScopeRuntimeResponseCard',
                data: res,
              }
            ];

            if (res.status === AgentScopeRuntimeRunStatus.Completed || res.status === AgentScopeRuntimeRunStatus.Failed) {
              onFinish();
            } else {
              updateMessage(currentQARef.current.response);

              // 更新处理状态（首个内容后切换为 processing）
              if (!processingStartedRef.current) {
                processingStartedRef.current = true;
                setProcessing({ status: 'processing' });
              }

              // 计算 token 和工具进度
              const displayText = extractDisplayText(res.output || []);
              const tokenCount = estimateTokens(displayText);
              const toolProgress = calculateToolProgress(res.output || []);

              throttledUpdateProcessing(tokenCount, toolProgress);
            }
          }
        }
      } catch (error) {
        console.error(error);

      }
    }
  }, [getCurrentSessionId, currentQARef, updateMessage, onFinish, setProcessing, throttledUpdateProcessing]);

  return { request, mockRequest };
}
