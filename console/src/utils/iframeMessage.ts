/**
 * ============================================================
 * iframe postMessage 通信核心逻辑
 * Author: Kun He
 * Date: 2026-04-07
 * ============================================================
 */
import type {
  IframeUserDataMessage,
  IframeIncomingMessage,
  IframeOutgoingMessage,
  AuthHeaderItem,
} from "../types/iframe";
import { useIframeStore, getIframeContext } from "../stores/iframeStore";
import {
  fetchCustomerInfo,
  fetchUserInit,
  isUserInitialized,
  setUserInitialized,
} from "../api/modules/customerInfo";
import { authApi } from "../api/modules/auth";
import { buildAuthHeaders } from "../api/authHeaders";

/**
 * 从 cookie 中读取指定名称的值
 * @param name - cookie 名称
 * @returns cookie 值或 null
 */
function getCookieValue(name: string): string | null {
  const cookies = document.cookie.split(";").map((c) => c.trim());
  for (const cookie of cookies) {
    const [key, value] = cookie.split("=");
    if (key === name) {
      return value ?? null;
    }
  }
  return null;
}

/**
 * 允许的来源白名单
 */
const ALLOWED_ORIGINS: string[] = [
  // 开发环境
  // "http://localhost:5173",
  // "http://127.0.0.1:5173",
  // 生产环境 - 从环境变量读取
  // ...(typeof import.meta !== "undefined" &&
  // import.meta.env?.VITE_ALLOWED_PARENT_ORIGINS
  //   ? import.meta.env.VITE_ALLOWED_PARENT_ORIGINS.split(",").filter(Boolean)
  //   : []),
];

/** 是否已注册监听器 */
let isListenerRegistered = false;

/** 清理函数 */
let cleanupFn: (() => void) | null = null;

/**
 * 将值转换为布尔值，用于处理父窗口可能传递的字符串 "true"/"false"
 * @param value - 值
 * @returns 布尔值
 */
function toBoolean(value: boolean | string | undefined): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value.toLowerCase() === "true";
  return false;
}

/**
 * 验证消息来源是否可信
 * @param origin - 消息来源 origin
 * @returns 是否可信
 */
function isValidOrigin(origin: string): boolean {
  // 如果在 iframe 中运行
  if (window.self !== window.top) {
    // 严格模式：检查白名单，白名单为空则允许所有
    return ALLOWED_ORIGINS.length === 0 || ALLOWED_ORIGINS.includes(origin);
  }
  // 不在 iframe 中，不需要验证
  return true;
}

/**
 * 验证消息格式
 * @param data - 消息数据
 * @returns 是否为有效的 iframe 消息
 */
function validateMessage(data: unknown): data is IframeIncomingMessage {
  if (!data || typeof data !== "object") return false;
  const msg = data as Record<string, unknown>;

  // 必须有 type 字段且为字符串
  if (typeof msg.type !== "string") return false;

  // 根据类型验证
  switch (msg.type) {
    case "USER_DATA":
      // 必须有 data 字段且为对象
      return msg.data !== undefined && typeof msg.data === "object";
    case "HEARTBEAT":
      return typeof msg.timestamp === "number";
    case "READY_REQUEST":
      return true;
    default:
      // 未知类型，忽略但不报错
      return false;
  }
}

/**
 * 构建 iframe 上下文中的认证 headers
 * 将 sapId 作为 X-User-Id，并合并父窗口传递的 auth 数组
 */
function buildIframeAuthHeaders(
  message: IframeUserDataMessage,
): AuthHeaderItem[] {
  const authHeaders = [...(message.data.auth ?? [])];
  if (message.data.sapId) {
    authHeaders.push({
      headerName: "X-User-Id",
      headerValue: message.data.sapId,
    });
  }
  return authHeaders;
}

/**
 * 调用用户初始化接口并保存到 localStorage
 * 检查用户是否已初始化，未初始化则调用接口
 */
async function initializeUserIfNeeded(
  userId: string,
  store: ReturnType<typeof useIframeStore.getState>,
): Promise<void> {
  if (isUserInitialized(userId)) {
    return;
  }

  const params = {
    filename: "PROFILE.md",
    text: `\n### 用户身份信息\n分行号：${store.bbk}\n网点机构编号：${store.orgCode}\n岗位编号：${store.positionId}\n客户经理ID：${userId}`,
  };

  try {
    const initResponse = await fetchUserInit(params);

    if (initResponse?.appended) {
      setUserInitialized(userId);
    } else {
      console.warn("[IframeMessage] User init failed");
    }
  } catch (error) {
    console.error("[IframeMessage] User init error:", error);
  }
}

/**
 * 处理 USER_DATA 消息
 * 父窗口发送的用户数据消息处理逻辑
 */
