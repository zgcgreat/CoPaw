import React, { useState, useCallback, useRef, useEffect } from "react";
import { Input, Upload } from "antd";
import { SparkAttachmentLine } from "@agentscope-ai/icons";
import { IconButton } from "@agentscope-ai/design";
import { Tooltip } from "antd";
import Style from "./style";
import KnowledgeTabs from "../KnowledgeTabs";
import FeaturedCases from "../FeaturedCases";
import CaseDetailDrawer from "../CaseDetailDrawer";
import { featuredCasesApi } from "@/api/modules/featuredCases";
import type { FeaturedCase } from "@/api/types/featuredCases";
import type { GreetingDisplay } from "@/api/types/greeting";
import sendIcon from '../../../assets/icons/send_highlight.svg'

interface WelcomeCenterLayoutProps {
  greeting?: string;
  onSubmit: (data: { query: string }) => void;
}

export default function WelcomeCenterLayout(props: WelcomeCenterLayoutProps) {
  const { greeting, onSubmit } = props;
  const [inputValue, setInputValue] = useState("");
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedCase, setSelectedCase] = useState<FeaturedCase | null>(null);
  const [randomPlaceholder, setRandomPlaceholder] = useState('');
  const [loadingCase, setLoadingCase] = useState(false);
  const uploadRef = useRef<any>(null);
  // 随机placeholder文案数组
  const placeholderOptions = [
    '告诉我你要做什么，我将召唤对应专家，为你执行...',
    '有什么要求都告诉我，我会越用越懂你...',
    '你可以给我取个名字，甚至设定我的人设...'
  ];

  // 组件挂载时随机选择placeholder文案
  useEffect(() => {
    const randomIndex = Math.floor(Math.random() * placeholderOptions.length);
    setRandomPlaceholder(placeholderOptions[randomIndex]);
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    onSubmit({ query: trimmed });
    setInputValue("");
  }, [inputValue, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleFillInput = useCallback((text: string) => {
    setInputValue(text);
  }, []);

  // Handle "看案例" click - fetch detail from API
  const handleViewCase = useCallback(async (id: number) => {
    setLoadingCase(true);
    setDrawerVisible(true);
    setSelectedCase(null); // Clear previous case

    try {
      const caseData = await featuredCasesApi.getCaseDetail(id);
      setSelectedCase(caseData);
    } catch (error) {
      console.error("Failed to load case detail:", error);
      // Close drawer on error
      setDrawerVisible(false);
    } finally {
      setLoadingCase(false);
    }
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setDrawerVisible(false);
    setSelectedCase(null);
  }, []);

  return (
    <>
      <Style />
      <div className="welcome-center-layout">
        {/* Greeting */}
        <div className="welcome-greeting">{greeting}</div>

        {/* Input Card */}
        <div className="welcome-input-card">
          <Input.TextArea
            className="welcome-input-placeholder"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={randomPlaceholder}
            autoSize={{ minRows: 1, maxRows: 5 }}
            bordered={false}
          />
          <div className="welcome-input-actions">
            <div className="welcome-input-actions-left">
              <Tooltip title="上传附件">
                <div>
                  <Upload
                    ref={uploadRef}
                    showUploadList={false}
                    accept="*/*"
                    beforeUpload={(file) => {
                      document.dispatchEvent(
                        new CustomEvent("pasteFile", {
                          detail: { file },
                        }),
                      );
                      return false;
                    }}
                  >
                    <IconButton
                      icon={<SparkAttachmentLine />}
                      bordered={false}
                    />
                  </Upload>
                </div>
              </Tooltip>
            </div>
            <button
              className="welcome-input-send-btn"
              onClick={handleSend}
              disabled={!inputValue.trim()}
              type="button"
            >
              <img src={sendIcon} alt="发送" width={28} height={28} />
            </button>
          </div>
        </div>

        {/* Knowledge Tabs */}
        {/* <div className="welcome-tabs-area">
          <KnowledgeTabs />
        </div> */}

        {/* Featured Cases */}
        <div className="welcome-cases-area">
          <FeaturedCases
            onFillInput={handleFillInput}
            onViewCase={handleViewCase}
          />
        </div>
      </div>

      {/* Case Detail Drawer */}
      <CaseDetailDrawer
        visible={drawerVisible}
        onClose={handleCloseDrawer}
        caseData={selectedCase}
        loading={loadingCase}
        onMakeSimilar={(value) => {
          setInputValue(value);
          handleCloseDrawer();
        }}
      />
    </>
  );
}