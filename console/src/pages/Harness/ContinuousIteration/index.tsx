import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Table,
  Card,
  Button,
  Tag,
  Space,
  Modal,
  message,
  Spin,
  Empty,
  Collapse,
  Typography,
  Tooltip,
  Tabs,
  DatePicker,
  Select,
  Row,
  Col,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  PlayCircleOutlined,
  HistoryOutlined,
  FileTextOutlined,
  RollbackOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  DatabaseOutlined,
  FilterOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { dreamLogsApi } from "../../../api/modules/dreamLogs";
import type {
  DreamLogRecord,
  DreamLogsStats,
  FileStats,
} from "../../../api/types/dreamLogs";
import StatsCards from "./components/StatsCards";
import FileDiffModal from "./components/FileDiffModal";
import BackupFiles from "./components/BackupFiles";
import OrphanFiles from "./components/OrphanFiles";
import styles from "./index.module.less";

const { Panel } = Collapse;
const { Text } = Typography;
const { RangePicker } = DatePicker;

export default function ContinuousIterationPage() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [records, setRecords] = useState<DreamLogRecord[]>([]);
  const [stats, setStats] = useState<DreamLogsStats | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [diffModalVisible, setDiffModalVisible] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<DreamLogRecord | null>(null);
  const [selectedFilename, setSelectedFilename] = useState<string>("");

  // Filter state
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [triggerFilter, setTriggerFilter] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, [page, pageSize]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await dreamLogsApi.list(page, pageSize);
      setRecords(data.records);
      setStats(data.stats);
      setTotal(data.total);
    } catch (error) {
      console.error("Failed to fetch dream logs:", error);
    } finally {
      setLoading(false);
    }
  };

  // Filter records based on date range and status
  const filteredRecords = records.filter((record) => {
    // Date filter
    if (dateRange && dateRange[0] && dateRange[1]) {
      const recordDate = dayjs(record.timestamp);
      if (recordDate < dateRange[0] || recordDate > dateRange[1].endOf('day')) {
        return false;
      }
    }
    // Status filter
    if (statusFilter && record.status !== statusFilter) {
      return false;
    }
    // Trigger filter
    if (triggerFilter && record.trigger !== triggerFilter) {
      return false;
    }
    return true;
  });

  const handleFilterChange = () => {
    // Reset to first page when filter changes
    setPage(1);
  };

  const clearFilters = () => {
    setDateRange(null);
    setStatusFilter(null);
    setTriggerFilter(null);
    setPage(1);
  };

  const handleTrigger = async () => {
    try {
      const result = await dreamLogsApi.trigger();
      if (result.success) {
        message.success(t("dreamLogs.triggerNow") + " - " + result.message);
        // Refresh data after a delay since optimization runs in background
        setTimeout(fetchData, 5000);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error("Failed to trigger dream optimization");
    }
  };

  const handleRollback = async (recordId: string, files?: string[]) => {
    Modal.confirm({
      title: t("dreamLogs.rollback.confirm"),
      content: files
        ? t("dreamLogs.rollback.confirmMessage")
        : t("dreamLogs.rollback.confirmAllMessage"),
      onOk: async () => {
        try {
          const result = await dreamLogsApi.rollback(recordId, files);
          if (result.success) {
            message.success(t("dreamLogs.rollback.success"));
            fetchData();
          } else {
            message.error(result.message);
          }
        } catch (error) {
          message.error(t("dreamLogs.rollback.failed"));
        }
      },
    });
  };

  const handleViewDiff = (record: DreamLogRecord, filename: string) => {
    setSelectedRecord(record);
    setSelectedFilename(filename);
    setDiffModalVisible(true);
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}min`;
  };

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; icon: React.ReactNode }> = {
      success: { color: "success", icon: <CheckCircleOutlined /> },
      failed: { color: "error", icon: <CloseCircleOutlined /> },
      rollback: { color: "warning", icon: <SyncOutlined /> },
    };
    const config = statusMap[status] || { color: "default", icon: null };
    return (
      <Tag color={config.color} icon={config.icon}>
        {t(`dreamLogs.statusValue.${status}`)}
      </Tag>
    );
  };

  const getTriggerTag = (trigger: string) => {
    const color = trigger === "cron" ? "blue" : "purple";
    return (
      <Tag color={color}>
        {t(`dreamLogs.trigger.${trigger}`)}
      </Tag>
    );
  };

  const columns: ColumnsType<DreamLogRecord> = [
    {
      title: t("dreamLogs.runTime"),
      key: "timestamp",
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size="small">
          <Text>{dayjs(record.timestamp).format("YYYY-MM-DD HH:mm:ss")}</Text>
          <Space size="small">
            {getTriggerTag(record.trigger)}
            {getStatusTag(record.status)}
          </Space>
        </Space>
      ),
    },
    {
      title: t("dreamLogs.filesOptimized"),
      dataIndex: "total_files_changed",
      key: "files",
      width: 100,
      render: (value: number, record) => (
        <Tooltip title={record.files_optimized.join(", ")}>
          <Tag icon={<FileTextOutlined />}>{value}</Tag>
        </Tooltip>
      ),
    },
    {
      title: t("dreamLogs.stats.spaceSaved"),
      dataIndex: "total_size_saved",
      key: "space_saved",
      width: 120,
      render: (value: number) => (
        <Text type="success">{formatSize(value)}</Text>
      ),
    },
    {
      title: t("dreamLogs.duration"),
      dataIndex: "duration_ms",
      key: "duration",
      width: 100,
      render: (value: number) => (
        <Text>
          <ClockCircleOutlined /> {formatDuration(value)}
        </Text>
      ),
    },
    {
      title: t("common.actions"),
      key: "actions",
      width: 80,
      fixed: "right",
      render: (_, record) => (
        <Space>
          <Tooltip title={t("dreamLogs.rollback.all")}>
            <Button
              type="text"
              size="small"
              icon={<RollbackOutlined />}
              onClick={() => handleRollback(record.id)}
              disabled={record.status === "rollback"}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const renderFileStats = (record: DreamLogRecord) => {
    // Filter files with actual changes (size_saved > 0 or lines_removed > 0)
    const fileEntries = Object.entries(record.file_stats).filter(
      ([, stats]) => stats.size_saved > 0 || stats.lines_removed > 0
    );
    if (fileEntries.length === 0) return null;

    const fileColumns: ColumnsType<[string, FileStats]> = [
      {
        title: t("dreamLogs.file.filename"),
        dataIndex: 0,
        key: "filename",
        width: 180,
        render: (filename: string) => <Text strong>{filename}</Text>,
      },
      {
        title: t("dreamLogs.file.sizeBefore"),
        dataIndex: 1,
        key: "size_before",
        width: 100,
        render: (stats: FileStats) => formatSize(stats.size_before),
      },
      {
        title: t("dreamLogs.file.sizeAfter"),
        dataIndex: 1,
        key: "size_after",
        width: 100,
        render: (stats: FileStats) => formatSize(stats.size_after),
      },
      {
        title: t("dreamLogs.file.sizeSaved"),
        dataIndex: 1,
        key: "size_saved",
        width: 100,
        render: (stats: FileStats) =>
          stats.size_saved > 0 ? (
            <Tag color="green">-{formatSize(stats.size_saved)}</Tag>
          ) : (
            <Text type="secondary">0</Text>
          ),
      },
      {
        title: t("common.actions"),
        key: "actions",
        width: 150,
        render: ([filename, stats]: [string, FileStats]) => (
          <Space>
            <Button
              type="link"
              size="small"
              icon={<FileTextOutlined />}
              onClick={() => handleViewDiff(record, filename)}
            >
              {t("dreamLogs.viewDiff")}
            </Button>
            <Button
              type="link"
              size="small"
              icon={<RollbackOutlined />}
              onClick={() => handleRollback(record.id, [filename])}
              disabled={record.status === "rollback"}
            >
              {t("dreamLogs.rollback.single")}
            </Button>
          </Space>
        ),
      },
    ];

    return (
      <Space direction="vertical" style={{ width: "100%" }}>
        <Text strong>{t("dreamLogs.filesOptimized")}:</Text>
        <Table
          columns={fileColumns}
          dataSource={fileEntries}
          rowKey={(item) => item[0]}
          pagination={false}
          size="small"
        />
        {record.summary && (
          <Collapse
            style={{ marginTop: 12 }}
            items={[
              {
                key: "summary",
                label: t("dreamLogs.summary"),
                children: (
                  <div className={styles.markdownContent} style={{ maxHeight: 300, overflow: "auto" }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {record.summary}
                    </ReactMarkdown>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Space>
    );
  };

  const renderRecordsContent = () => (
    <>
      {stats && <StatsCards stats={stats} />}
      <Card
        title={
          <Space>
            <HistoryOutlined />
            {t("dreamLogs.title")}
          </Space>
        }
        extra={
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleTrigger}
          >
            {t("dreamLogs.triggerNow")}
          </Button>
        }
      >
        {/* Filter controls */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col>
            <Space>
              <FilterOutlined />
              <RangePicker
                value={dateRange}
                onChange={(dates) => {
                  setDateRange(dates);
                  handleFilterChange();
                }}
                placeholder={[t("dreamLogs.filter.startDate"), t("dreamLogs.filter.endDate")]}
                allowClear
              />
              <Select
                value={statusFilter}
                onChange={(value) => {
                  setStatusFilter(value);
                  handleFilterChange();
                }}
                placeholder={t("dreamLogs.filter.status")}
                allowClear
                style={{ width: 120 }}
                options={[
                  { value: "success", label: t("dreamLogs.statusValue.success") },
                  { value: "failed", label: t("dreamLogs.statusValue.failed") },
                  { value: "rollback", label: t("dreamLogs.statusValue.rollback") },
                ]}
              />
              <Select
                value={triggerFilter}
                onChange={(value) => {
                  setTriggerFilter(value);
                  handleFilterChange();
                }}
                placeholder={t("dreamLogs.filter.trigger")}
                allowClear
                style={{ width: 120 }}
                options={[
                  { value: "cron", label: t("dreamLogs.trigger.cron") },
                  { value: "manual", label: t("dreamLogs.trigger.manual") },
                ]}
              />
              {(dateRange || statusFilter || triggerFilter) && (
                <Button onClick={clearFilters}>
                  {t("dreamLogs.filter.clear")}
                </Button>
              )}
            </Space>
          </Col>
        </Row>

        <Spin spinning={loading}>
          {filteredRecords.length === 0 ? (
            <Empty
              description={t("dreamLogs.noRecords")}
              style={{ padding: 40 }}
            >
              <Text type="secondary">{t("dreamLogs.firstRecord")}</Text>
            </Empty>
          ) : (
            <Table
              columns={columns}
              dataSource={filteredRecords}
              rowKey="id"
              pagination={{
                current: page,
                pageSize,
                total: filteredRecords.length,
                onChange: (p, ps) => {
                  setPage(p);
                  setPageSize(ps);
                },
              }}
              expandable={{
                expandedRowRender: renderFileStats,
                rowExpandable: (record) =>
                  Object.entries(record.file_stats).some(
                    ([, stats]) => stats.size_saved > 0 || stats.lines_removed > 0
                  ),
              }}
              scroll={{ x: 700 }}
            />
          )}
        </Spin>
      </Card>
    </>
  );

  const tabItems = [
    {
      key: "records",
      label: (
        <Space>
          <HistoryOutlined />
          {t("dreamLogs.tabRecords")}
        </Space>
      ),
      children: renderRecordsContent(),
    },
    {
      key: "backups",
      label: (
        <Space>
          <DatabaseOutlined />
          {t("dreamLogs.tabBackups")}
        </Space>
      ),
      children: <BackupFiles />,
    },
    {
      key: "cleanup",
      label: (
        <Space>
          <DeleteOutlined />
          {t("dreamLogs.tabCleanup")}
        </Space>
      ),
      children: <OrphanFiles />,
    },
  ];

  return (
    <div className={styles.container}>
      <Tabs defaultActiveKey="records" items={tabItems} />
      <FileDiffModal
        visible={diffModalVisible}
        record={selectedRecord}
        filename={selectedFilename}
        onClose={() => setDiffModalVisible(false)}
        onRollback={() => {
          if (selectedRecord) {
            handleRollback(selectedRecord.id, [selectedFilename]);
          }
          setDiffModalVisible(false);
        }}
      />
    </div>
  );
}