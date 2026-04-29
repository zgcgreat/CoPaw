import { createGlobalStyle } from "antd-style";
import { ConfigProvider, bailianTheme } from "@agentscope-ai/design";
import { App as AntdApp } from "antd";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import zhCN from "antd/locale/zh_CN";
import enUS from "antd/locale/en_US";
import jaJP from "antd/locale/ja_JP";
import ruRU from "antd/locale/ru_RU";
import type { Locale } from "antd/es/locale";
import { theme as antdTheme } from "antd";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import "dayjs/locale/zh-cn";
import "dayjs/locale/ja";
import "dayjs/locale/ru";
dayjs.extend(relativeTime);
import MainLayout from "./layouts/MainLayout";
import { ThemeProvider, useTheme } from "./contexts/ThemeContext";
// ==================== 品牌主题 (Kun He) ====================
import {
  BrandThemeProvider,
  useBrandTheme,
} from "./contexts/BrandThemeContext";
// ==================== 品牌主题结束 ====================
import LoginPage from "./pages/Login";
import { authApi } from "./api/modules/auth";
import { languageApi } from "./api/modules/language";
import { getApiUrl, getApiToken, clearAuthToken } from "./api/config";
import { buildAuthHeaders } from "./api/authHeaders";
import "./styles/layout.css";
import "./styles/form-override.css";

const antdLocaleMap: Record<string, Locale> = {
  zh: zhCN,
  en: enUS,
  ja: jaJP,
  ru: ruRU,
};

const dayjsLocaleMap: Record<string, string> = {
  zh: "zh-cn",
  en: "en",
  ja: "ja",
  ru: "ru",
};

const GlobalStyle = createGlobalStyle`
* {
  margin: 0;
  box-sizing: border-box;
}
`;

function AuthGuard({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"loading" | "auth-required" | "ok">(
    "loading",
  );

  useEffect(() => {
    // Token is already initialized at App level, no need to wait here
    let cancelled = false;
    (async () => {
      try {
        const res = await authApi.getStatus();
        if (cancelled) return;
        if (!res.enabled) {
          setStatus("ok");
          return;
        }
        const token = getApiToken();
        if (!token) {
          setStatus("auth-required");
          return;
        }
        try {
          const r = await fetch(getApiUrl("/auth/verify"), {
            headers: {
              Authorization: `Bearer ${token}`,
              ...buildAuthHeaders(),
            },
          });
          if (cancelled) return;
          if (r.ok) {
            setStatus("ok");
          } else {
            clearAuthToken();
            setStatus("auth-required");
          }
        } catch {
          if (!cancelled) {
            clearAuthToken();
            setStatus("auth-required");
          }
        }
      } catch {
        if (!cancelled) setStatus("ok");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") return null;
  if (status === "auth-required")
    return (
      <Navigate
        to={`/login?redirect=${encodeURIComponent(window.location.pathname)}`}
        replace
      />
    );
  return <>{children}</>;
}

function getRouterBasename(pathname: string): string | undefined {
  return /^\/console(?:\/|$)/.test(pathname) ? "/console" : undefined;
}

function AppInner() {
  const basename = getRouterBasename(window.location.pathname);
  const { i18n } = useTranslation();
  const { isDark } = useTheme();

  // ==================== 品牌主题 (Kun He) ====================
  // 获取动态品牌配置，用于设置主题色
  const { theme: brandTheme } = useBrandTheme();
  // ==================== 品牌主题结束 ====================

  // ==================== 语言默认值调整 (Kun He) ====================
  // 将默认语言从 "en" 改为 "zh"（中文）
  // 同时将默认 locale 从 enUS 改为 zhCN
  const lang = i18n.resolvedLanguage || i18n.language || "zh";
  const [antdLocale, setAntdLocale] = useState<Locale>(
    antdLocaleMap[lang] ?? zhCN,
  );
  // ==================== 语言默认值调整结束 ====================

  useEffect(() => {
    // 如果 localStorage 中没有 language，先设置默认中文，再尝试从后端获取
    if (!localStorage.getItem("language")) {
      localStorage.setItem("language", "zh"); // 默认中文
      languageApi
        .getLanguage()
        .then(({ language }) => {
          if (language && language !== i18n.language) {
            i18n.changeLanguage(language);
            localStorage.setItem("language", language);
          }
        })
        .catch((err) =>
          console.error("Failed to fetch language preference:", err),
        );
    }
  }, []);

  useEffect(() => {
    // ==================== 语言默认值调整 (Kun He) ====================
    // 将语言回退默认值从 "en" 改为 "zh"/"zh-cn"
    const handleLanguageChanged = (lng: string) => {
      const shortLng = lng.split("-")[0];
      setAntdLocale(antdLocaleMap[shortLng] ?? zhCN);
      dayjs.locale(dayjsLocaleMap[shortLng] ?? "zh-cn");
    };

    // Set initial dayjs locale
    dayjs.locale(dayjsLocaleMap[lang.split("-")[0]] ?? "zh-cn");
    // ==================== 语言默认值调整结束 ====================

    i18n.on("languageChanged", handleLanguageChanged);
    return () => {
      i18n.off("languageChanged", handleLanguageChanged);
    };
  }, [i18n]);

  return (
    <BrowserRouter basename={basename}>
      <GlobalStyle />
      <ConfigProvider
        {...bailianTheme}
        prefix="swe"
        prefixCls="swe"
        locale={antdLocale}
        theme={{
          ...(bailianTheme as any)?.theme,
          algorithm: isDark
            ? antdTheme.darkAlgorithm
            : antdTheme.defaultAlgorithm,
          token: {
            // ==================== 品牌主题 (Kun He) ====================
            // 使用动态品牌主题色
            colorPrimary: brandTheme.primaryColor,
            // 确保浅色主题下 primary button 字体为白色
            colorTextOnPrimary: "#ffffff",
            // ==================== 品牌主题结束 ====================
          },
        }}
      >
        <AntdApp>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/*"
              element={
                <AuthGuard>
                  <MainLayout />
                </AuthGuard>
              }
            />
          </Routes>
        </AntdApp>
      </ConfigProvider>
    </BrowserRouter>
  );
}

function App() {
  // ==================== 外部系统 Token 针权 ====================
  // Token 已在 main.tsx 中获取完成，此处无需等待
  // ==================== 外部系统 Token 针权结束 ====================

  return (
    <ThemeProvider>
      {/* ==================== 品牌主题 (Kun He) ==================== */}
      {/* 包裹 BrandThemeProvider，根据 source 动态切换品牌配置 */}
      <BrandThemeProvider>
        <AppInner />
      </BrandThemeProvider>
      {/* ==================== 品牌主题结束 ==================== */}
    </ThemeProvider>
  );
}

export default App;
