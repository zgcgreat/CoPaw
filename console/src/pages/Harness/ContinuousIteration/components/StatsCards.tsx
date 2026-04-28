import { Card, Row, Col, Statistic } from "antd";
import {
  HistoryOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  ClockCircleOutlined,
  HourglassOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { DreamLogsStats } from "../../../../api/types/dreamLogs";
import styles from "../index.module.less";

interface StatsCardsProps {
  stats: DreamLogsStats;
}

export default function StatsCards({ stats }: StatsCardsProps) {
  const { t } = useTranslation();

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}min`;
  };

  const successRate =
    stats.total_executions > 0
      ? ((stats.success_count / stats.total_executions) * 100).toFixed(1)
      : "0";

  const formatLastExecution = (timestamp?: string): string => {
    if (!timestamp) return "-";
    const date = new Date(timestamp);
    // Use shorter format to avoid line breaks
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${month}-${day} ${hours}:${minutes}`;
  };

  return (
    <Row gutter={16} className={styles.statsRow}>
      <Col span={4}>
        <Card className={styles.statsCard}>
          <Statistic
            title={t("dreamLogs.stats.totalExecutions")}
            value={stats.total_executions}
            prefix={<HistoryOutlined />}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card className={styles.statsCard}>
          <Statistic
            title={t("dreamLogs.stats.successRate")}
            value={successRate}
            suffix="%"
            prefix={<CheckCircleOutlined />}
            valueStyle={{ color: "#3f8600" }}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card className={styles.statsCard}>
          <Statistic
            title={t("dreamLogs.stats.spaceSaved")}
            value={formatSize(stats.total_size_saved)}
            prefix={<DatabaseOutlined />}
            valueStyle={{ color: "#1890ff" }}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card className={styles.statsCard}>
          <Statistic
            title={t("dreamLogs.stats.filesChanged")}
            value={stats.total_files_changed}
            prefix={<FileTextOutlined />}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card className={styles.statsCard}>
          <Statistic
            title={t("dreamLogs.stats.avgDuration")}
            value={formatDuration(stats.avg_duration_ms)}
            prefix={<HourglassOutlined />}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card className={styles.statsCard}>
          <Statistic
            title={t("dreamLogs.stats.lastOptimization")}
            value={formatLastExecution(stats.last_execution)}
            prefix={<ClockCircleOutlined />}
          />
        </Card>
      </Col>
    </Row>
  );
}