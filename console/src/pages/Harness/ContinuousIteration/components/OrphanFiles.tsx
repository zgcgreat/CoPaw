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
  Alert,
  Image,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  DeleteOutlined,
  FileOutlined,
  ReloadOutlined,
  EyeOutlined,
  FolderOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { dreamLogsApi } from "../../../../api/modules/dreamLogs";
import type {
  OrphanFileInfo,
  OrphanFilesResponse,
  OrphanFileContentResponse,
} from "../../../../api/types/dreamLogs";
import styles from "../index.module.less";

const { Text } = Typography;

export default function OrphanFilesPage() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [orphanFiles, setOrphanFiles] = useState<OrphanFilesResponse | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewContent, setPreviewContent] = useState<OrphanFileContentResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    fetchOrphanFiles();
  }, []);

  const fetchOrphanFiles = async () => {
    setLoading(true);
    try {
      const data = await dreamLogsApi.listOrphanFiles();
      setOrphanFiles(data);
    } catch (error) {
      console.error("Failed to fetch orphan files:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteFile = async (filepath: string) => {
    try {
      const result = await dreamLogsApi.deleteOrphanFile(filepath);
      if (result.success) {
        message.success(t("dreamLogs.orphanFiles.deleteSuccess"));
        fetchOrphanFiles();
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error(t("dreamLogs.orphanFiles.deleteFailed"));
    }
  };

  const handlePreview = async (filepath: string) => {
    setPreviewVisible(true);
    setPreviewLoading(true);
    setPreviewContent(null);
    try {
      const content = await dreamLogsApi.getOrphanFileContent(filepath);
      setPreviewContent(content);
    } catch (error) {
      // Keep modal open and show error
      setPreviewContent({
        filename: filepath,
        content: "",
        size: 0,
        file_type: "error",
        is_loadable: false,
        error_message: t("dreamLogs.orphanFiles.previewFailed"),
      });
    } finally {
      setPreviewLoading(false);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)}MB`;
  };

  const columns: ColumnsType<OrphanFileInfo> = [
    {
      title: t("dreamLogs.orphanFiles.filePath"),
      dataIndex: "path",
      key: "path",
      width: 350,
      render: (value: string) => (
        <Text copyable style={{ fontSize: 12 }}>
          {value}
        </Text>
      ),
    },
    {
      title: t("dreamLogs.orphanFiles.size"),
      dataIndex: "size",
      key: "size",
      width: 100,
      render: (value: number) => formatSize(value),
    },
    {
      title: t("dreamLogs.orphanFiles.createdAt"),
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value: string) => dayjs(value).format("YYYY-MM-DD HH:mm:ss"),
    },
    {
      title: t("dreamLogs.orphanFiles.modifiedAt"),
      dataIndex: "modified_at",
      key: "modified_at",
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
            onClick={() => handlePreview(record.path)}
          />
          <Popconfirm
            title={t("dreamLogs.orphanFiles.deleteConfirm")}
            onConfirm={() => handleDeleteFile(record.path)}
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
      {orphanFiles && (
        <Alert
          type="info"
          showIcon
          icon={<FolderOutlined />}
          style={{ marginBottom: 16 }}
          message={
            <Space>
              <Text strong>{t("dreamLogs.orphanFiles.workspaceDir")}:</Text>
              <Text copyable>{orphanFiles.workspace_dir}</Text>
            </Space>
          }
        />
      )}
      {orphanFiles && (
        <Row gutter={16} className={styles.statsRow}>
          <Col span={12}>
            <Card className={styles.statsCard}>
              <Statistic
                title={t("dreamLogs.orphanFiles.totalFiles")}
                value={orphanFiles.total_files}
                prefix={<FileOutlined />}
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card className={styles.statsCard}>
              <Statistic
                title={t("dreamLogs.orphanFiles.totalSize")}
                value={formatSize(orphanFiles.total_size)}
                prefix={<FolderOutlined />}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card
        title={t("dreamLogs.orphanFiles.title")}
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchOrphanFiles}
          >
            {t("common.refresh")}
          </Button>
        }
      >
        <Spin spinning={loading}>
          {!orphanFiles || orphanFiles.files.length === 0 ? (
            <Empty
              description={t("dreamLogs.orphanFiles.noFiles")}
              style={{ padding: 40 }}
            />
          ) : (
            <Table
              columns={columns}
              dataSource={orphanFiles.files}
              rowKey="path"
              pagination={false}
              scroll={{ x: 800 }}
            />
          )}
        </Spin>
      </Card>

      <Modal
        title={
          <Space>
            <FileOutlined />
            {t("dreamLogs.orphanFiles.previewTitle")}
            {previewContent && (
              <Text type="secondary">
                ({previewContent.filename})
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
                  {t("dreamLogs.orphanFiles.filename")}: {previewContent.filename} |
                  {t("dreamLogs.orphanFiles.size")}: {formatSize(previewContent.size)}
                </Text>
              </Space>

              {/* Error message display */}
              {!previewContent.is_loadable && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginTop: 12 }}
                  message={previewContent.error_message || t("dreamLogs.orphanFiles.previewFailed")}
                />
              )}

              {/* Image preview */}
              {previewContent.is_loadable && previewContent.file_type === "image" && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: "#f5f5f5",
                    borderRadius: 4,
                    textAlign: "center",
                  }}
                >
                  <Image
                    src={`data:image;base64,${previewContent.content}`}
                    alt={previewContent.filename}
                    style={{ maxWidth: "100%", maxHeight: 400 }}
                  />
                </div>
              )}

              {/* Text/Markdown preview */}
              {previewContent.is_loadable && previewContent.file_type === "text" && (
                <div
                  className={styles.markdownContent}
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: "#f5f5f5",
                    borderRadius: 4,
                  }}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {previewContent.content}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )}
        </Spin>
      </Modal>
    </div>
  );
}