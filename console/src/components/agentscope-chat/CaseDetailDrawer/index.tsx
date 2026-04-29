import { useState } from "react";
import { Drawer, Spin } from "antd";
import Style from "./style";
import type { FeaturedCase, CaseDetail, CaseStep } from "@/api/types/featuredCases";
import ScheduledTaskPopup from "@/components/ScheduledTaskPopup";
import { cronJobApi } from "@/api/modules/cronjob";
import { getUserId, getChannel } from "@/utils/identity";
import { buildCronJobSpec, generateCronExpression, type ScheduleConfig } from "@/utils/cron";

export interface CaseDetailDrawerProps {
  visible: boolean;
  onClose: () => void;
  caseData: FeaturedCase | null;
  loading?: boolean;
  onMakeSimilar?: (value: string) => void;
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path
        d="M1 1L13 13M13 1L1 13"
        stroke="#999999"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SubscribeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M8 4.5V8.5L10.5 10"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function NewSessionIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M8 3V13M3 8H13"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M2 8C2 4.68629 4.68629 2 8 2C11.3137 2 14 4.68629 14 8C14 11.3137 11.3137 14 8 14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M14 2L14 5.5L10.5 5.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function normalizeUrl(url: string): string {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  return `https://${url}`;
}

export default function CaseDetailDrawer({
  visible,
  onClose,
  caseData,
  loading = false,
  onMakeSimilar,
}: CaseDetailDrawerProps) {
  const [iframeLoading, setIframeLoading] = useState(true);
  const [iframeError, setIframeError] = useState(false);
  const [scheduledPopupVisible, setScheduledPopupVisible] = useState(false);

  const handleMakeSimilar = () => {
    if (caseData) {
      onMakeSimilar?.(caseData.value);
    }
    onClose();
  };

  const handleOpenScheduledPopup = () => {
    setScheduledPopupVisible(true);
  };

  const handleCloseScheduledPopup = () => {
    setScheduledPopupVisible(false);
  };

  const handleTaskCreatedSuccess = () => {
    // 关闭 CaseDetailDrawer
    onClose();
  };

  const handleConfirmScheduledTask = async (
    cronExpression: string,
    config: ScheduleConfig
  ) => {
    if (!caseData) return;

    const userId = getUserId();
    const channel = getChannel();

    const spec = buildCronJobSpec({
      cronExpression,
      name: caseData.label || "定时任务",
      userId,
      sessionId: undefined,
      caseValue: caseData.value,
      channel,
    });

    await cronJobApi.createCronJob(spec);

    // 通知 Chat 页面刷新任务列表
    document.dispatchEvent(new CustomEvent("taskCreated"));
  };

  const handleIframeLoad = () => {
    setIframeLoading(false);
    setIframeError(false);
  };

  const handleIframeError = () => {
    setIframeLoading(false);
    setIframeError(true);
  };

  const handleRefreshIframe = () => {
    setIframeLoading(true);
    setIframeError(false);
    // Force iframe reload by resetting src
    const iframe = document.querySelector(
      ".case-detail-drawer-iframe",
    ) as HTMLIFrameElement;
    if (iframe && caseData?.iframe_url) {
      iframe.src = normalizeUrl(caseData.iframe_url);
    }
  };

  const steps: CaseStep[] = caseData?.steps || [];
  const iframeUrl = normalizeUrl(caseData?.iframe_url || "");
  const iframeTitle = caseData?.iframe_title || "详情";

  return (
    <>
      <Style />
      <Drawer
        className="case-detail-drawer"
        placement="bottom"
        open={visible}
        onClose={onClose}
        height="90%"
        closable={false}
        maskClosable
        styles={{
          body: { padding: 0, overflow: "hidden" },
        }}
      >
        {/* Header */}
        <div className="case-detail-drawer-header">
          <span className="case-detail-drawer-title">
            {loading ? "加载中..." : caseData?.label || "案例详情"}
          </span>
          <button
            className="case-detail-drawer-close"
            onClick={onClose}
            type="button"
          >
            <CloseIcon />
          </button>
        </div>

        {/* Body - Left/Right split */}
        {loading ? (
          <div className="case-detail-drawer-loading-body">
            <Spin size="large" />
          </div>
        ) : (
          <div className="case-detail-drawer-body">
            {/* Left: Steps */}
            <div className="case-detail-drawer-steps-panel">
              {steps.length === 0 ? (
                <div className="case-detail-drawer-empty">
                  暂无步骤说明
                </div>
              ) : (
                steps.map((step, i) => (
                  <div key={i} className="case-detail-drawer-step">
                    <div className="case-detail-drawer-step-title">
                      {step.title}
                    </div>
                    <div className="case-detail-drawer-step-content">
                      {step.content}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Right: iframe - only show when iframeUrl exists */}
            {iframeUrl && (
              <div className="case-detail-drawer-iframe-panel">
                <div className="case-detail-drawer-iframe-title">
                  {iframeTitle}
                </div>
                <div className="case-detail-drawer-iframe-container">
                  {iframeLoading && !iframeError && (
                    <div className="case-detail-drawer-iframe-loading">
                      <Spin />
                      <span>加载中...</span>
                    </div>
                  )}
                  {iframeError && (
                    <div className="case-detail-drawer-iframe-error">
                      <span>页面加载失败</span>
                      <button
                        className="case-detail-drawer-iframe-refresh"
                        onClick={handleRefreshIframe}
                        type="button"
                      >
                        <RefreshIcon />
                        重新加载
                      </button>
                    </div>
                  )}
                  <iframe
                    className="case-detail-drawer-iframe"
                    src={iframeUrl}
                    title={iframeTitle}
                    sandbox="allow-scripts allow-same-origin allow-forms"
                    onLoad={handleIframeLoad}
                    onError={handleIframeError}
                    loading="lazy"
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="case-detail-drawer-footer">
          <button
            className="case-detail-drawer-footer-btn"
            type="button"
            onClick={handleOpenScheduledPopup}
          >
            <SubscribeIcon />
            订阅为定时任务
          </button>
          <button
            className="case-detail-drawer-footer-btn case-detail-drawer-footer-btn--primary"
            type="button"
            onClick={handleMakeSimilar}
            disabled={!caseData}
          >
            <NewSessionIcon />
            做同款
          </button>
        </div>
      </Drawer>
      <ScheduledTaskPopup
        open={scheduledPopupVisible}
        onClose={handleCloseScheduledPopup}
        onConfirm={handleConfirmScheduledTask}
        onSuccess={handleTaskCreatedSuccess}
        caseValue={caseData?.value}
      />
    </>
  );
}