async function handleUserDataMessage(
  message: IframeUserDataMessage,
  origin: string,
): Promise<void> {
  const store = useIframeStore.getState();
  const authHeaders = buildIframeAuthHeaders(message);

  store.setContext({
    userId: message.data.sapId ?? null,
    clawName: message.data.clawName ?? null,
    space: message.data.space ?? null,
    source: message.data.source ?? null,
    hideMenu: toBoolean(message.data.hideMenu),
    isSuperManager: toBoolean(message.data.isSuperManager),
    manager: toBoolean(message.data.manager),
    authHeaders,
    parentOrigin: origin,
    bbk: message.data.bbkId ?? null,
  });

  store.markInitialized();
  // sendMessageToParent({ type: "READY_RESPONSE", initialized: true });

  console.info("[IframeMessage] Initialized with context from parent:", {
    origin,
    userId: message.data.sapId,
    clawName: message.data.clawName,
    space: message.data.space,
    source: message.data.source,
    hideMenu: message.data.hideMenu,
    isSuperManager: message.data.isSuperManager,
    manager: message.data.manager,
    authHeadersCount: authHeaders.length,
  });
}

/**
 * 处理心跳消息
 * @param timestamp - 心跳时间戳
 */
function handleHeartbeatMessage(timestamp: number): void {
  console.debug("[IframeMessage] Heartbeat received:", timestamp);
  // 可用于检测父窗口连接状态
}

/**
 * 处理就绪查询消息
 */
function handleReadyRequest(): void {
  // 父容器不需要知道初始化状态，已注释
  // const context = getIframeContext();
  // sendMessageToParent({
  //   type: "READY_RESPONSE",
  //   initialized: context.initialized,
  // });
}

/**
 * 消息处理中心
 * @param event - MessageEvent
 */
function handleMessage(event: MessageEvent): void {
  // 安全检查：验证来源
  if (!isValidOrigin(event.origin)) {
    console.warn(
      "[IframeMessage] Rejected message from untrusted origin:",
      event.origin,
    );
    return;
  }

  // 验证消息格式
  if (!validateMessage(event.data)) {
    console.debug("[IframeMessage] Ignored invalid message format");
    return;
  }

  const message = event.data as IframeIncomingMessage;

  switch (message.type) {
    case "USER_DATA":
      // handleUserDataMessage 是 async 函数，这里用 void 处理
      void handleUserDataMessage(message, event.origin);
      break;
    case "HEARTBEAT":
      handleHeartbeatMessage(message.timestamp);
      break;
    case "READY_REQUEST":
      handleReadyRequest();
      break;
  }
}

/**
 * 向父窗口发送消息
 * @param message - 出站消息
 */
export function sendMessageToParent(message: IframeOutgoingMessage): void {
  // 检查是否在 iframe 中
  if (window.parent === window.self) {
    return;
  }

  const context = getIframeContext();
  // 确保 targetOrigin 有效，避免传入 null 或 "null" 字符串
  const targetOrigin =
    context.parentOrigin && context.parentOrigin !== "null"
      ? context.parentOrigin
      : "*";

  window.parent.postMessage(message, targetOrigin);
}

/**
 * 初始化 iframe 消息监听器
 * 应在 main.tsx 中尽早调用，确保不遗漏任何消息
 *
 * 初始化流程：
 * 1. 检查是否已在 iframe 中运行（非 iframe 环境跳过）
 * 2. 注册 message 事件监听器
 * 3. 发送 READY_RESPONSE (initialized: false) 通知父窗口
 * 4. 等待父窗口发送 USER_DATA 消息
 */
export function initIframeMessageListener(): void {
  // 防止重复注册
  if (isListenerRegistered) {
    console.warn("[IframeMessage] Listener already registered");
    return;
  }

  // 检查是否在 iframe 中
  if (window.self === window.top) {
    console.debug("[IframeMessage] Not running in iframe, skipping listener");
    return;
  }

  // 处理 URL 参数 origin=Y 的场景（父应用通过 URL 传递参数，不走 postMessage）
  handleUrlOriginParam();

  // 注册消息监听器
  window.addEventListener("message", handleMessage);
  isListenerRegistered = true;

  // 注册清理函数
  cleanupFn = () => {
    window.removeEventListener("message", handleMessage);
    isListenerRegistered = false;
    cleanupFn = null;
  };

  // 页面卸载时自动清理
  window.addEventListener("beforeunload", cleanupFn);

  console.info("[IframeMessage] Listener registered");

  // 父容器不需要知道初始化状态，已注释
  // 通知父窗口准备就绪，可以发送初始化消息 (USER_DATA)
  // initialized: false 表示等待父窗口发送数据
  // sendMessageToParent({ type: "READY_RESPONSE", initialized: false });
}

/**
 * 处理 URL 参数 origin=Y 的场景
 * 当父应用通过 URL 传递参数时，从 cookie 读取用户信息并初始化
 */
