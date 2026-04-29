import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./i18n";

// ==================== iframe 集成 (Kun He) ====================
// 在 React 渲染之前尽早初始化 iframe 消息监听器
// 确保不遗漏父窗口发送的任何初始化消息 (USER_DATA)
import { initIframeMessageListener } from "./utils/iframeMessage";
// ==================== iframe 集成结束 ====================

// ==================== 外部系统 Token 鉴权 ====================
import {
  isExternalTokenEnabled,
  ensureValidToken,
} from "./api/externalToken";
// ==================== 外部系统 Token 鉴权结束 ====================

/**
 * 初始化流程：
 * 1. 先获取外部 token（如果配置了）
 * 2. 等待 token 获取完成
 * 3. 初始化 iframe 消息监听器
 * 4. 渲染 React 应用
 */
async function initializeApp(): Promise<void> {
  // ==================== 外部系统 Token 鉴权 ====================
  // 在所有初始化之前获取 token，同步等待完成
  if (isExternalTokenEnabled()) {
    try {
      await ensureValidToken();
    } catch (error) {
      console.warn("Failed to initialize external token:", error);
    }
  }
  // ==================== 外部系统 Token 鉴权结束 ====================

  // ==================== iframe 集成 (Kun He) ====================
  // 初始化 iframe 消息监听器（在 React 渲染之前）
  // 确保不遗漏父窗口发送的任何消息
  initIframeMessageListener();
  // ==================== iframe 集成结束 ====================

  // 过滤不必要的 console 警告
  if (typeof window !== "undefined") {
    const originalError = console.error;
    const originalWarn = console.warn;

    console.error = function (...args: any[]) {
      const msg = args[0]?.toString() || "";
      if (msg.includes(":first-child") || msg.includes("pseudo class")) {
        return;
      }
      originalError.apply(console, args);
    };

    console.warn = function (...args: any[]) {
      const msg = args[0]?.toString() || "";
      if (
        msg.includes(":first-child") ||
        msg.includes("pseudo class") ||
        msg.includes("potentially unsafe")
      ) {
        return;
      }
      originalWarn.apply(console, args);
    };
  }

  // 渲染 React 应用
  createRoot(document.getElementById("root")!).render(<App />);
}

// 启动初始化
initializeApp();
