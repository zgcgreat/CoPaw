import { useEffect, useState } from "react";
import { Modal, Button, Spin, Tag, Space, Typography, message } from "antd";
import {
  FileTextOutlined,
  RollbackOutlined,
  ArrowRightOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { dreamLogsApi } from "../../../../api/modules/dreamLogs";
import type { DreamLogRecord, DiffResponse } from "../../../../api/types/dreamLogs";
import styles from "../index.module.less";

const { Text } = Typography;

interface FileDiffModalProps {
  visible: boolean;
  record: DreamLogRecord | null;
  filename: string;
  onClose: () => void;
  onRollback: () => void;
}

export default function FileDiffModal({
  visible,
  record,
  filename,
  onClose,
  onRollback,
}: FileDiffModalProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [diffData, setDiffData] = useState<DiffResponse | null>(null);
  const [rolledBack, setRolledBack] = useState(false);

  useEffect(() => {
    if (visible && record && filename) {
      fetchDiff();
    }
  }, [visible, record, filename]);

  const fetchDiff = async () => {
    if (!record) return;
    setLoading(true);
    try {
      const data = await dreamLogsApi.diff(record.id, filename);
      setDiffData(data);
    } catch (error) {
      console.error("Failed to fetch diff:", error);
      message.error("Failed to load file comparison");
    } finally {
      setLoading(false);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const handleRollback = async () => {
    onRollback();
    setRolledBack(true);
  };

  if (!record) return null;

  const fileStats = record.file_stats[filename];
  const canRollback = record.status !== "rollback" && !rolledBack;

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      width={1000}
      footer={[
        <Button key="close" onClick={onClose}>
          {t("common.close")}
        </Button>,
        canRollback && (
          <Button
            key="rollback"
            type="primary"
            danger
            icon={<RollbackOutlined />}
            onClick={handleRollback}
          >
            {t("dreamLogs.rollback.single")}
          </Button>
        ),
      ]}
      title={
        <Space>
          <FileTextOutlined />
          {t("dreamLogs.diff.title")} - {filename}
        </Space>
      }
    >
      <Spin spinning={loading}>
        {diffData && (
          <>
            {/* File Stats Header */}
            <Space style={{ marginBottom: 16 }}>
              <Tag color="blue">
                {t("dreamLogs.file.sizeBefore")}: {formatSize(diffData.size_before)}
              </Tag>
              <ArrowRightOutlined />
              <Tag color="green">
                {t("dreamLogs.file.sizeAfter")}: {formatSize(diffData.size_after)}
              </Tag>
              {diffData.size_saved > 0 && (
                <Tag color="success">
                  {t("dreamLogs.file.sizeSaved")}: {formatSize(diffData.size_saved)}
                </Tag>
              )}
              {fileStats && (
                <Tag>
                  {t("dreamLogs.file.linesRemoved")}: {fileStats.lines_removed}
                </Tag>
              )}
            </Space>

            {/* Diff Panels */}
            <div className={styles.diffContainer}>
              {/* Before Panel */}
              <div className={styles.diffPanel}>
                <div className={styles.diffHeader}>
                  <Text strong>{t("dreamLogs.diff.before")}</Text>
                  <Text type="secondary">
                    {diffData.content_before.split("\n").length} lines
                  </Text>
                </div>
                <div
                  className={styles.diffContent}
                  style={{ background: "#ffebe9" }}
                >
                  {diffData.content_before || t("dreamLogs.diff.noChanges")}
                </div>
              </div>

              {/* After Panel */}
              <div className={styles.diffPanel}>
                <div className={styles.diffHeader}>
                  <Text strong>{t("dreamLogs.diff.after")}</Text>
                  <Text type="secondary">
                    {diffData.content_after.split("\n").length} lines
                  </Text>
                </div>
                <div
                  className={styles.diffContent}
                  style={{ background: "#e6ffed" }}
                >
                  {diffData.content_after || t("dreamLogs.diff.noChanges")}
                </div>
              </div>
            </div>
          </>
        )}
      </Spin>
    </Modal>
  );
}