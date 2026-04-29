import { List, Typography, Tag, Button, Space, Checkbox, Popconfirm, message } from "antd";
import { SyncOutlined, CheckCircleOutlined, DeleteOutlined } from "@ant-design/icons";
import { useState } from "react";
import { MySkill } from "../../api/modules/mySkills";

const { Text } = Typography;

interface ReceivedSkillsProps {
  skills: MySkill[];
  onUpdate?: (skill: MySkill) => void;
}

export function ReceivedSkills({ skills, onUpdate }: ReceivedSkillsProps) {
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

  const handleUpdate = async (skill: MySkill) => {
    message.info(`更新功能开发中: ${skill.skill_name}`);
  };

  const handleDelete = async (skill: MySkill) => {
    message.info(`删除功能开发中: ${skill.skill_name}`);
  };

  const handleBatchDelete = async () => {
    message.info(`批量删除功能开发中: ${Array.from(selectedSkills).join(", ")}`);
    clearSelection();
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
              skill.has_update && (
                <Button
                  type="link"
                  size="small"
                  icon={<SyncOutlined />}
                  onClick={() => handleUpdate(skill)}
                >
                  更新
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
                  {skill.received_version && <Tag color="green">v{skill.received_version}</Tag>}
                  {skill.has_update && <Tag color="orange">有更新</Tag>}
                </Space>
              }
              description={
                <Space direction="vertical" size={0}>
                  <Text type="secondary">{skill.description || "暂无描述"}</Text>
                  {skill.distributed_by && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      分发人: {skill.distributed_by}
                    </Text>
                  )}
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </>
  );
}
