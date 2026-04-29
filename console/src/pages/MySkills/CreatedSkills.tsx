import { List, Typography, Tag, Button, Space, Checkbox, Popconfirm } from "antd";
import { EditOutlined, DeleteOutlined, SyncOutlined, CheckCircleOutlined, StopOutlined } from "@ant-design/icons";
import { useState } from "react";
import { MySkill } from "../../api/modules/mySkills";
import { message } from "antd";

const { Text } = Typography;

interface CreatedSkillsProps {
  skills: MySkill[];
  sourceId: string;
  bbkId: string;
  userId: string;
  userName: string;
  isManager: boolean;
  onRefresh: () => void;
  onEdit?: (skill: MySkill) => void;
}

export function CreatedSkills({
  skills,
  sourceId,
  bbkId,
  userId,
  userName,
  isManager,
  onRefresh,
  onEdit,
}: CreatedSkillsProps) {
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set());
  const batchMode = selectedSkills.size > 0;

  const toggleSelect = (name: string) => {
    setSelectedSkills((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const selectAll = () => setSelectedSkills(new Set(skills.map((s) => s.skill_name)));

  const clearSelection = () => setSelectedSkills(new Set());

  const handleToggleEnabled = async (skill: MySkill) => {
    message.info(`启用/禁用功能开发中: ${skill.skill_name}`);
  };

  const handleDelete = async (skill: MySkill) => {
    message.info(`删除功能开发中: ${skill.skill_name}`);
  };

  const handleBatchDelete = async () => {
    message.info(`批量删除功能开发中: ${Array.from(selectedSkills).join(", ")}`);
    clearSelection();
  };

  const handleSyncToMarket = async (skill: MySkill) => {
    message.info(`同步到市场功能开发中: ${skill.skill_name}`);
  };

  return (
    <>
      {batchMode && (
        <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 16 }}>
          <Text>
            已选择 {selectedSkills.size} 个技能
          </Text>
          <Button size="small" onClick={selectAll}>
            全选
          </Button>
          <Button size="small" onClick={clearSelection}>
            清除选择
          </Button>
          <Popconfirm
            title="批量删除"
            description={`确定删除选中的 ${selectedSkills.size} 个技能吗？`}
            onConfirm={handleBatchDelete}
          >
            <Button danger size="small" icon={<DeleteOutlined />}>
              批量删除
            </Button>
          </Popconfirm>
        </div>
      )}
      <List
        dataSource={skills}
        renderItem={(skill) => (
          <List.Item
            actions={[
              <Checkbox
                checked={selectedSkills.has(skill.skill_name)}
                onChange={() => toggleSelect(skill.skill_name)}
              />,
              <Button
                type="link"
                size="small"
                icon={<CheckCircleOutlined />}
                onClick={() => handleToggleEnabled(skill)}
              >
                启用/禁用
              </Button>,
              onEdit && (
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => onEdit(skill)}
                >
                  编辑
                </Button>
              ),
              isManager && (
                <Button
                  type="link"
                  size="small"
                  icon={<SyncOutlined />}
                  onClick={() => handleSyncToMarket(skill)}
                >
                  同步到市场
                </Button>
              ),
              <Popconfirm
                title="删除技能"
                description={`确定删除技能「${skill.skill_name}」吗？`}
                onConfirm={() => handleDelete(skill)}
              >
                <Button
                  type="link"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                >
                  删除
                </Button>
              </Popconfirm>,
            ].filter(Boolean)}
          >
            <List.Item.Meta
              title={
                <Space>
                  <Text strong>{skill.skill_name}</Text>
                  {skill.version && <Tag color="blue">v{skill.version}</Tag>}
                  {skill.source === "customized" && <Tag color="green">自定义</Tag>}
                </Space>
              }
              description={skill.description || "暂无描述"}
            />
          </List.Item>
        )}
      />
    </>
  );
}