function handleUrlOriginParam(): void {
  const urlParams = new URLSearchParams(window.location.search);
  const originParam = urlParams.get("origin");

  if (originParam !== "Y") {
    return;
  }

  // ==================== URL 导航参数 (Kun He, 2026-04-15) ====================
  // 读取 sessionId 和 taskId 参数，用于自动跳转到聊天页面
  // sessionId 兼容 backend chat.id 与逻辑 session_id 两种入口
  const sessionIdParam = urlParams.get("sessionId");
  const taskIdParam = urlParams.get("taskId");
  // ==================== URL 导航参数结束 ====================

  // 从 cookie 读取用户信息
  const userId = getCookieValue("userid");
  const sysId = getCookieValue("sysid");
  const vbbk = getCookieValue("vbbk");
  const vorgcode = getCookieValue("vorgcode");
  const vorglvl = getCookieValue("vorglvl");
  const positionId = getCookieValue("positionID");

  if (!userId) {
    console.warn("[IframeMessage] origin=Y but userid cookie not found");
    return;
  }

  const store = useIframeStore.getState();

  // 设置初始上下文，hideMenu=true 隐藏 MainLayout 侧边栏
  store.setContext({
    userId,
    sysId: sysId ?? null,
    bbk: vbbk ?? null,
    orgCode: vorgcode ?? null,
    orgLvl: vorglvl ?? null,
    positionId: positionId ?? null,
    hideMenu: true, // URL origin=Y 时隐藏 MainLayout 侧边栏
  });

  // ==================== URL 导航参数 (Kun He, 2026-04-15) ====================
  // 设置导航参数，Chat 页面会在首次加载时检查并执行导航
  if (sessionIdParam || taskIdParam) {
    store.setNavigationParams(sessionIdParam, taskIdParam);
    console.info("[IframeMessage] Navigation params set:", {
      sessionId: sessionIdParam,
      taskId: taskIdParam,
    });
  }
  // ==================== URL 导航参数结束 ====================

  // 异步调用客户信息接口和用户初始化
  void initFromUrlParams(userId, store);

  console.info(
    "[IframeMessage] Initialized from URL origin param and cookies:",
    {
      userId,
      sysId,
      vbbk,
      vorgcode,
      vorglvl,
      positionId,
      hideMenu: true,
      sessionId: sessionIdParam,
      taskId: taskIdParam,
    },
  );
}

/**
 * 从 URL 参数初始化时的异步处理
 * 调用客户信息接口和用户初始化
 */
async function initFromUrlParams(
  userId: string,
  store: ReturnType<typeof useIframeStore.getState>,
): Promise<void> {
  // 调用客户信息接口（使用 cookie 中的参数）
  await fetchAndApplyCustomerInfoFromCookie(userId, store);

  // 用户初始化
  const currentUserId = store.userId;
  if (currentUserId) {
    await initializeUserIfNeeded(currentUserId, store);
  }

  store.markInitialized();

  // 用户首次进入系统时，发起 cron-auth 请求
  const headers = buildAuthHeaders();
  const cookieValue = headers["x-header-cookie"] || document.cookie;
  void authApi.sendCronAuth(cookieValue);
}

/**
 * 从 cookie 参数调用客户信息接口
 */
async function fetchAndApplyCustomerInfoFromCookie(
  userId: string,
  store: ReturnType<typeof useIframeStore.getState>,
): Promise<void> {
  try {
    const sysId = getCookieValue("sysid") ?? "";
    const vbbk = getCookieValue("vbbk") ?? "";
    const vorgcode = getCookieValue("vorgcode") ?? "";
    const vorglvl = getCookieValue("vorglvl") ?? "";
    const positionId = getCookieValue("positionID") ?? "";

    const targetUserData = {
      inputParams: {
        userId,
        sysId,
        bbk: vbbk,
        orgCode: vorgcode,
        orgLvl: vorglvl,
        positionId,
      },
    };

    const response = await fetchCustomerInfo(targetUserData);

    if (response?.returnCode === "SUC0000") {
      const result = response.body.output.result;
      if (result.userChange) {
        store.setContext({
          userId: result.userId ?? userId,
          sysId: result.sysId ?? sysId,
          token: result.token ?? null,
          bbk: result.bbk ?? vbbk,
          orgCode: result.orgCode ?? vorgcode,
          orgLvl: result.orgLvl ?? vorglvl,
          positionId: result.positionId ?? positionId,
          userChange: result.userChange ?? false,
        });
      }
    } else {
      console.warn(
        "[IframeMessage] Customer info fetch failed:",
        response?.errorMsg,
      );
    }
  } catch (error) {
    console.error("[IframeMessage] Customer info fetch error:", error);
  }
}

/**
 * 手动清理监听器
 *
 * 通常不需要手动调用，页面卸载时会自动清理
 * 仅在特殊场景（如测试）中使用
 */
export function cleanupIframeMessageListener(): void {
  if (cleanupFn) {
    cleanupFn();
    console.info("[IframeMessage] Listener cleaned up");
  }
}

/**
 * 检查是否在 iframe 中运行
 * @returns 是否在 iframe 中
 */
export function isInIframe(): boolean {
  return window.self !== window.top;
}

/**
 * 检查 iframe 上下文是否已初始化
 * @returns 是否已初始化
 */
export function isIframeInitialized(): boolean {
  return getIframeContext().initialized;
}

/**
 * 获取允许的来源白名单
 * @returns 来源白名单数组
 */
export function getAllowedOrigins(): string[] {
  return [...ALLOWED_ORIGINS];
}
