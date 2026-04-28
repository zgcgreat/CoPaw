import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Card,
  Table,
  Button,
  Space,
  Modal,
  message,
  Spin,
  Empty,
  Statistic,
  Row,
  Col,
  Tag,
  Popconfirm,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  DeleteOutlined,
  DeleteFilled,
  DatabaseOutlined,
  FileOutlined,
  ReloadOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { dreamLogsApi } from "../../../../api/modules/dreamLogs";
import type { BackupFileInfo, BackupListResponse, BackupContentResponse } from "../../../../api/types/dreamLogs";
import styles from "../index.module.less";

const { Text } = Typography;

export default function BackupFilesPage() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [backups, setBackups] = useState<BackupListResponse | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewContent, setPreviewContent] = useState<BackupContentResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    fetchBackups();
  }, []);

  const fetchBackups = async () => {
    setLoading(true);
    try {
      const data = await dreamLogsApi.listBackups();
      setBackups(data);
    } catch (error) {
      console.error("Failed to fetch backups:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteFile = async (filename: string) => {
    try {
      const result = await dreamLogsApi.deleteBackup(filename);
      if (result.success) {
        message.success(t("dreamLogs.backup.deleteSuccess"));
        fetchBackups();
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error(t("dreamLogs.backup.deleteFailed"));
    }
  };

  const handleDeleteAll = async () => {
    Modal.confirm({
      title: t("dreamLogs.backup.deleteAllConfirm"),
      content: t("dreamLogs.backup.deleteAllMessage"),
      onOk: async () => {
        try {
          const result = await dreamLogsApi.deleteAllBackups();
          if (result.success) {
            message.success(t("dreamLogs.backup.deleteAllSuccess"));
            fetchBackups();
          } else {
            message.error(result.message);
          }
        } catch (error) {
          message.error(t("dreamLogs.backup.deleteFailed"));
        }
      },
    });
  };

  const handlePreview = async (filename: string) => {
    setPreviewVisible(true);
    setPreviewLoading(true);
    try {
      const content = await dreamLogsApi.getBackupContent(filename);
      setPreviewContent(content);
    } catch (error) {
      message.error(t("dreamLogs.backup.previewFailed"));
      setPreviewVisible(false);
    } finally {
      setPreviewLoading(false);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)}MB`;
  };

  const columns: ColumnsType<BackupFileInfo> = [
    {
      title: t("dreamLogs.backup.filename"),
      dataIndex: "filename",
      key: "filename",
      width: 250,
      render: (value: string) => <Tag icon={<FileOutlined />}>{value}</Tag>,
    },
    {
      title: t("dreamLogs.backup.originalFile"),
      dataIndex: "original_file",
      key: "original_file",
      width: 150,
    },
    {
      title: t("dreamLogs.backup.recordId"),
      dataIndex: "record_id",
      key: "record_id",
      width: 180,
      render: (value: string) => value || "-",
    },
    {
      title: t("dreamLogs.backup.timestamp"),
      dataIndex: "timestamp",
      key: "timestamp",
      width: 180,
      render: (value: string) =>
        value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-",
    },
    {
      title: t("dreamLogs.backup.size"),
      dataIndex: "size",
      key: "size",
      width: 100,
      render: (value: number) => formatSize(value),
    },
    {
      title: t("dreamLogs.backup.createdAt"),
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value: string) => dayjs(value).format("YYYY-MM-DD HH:mm:ss"),
    },
    {
      title: t("common.actions"),
      key: "actions",
      width: 100,
      fixed: "right",
      render: (_, record) => (
        <Space>
          <Button
            type="text"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handlePreview(record.filename)}
          />
          <Popconfirm
            title={t("dreamLogs.backup.deleteConfirm")}
            onConfirm={() => handleDeleteFile(record.filename)}
          >
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      {backups && (
        <Row gutter={16} className={styles.statsRow}>
          <Col span={8}>
            <Card className={styles.statsCard}>
              <Statistic
                title={t("dreamLogs.backup.totalFiles")}
                value={backups.total_files}
                prefix={<FileOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card className={styles.statsCard}>
              <Statistic
                title={t("dreamLogs.backup.totalSize")}
                value={formatSize(backups.total_size)}
                prefix={<DatabaseOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card className={styles.statsCard}>
              <Button
                type="primary"
                danger
                icon={<DeleteFilled />}
                onClick={handleDeleteAll}
                disabled={backups.total_files === 0}
                block
              >
                {t("dreamLogs.backup.deleteAll")}
              </Button>
            </Card>
          </Col>
        </Row>
      )}

      <Card
        title={t("dreamLogs.backup.title")}
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchBackups}
          >
            {t("common.refresh")}
          </Button>
        }
      >
        <Spin spinning={loading}>
          {!backups || backups.files.length === 0 ? (
            <Empty
              description={t("dreamLogs.backup.noFiles")}
              style={{ padding: 40 }}
            />
          ) : (
            <Table
              columns={columns}
              dataSource={backups.files}
              rowKey="filename"
              pagination={false}
              scroll={{ x: 1000 }}
            />
          )}
        </Spin>
      </Card>

      <Modal
        title={
          <Space>
            <FileOutlined />
            {t("dreamLogs.backup.previewTitle")}
            {previewContent && (
              <Text type="secondary">
                ({previewContent.original_file})
              </Text>
            )}
          </Space>
        }
        open={previewVisible}
        onCancel={() => setPreviewVisible(false)}
        footer={null}
        width={800}
      >
        <Spin spinning={previewLoading}>
          {previewContent && (
            <div style={{ maxHeight: 500, overflow: "auto" }}>
              <Space direction="vertical" style={{ width: "100%" }} size="small">
                <Text type="secondary">
                  {t("dreamLogs.backup.filename")}: {previewContent.filename} |
                  {t("dreamLogs.backup.size")}: {formatSize(previewContent.size)}
                </Text>
              </Space>
              <div className={styles.markdownContent} style={{ marginTop: 12, padding: 12, background: "#f5f5f5", borderRadius: 4 }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {previewContent.content}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </Spin>
      </Modal>
    </div>
  );
}