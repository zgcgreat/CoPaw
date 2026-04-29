import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./i18n";
// 在 React 渲染之前尽早初始化 iframe 消息监听器
// 确保不遗漏父窗口发送的任何初始化消息 (USER_DATA)
import { initIframeMessageListener } from "./utils/iframeMessage";
import {
  isExternalTokenEnabled,
  ensureValidToken,
} from "./api/externalToken";
import { handleUrlOriginParam } from './utils/iframeMessage.ts'

/**
 * 初始化流程：
 * 1. 先获取外部 token（如果配置了）
 * 2. 等待 token 获取完成
 * 3. 初始化 iframe 消息监听器
 * 4. 渲染 React 应用
 */
async function initializeApp(): Promise<void> {
  // 初始化 iframe 消息监听器（在 React 渲染之前）
  // 确保不遗漏父窗口发送的任何消息
  initIframeMessageListener();

  // 在所有初始化之前获取 token，同步等待完成
  if (isExternalTokenEnabled()) {
    try {
      await ensureValidToken();
    } catch (error) {
      console.warn("SWE: 初始化token失败", error);
    }
  }

  // 处理传递URL参数的场景（需要在 token 初始化之后）
  await handleUrlOriginParam();

  // 渲染 React 应用
  createRoot(document.getElementById("root")!).render(<App />);
}

// 启动初始化
initializeApp();
