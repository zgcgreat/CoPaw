import { useEffect, useState, useRef } from "react";
import { Typography, Tree, Card, Spin, Button, Space, Input, message } from "antd";
import { PlusOutlined, UploadOutlined, ReloadOutlined } from "@ant-design/icons";
import { CreatedSkills } from "./CreatedSkills";
import { ReceivedSkills } from "./ReceivedSkills";
import { useMySkills } from "./useMySkills";
import { useIframeStore } from "../../stores/iframeStore";
import { getUserId } from "../../utils/identity";
import { DEFAULT_SOURCE_ID } from "../../constants/identity";

const { Title } = Typography;
const { Search } = Input;

type TabKey = "created" | "received";

export default function MySkillsPage() {
  const sourceId = useIframeStore((state) => state.source) || DEFAULT_SOURCE_ID;
  const bbkId = useIframeStore((state) => state.bbk) || "100";
  const isManager = useIframeStore((state) => state.manager) || false;
  const userId = getUserId();
  const { createdSkills, receivedSkills, loading, refresh } = useMySkills(sourceId, userId);
  const [selectedTab, setSelectedTab] = useState<TabKey>("created");
  const [searchText, setSearchText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreateNew = () => {
    message.info("创建新技能功能开发中");
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    message.info(`上传功能开发中: ${file.name}`);
    e.target.value = "";
  };

  const treeData = [
    { key: "created", title: `我创建的 (${createdSkills.length})` },
    { key: "received", title: `我接收的 (${receivedSkills.length})` },
  ];

  const filteredCreatedSkills = createdSkills.filter((s) =>
    s.skill_name.toLowerCase().includes(searchText.toLowerCase())
  );

  const filteredReceivedSkills = receivedSkills.filter((s) =>
    s.skill_name.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{ width: 200, borderRight: "1px solid #f0f0f0", padding: 16 }}>
        <Tree
          treeData={treeData}
          selectedKeys={[selectedTab]}
          onSelect={(keys) => setSelectedTab(keys[0] as TabKey)}
        />
      </div>
      <div style={{ flex: 1, padding: 16, overflow: "auto" }}>
        <Card>
          {loading ? (
            <Spin />
          ) : selectedTab === "created" ? (
            <>
              <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Title level={4} style={{ margin: 0 }}>我创建的技能</Title>
                <Space>
                  <Search
                    placeholder="搜索技能"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    style={{ width: 200 }}
                    allowClear
                  />
                  <Button icon={<ReloadOutlined />} onClick={refresh}>
                    刷新
                  </Button>
                  <Button icon={<UploadOutlined />} onClick={handleUploadClick}>
                    上传 ZIP
                  </Button>
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateNew}>
                    创建新技能
                  </Button>
                </Space>
              </div>
              <CreatedSkills
                skills={filteredCreatedSkills}
                sourceId={sourceId}
                bbkId={bbkId}
                userId={userId}
                userName=""
                isManager={isManager}
                onRefresh={refresh}
              />
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                style={{ display: "none" }}
                onChange={handleFileSelect}
              />
            </>
          ) : (
            <>
              <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Title level={4} style={{ margin: 0 }}>我接收的技能</Title>
                <Space>
                  <Search
                    placeholder="搜索技能"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    style={{ width: 200 }}
                    allowClear
                  />
                  <Button icon={<ReloadOutlined />} onClick={refresh}>
                    刷新
                  </Button>
                </Space>
              </div>
              <ReceivedSkills skills={filteredReceivedSkills} />
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
