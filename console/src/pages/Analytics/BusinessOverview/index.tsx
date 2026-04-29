/**
 * AI平台运营概览 - 业务价值展示页面
 * 用于银行管理层查看平台使用情况和业务覆盖情况
 */

import { useState, useEffect, useCallback } from "react";
import { Row, Col, Tooltip, Select, DatePicker, message } from "antd";
import {
  Users,
  Clock,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import dayjs from "dayjs";
import styles from "./index.module.less";
import { tracingApi } from "../../../api/modules/tracing";
import {
  formatNumber,
  formatTokens,
  formatChange,
  truncateName,
  type UserRow,
  type TimeRange,
} from "./types";

const { Option } = Select;

// 平台名称映射（source_id -> 中文名称）
const PLATFORM_NAME_MAP: Record<string, string> = {
  CMSJY: "远程RM小助Claw版",
  UPPCLAW: "智像小助CLAW",
  copilotClaw: "数据赋能小助CLAW",
  ruice: "睿策小助Claw版",
  privatebanking: "私行小助claw",
  SZLS: "数智零售claw",
  rtauto: "实时数据CLAW",
  RMASSIST: "RM小助",
};

// 获取平台显示名称
const getPlatformDisplayName = (sourceId: string): string => {
  return PLATFORM_NAME_MAP[sourceId] || sourceId;
};

// 颜色配置
const CHART_COLORS = [
  "#1890ff",
  "#52c41a",
  "#faad14",
  "#722ed1",
  "#e866a8",
  "#13c2c2",
  "#fa8c16",
  "#a0d911",
];

// 柱状图颜色（纯色填充）
const BAR_COLORS = [
  "#1890ff",
  "#52c41a",
  "#faad14",
  "#722ed1",
  "#e866a8",
];

// 指标卡片左边框颜色
const METRIC_BORDER_COLORS = ["#1890ff", "#52c41a", "#722ed1", "#faad14"];

export default function BusinessOverviewPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("day");
  const [startDate, setStartDate] = useState<dayjs.Dayjs>(dayjs());
  const [endDate, setEndDate] = useState<dayjs.Dayjs>(dayjs());
  const [platform, setPlatform] = useState<string>("all");

  // 平台列表（从API获取）
  const [sources, setSources] = useState<string[]>([]);

  // 数据状态
  const [overviewStats, setOverviewStats] = useState<any>(null);
  const [growthStats, setGrowthStats] = useState({
    callsGrowth: 0,
    tokensGrowth: 0,
    sessionGrowth: 0,
    userGrowth: 0,
    platformGrowth: 0,
  });
  const [channelDistribution, setChannelDistribution] = useState<{
    platformUserDistribution: { name: string; value: number }[];
    platformCallDistribution: { name: string; value: number }[];
    totalPlatforms: number;
  }>({
    platformUserDistribution: [],
    platformCallDistribution: [],
    totalPlatforms: 0,
  });
  const [trendData, setTrendData] = useState<{
    date: string;
    calls: number;
    tokens: number;
    users: number;
  }[]>([]);
  const [topUsers, setTopUsers] = useState<UserRow[]>([]);

  // 折线图悬浮 tooltip 状态
  const [lineChartTooltip, setLineChartTooltip] = useState<{
    visible: boolean;
    x: number;
    y: number;
    date: string;
    calls: number;
    tokens: number;
    users: number;
  }>({
    visible: false,
    x: 0,
    y: 0,
    date: "",
    calls: 0,
    tokens: 0,
    users: 0,
  });

  // 计算结束日期
  const calculateEndDate = (start: dayjs.Dayjs, mode: TimeRange): dayjs.Dayjs => {
    switch (mode) {
      case "day":
        return start;
      case "week":
        return start.add(6, "day");
      case "month":
        return start.add(1, "month").subtract(1, "day");
      case "custom":
        return endDate;
      default:
        return start;
    }
  };

  // 获取平台列表
  const fetchSources = useCallback(async () => {
    try {
      const res = await tracingApi.getSources();
      setSources(res.sources || []);
    } catch (error) {
      console.error("Failed to fetch sources:", error);
    }
  }, []);

  // 初始加载平台列表
  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  // 获取数据
  const fetchData = useCallback(async () => {
    const startStr = startDate.format("YYYY-MM-DD");
    const endStr = endDate.format("YYYY-MM-DD");
    // 用于筛选的 source_id（"all" 表示不筛选，其他值表示筛选特定平台）
    const filterSourceId = platform === "all" ? undefined : platform;

    // 趋势图始终使用近30天数据（不受顶部日期选择器影响）
    const trendEndDate = dayjs();
    const trendStartDate = trendEndDate.subtract(29, "day");
    const trendStartStr = trendStartDate.format("YYYY-MM-DD");
    const trendEndStr = trendEndDate.format("YYYY-MM-DD");

    try {
      // 并行请求所有数据
      // 核心运营指标、趋势、模型分布、用户分析等需要根据平台筛选
      // 平台用户分布和平台调用次数分布也受平台筛选影响
      // 趋势图始终使用近30天数据
      const [overviewRes, growthRes, channelRes, trendRes, usersRes] = await Promise.allSettled([
        tracingApi.getOverview(startStr, endStr, filterSourceId),
        tracingApi.getGrowthStats(startStr, endStr, timeRange, filterSourceId),
        tracingApi.getChannelDistribution(filterSourceId, startStr, endStr), // 受平台筛选影响
        tracingApi.getDailyTrend(trendStartStr, trendEndStr, filterSourceId), // 始终近30天
        tracingApi.getUsers(1, 5, { start_date: startStr, end_date: endStr, source_id: filterSourceId }),
      ]);

      // 处理 overview stats
      if (overviewRes.status === "fulfilled") {
        setOverviewStats(overviewRes.value);
      }

      // 处理 growth stats
      if (growthRes.status === "fulfilled") {
        setGrowthStats(growthRes.value);
      }

      // 处理 channel distribution
      if (channelRes.status === "fulfilled") {
        setChannelDistribution(channelRes.value);
      }

      // 处理 trend data
      if (trendRes.status === "fulfilled") {
        setTrendData(trendRes.value.trendData || []);
      }

      // 处理 top users
      if (usersRes.status === "fulfilled") {
        const users = usersRes.value.items.map((u: any) => ({
          userId: u.user_id,
          name: u.user_id, // 后端没返回name，用user_id代替
          calls: u.total_conversations,
          tokens: u.total_tokens,
          lastActive: u.last_active
            ? dayjs(u.last_active).format("YYYY-MM-DD HH:mm")
            : "-",
        }));
        setTopUsers(users);
      }
    } catch (error) {
      console.error("Failed to fetch data:", error);
      message.error("获取数据失败");
    }
  }, [startDate, endDate, timeRange, platform]);

  // 初始加载和日期变化时获取数据
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 处理开始日期变化
  const handleStartDateChange = (date: dayjs.Dayjs | null) => {
    if (date) {
      setStartDate(date);
      if (timeRange === "day") {
        setEndDate(date);
      } else if (timeRange === "week") {
        setEndDate(date.add(6, "day"));
      } else if (timeRange === "month") {
        setEndDate(date.add(1, "month").subtract(1, "day"));
      }
    }
  };

  // 禁用不符合时间范围要求的日期（开始日期）
  const disabledStartDate = (current: dayjs.Dayjs | null): boolean => {
    if (!current) return false;
    const today = dayjs().startOf("day");
    // 只禁用未来日期，允许选择任意历史日期
    return current.isAfter(today, "day");
  };

  // 禁用不符合时间范围要求的日期（结束日期）
  const disabledEndDate = (current: dayjs.Dayjs | null): boolean => {
    if (!current) return false;
    const today = dayjs().startOf("day");
    // 禁用未来日期
    if (current.isAfter(today, "day")) {
      return true;
    }
    // 自定义模式：结束日期不能早于开始日期
    if (timeRange === "custom" && current.isBefore(startDate, "day")) {
      return true;
    }
    return false;
  };

  // 处理模式切换
  const handleModeChange = (mode: TimeRange) => {
    setTimeRange(mode);
    const today = dayjs().startOf("day");
    if (mode === "day") {
      // 日模式：显示今天
      setStartDate(today);
      setEndDate(today);
    } else if (mode === "week") {
      // 周模式：显示最近7天（今天往前推6天 + 今天）
      const weekStart = today.subtract(6, "day");
      setStartDate(weekStart);
      setEndDate(today);
    } else if (mode === "month") {
      // 月模式：显示最近30天（今天往前推29天 + 今天）
      const monthStart = today.subtract(29, "day");
      setStartDate(monthStart);
      setEndDate(today);
    } else if (mode === "custom") {
      // 自定义模式：默认显示最近7天，用户可以手动调整
      const customStart = today.subtract(6, "day");
      setStartDate(customStart);
      setEndDate(today);
    }
  };

  // 处理结束日期变化
  const handleEndDateChange = (date: dayjs.Dayjs | null) => {
    if (date) {
      // 确保结束日期不早于开始日期
      if (date.isBefore(startDate, "day")) {
        message.warning("结束日期不能早于开始日期");
        return;
      }
      setEndDate(date);
    }
  };

  const calculatedEndDate = calculateEndDate(startDate, timeRange);

  // 趋势标题固定为近30天（趋势图始终显示近30天数据，不受顶部日期选择器影响）
  const getTrendTitle = () => {
    return "近30天使用趋势";
  };

  // 计算指标数据
  const metricData = {
    totalCalls: overviewStats?.total_conversations || 0,
    callsGrowth: growthStats.callsGrowth,
    totalTokens: overviewStats?.total_tokens || 0,
    tokensGrowth: growthStats.tokensGrowth,
    avgResponseTime: 0,
    responseTimeGrowth: 0,
    avgDuration: overviewStats?.avg_duration_ms
      ? (overviewStats.avg_duration_ms / 1000)
      : 0,
    sessionCount: overviewStats?.total_sessions || 0,
    sessionGrowth: growthStats.sessionGrowth,
  };

  // 平台使用情况数据
  const platformData = {
    totalUsers: overviewStats?.total_users || 0,
    userGrowth: growthStats.userGrowth,
    totalPlatforms: channelDistribution.totalPlatforms,
    platformGrowth: growthStats.platformGrowth,
    platformUserDistribution: channelDistribution.platformUserDistribution,
    platformCallDistribution: channelDistribution.platformCallDistribution,
  };

  // ============================================================
  // 渲染：饼图（使用 SVG 实现实心饼图，带悬浮效果）
  // ============================================================
  const renderPieChart = (
    chartData: { name: string; fullName?: string; value: number }[],
  ) => {
    const total = chartData.reduce((sum, item) => sum + item.value, 0);
    if (total === 0) {
      return (
        <div className={styles.pieChartContainer}>
          <svg width="200" height="200" viewBox="0 0 200 200">
            <circle cx="100" cy="100" r="80" fill="#f0f0f0" />
            <text x="100" y="105" textAnchor="middle" fontSize="12" fill="#999">
              暂无数据
            </text>
          </svg>
        </div>
      );
    }

    const cx = 100;
    const cy = 100;
    const radius = 80;
    const hoverRadius = 85; // 悬浮时放大的半径

    // 计算每个扇形的角度和路径
    const slices: Array<{
      path: string;
      hoverPath: string;
      percentage: number;
      name: string;
      fullName: string;
      value: number;
      color: string;
      index: number;
    }> = [];

    let currentAngle = -90;

    chartData.forEach((item, index) => {
      const percentage = item.value / total;
      const angle = percentage * 360;
      const startAngle = currentAngle;
      const endAngle = currentAngle + angle;
      currentAngle = endAngle;

      const startRad = (startAngle * Math.PI) / 180;
      const endRad = (endAngle * Math.PI) / 180;

      // 正常路径
      const x1 = cx + radius * Math.cos(startRad);
      const y1 = cy + radius * Math.sin(startRad);
      const x2 = cx + radius * Math.cos(endRad);
      const y2 = cy + radius * Math.sin(endRad);

      // 悬浮时放大的路径
      const hx1 = cx + hoverRadius * Math.cos(startRad);
      const hy1 = cy + hoverRadius * Math.sin(startRad);
      const hx2 = cx + hoverRadius * Math.cos(endRad);
      const hy2 = cy + hoverRadius * Math.sin(endRad);

      const largeArc = angle > 180 ? 1 : 0;

      const pathD = `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`;
      const hoverPathD = `M ${cx} ${cy} L ${hx1} ${hy1} A ${hoverRadius} ${hoverRadius} 0 ${largeArc} 1 ${hx2} ${hy2} Z`;

      slices.push({
        path: pathD,
        hoverPath: hoverPathD,
        percentage,
        name: item.name,
        fullName: item.fullName || item.name,
        value: item.value,
        color: CHART_COLORS[index % CHART_COLORS.length],
        index,
      });
    });

    return (
      <div className={styles.pieChartContainer}>
        <svg width="200" height="200" viewBox="0 0 200 200" className={styles.pieSvg}>
          {slices.map((slice) => (
            <Tooltip
              key={slice.index}
              title={`${slice.fullName}: ${slice.value} (${(slice.percentage * 100).toFixed(1)}%)`}
              mouseLeaveDelay={0}
              mouseEnterDelay={0}
            >
              <g className={styles.pieSlice}>
                <path
                  d={slice.path}
                  fill={slice.color}
                  stroke="#fff"
                  strokeWidth="2"
                  className={styles.pieSlicePath}
                />
              </g>
            </Tooltip>
          ))}
        </svg>
      </div>
    );
  };

  // ============================================================
  // 渲染：图例
  // ============================================================
  const renderLegend = (chartData: { name: string; fullName?: string; value: number }[]) => {
    const total = chartData.reduce((sum, item) => sum + item.value, 0);
    return (
      <div className={styles.pieLegend}>
        {chartData.map((item, index) => {
          const displayName = item.name;
          const fullName = item.fullName || item.name;
          const isTruncated = fullName !== displayName;
          const statsInfo = `${item.value} (${((item.value / total) * 100).toFixed(1)}%)`;
          const tooltipTitle = isTruncated ? `${fullName}\n${statsInfo}` : statsInfo;
          return (
            <Tooltip
              key={index}
              title={tooltipTitle}
            >
              <span className={styles.legendItem}>
                <span
                  className={styles.legendDot}
                  style={{
                    background: CHART_COLORS[index % CHART_COLORS.length],
                  }}
                />
                <span>{displayName}</span>
              </span>
            </Tooltip>
          );
        })}
      </div>
    );
  };

  // ============================================================
  // 渲染：折线图（带悬浮效果）
  // ============================================================
  const renderLineChart = (
    chartData: { date: string; calls: number; tokens: number; users: number }[],
    height: number = 320,
  ) => {
    if (!chartData || chartData.length === 0) return null;
    if (chartData.length === 1) {
      const d = chartData[0];
      return (
        <div className={styles.trendChartContainer} style={{ height }}>
          <div style={{ textAlign: "center", padding: "100px 0", color: "#999" }}>
            <div>日期: {d.date}</div>
            <div>调用次数: {formatNumber(d.calls)}</div>
            <div>Token消耗: {formatTokens(d.tokens)}</div>
            <div>用户数: {formatNumber(d.users)}</div>
          </div>
        </div>
      );
    }

    const padding = { top: 20, right: 30, bottom: 60, left: 50 };
    const width = 1000;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const maxCalls = Math.max(...chartData.map((d) => d.calls), 1);
    const maxTokens = Math.max(...chartData.map((d) => d.tokens), 1);
    const maxUsers = Math.max(...chartData.map((d) => d.users), 1);

    const xScale = (index: number) =>
      (index / (chartData.length - 1)) * chartWidth + padding.left;

    // Y轴刻度
    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
      y: chartHeight * ratio + padding.top,
      label: formatNumber(maxCalls * (1 - ratio)),
    }));

    // X轴刻度 - 显示所有日期，每隔一定间隔显示标签
    const dateInterval = chartData.length <= 15 ? 1 : chartData.length <= 30 ? 2 : 3;

    // 生成折线路径
    const callsPath = chartData
      .map((d, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${chartHeight - (d.calls / maxCalls) * chartHeight + padding.top}`)
      .join(" ");
    const tokensPath = chartData
      .map((d, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${chartHeight - (d.tokens / maxTokens) * chartHeight + padding.top}`)
      .join(" ");
    const usersPath = chartData
      .map((d, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${chartHeight - (d.users / maxUsers) * chartHeight + padding.top}`)
      .join(" ");

    // 鼠标移动处理 - 基于最近的数据点
    const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // SVG 使用 preserveAspectRatio="xMidYMid meet" 会居中显示
      // 需要计算实际的缩放比例和偏移量
      const viewBoxAspect = width / height;
      const containerAspect = rect.width / rect.height;

      let actualScaleX: number;
      let offsetX: number;

      if (containerAspect > viewBoxAspect) {
        // 容器更宽，SVG 按高度缩放，左右留白
        actualScaleX = rect.height / height;
        offsetX = (rect.width - width * actualScaleX) / 2;
      } else {
        // 容器更高，SVG 按宽度缩放，上下留白
        actualScaleX = rect.width / width;
        offsetX = 0;
      }

      // 计算每个数据点在 DOM 中的实际 X 位置（考虑居中偏移）
      const dataPoints = chartData.map((d, i) => ({
        index: i,
        x: xScale(i) * actualScaleX + offsetX,
        data: d,
      }));

      // 找到离鼠标最近的数据点
      let nearestPoint = dataPoints[0];
      let minDistance = Math.abs(mouseX - nearestPoint.x);

      for (const point of dataPoints) {
        const distance = Math.abs(mouseX - point.x);
        if (distance < minDistance) {
          minDistance = distance;
          nearestPoint = point;
        }
      }

      // 计算实际图表宽度的一半作为阈值
      const actualChartWidth = chartWidth * actualScaleX;
      const threshold = actualChartWidth / chartData.length / 2;

      if (minDistance <= threshold) {
        setLineChartTooltip({
          visible: true,
          x: nearestPoint.x + 10,
          y: mouseY - 10,
          date: nearestPoint.data.date,
          calls: nearestPoint.data.calls,
          tokens: nearestPoint.data.tokens,
          users: nearestPoint.data.users,
        });
      } else {
        setLineChartTooltip((prev) => ({ ...prev, visible: false }));
      }
    };

    const handleMouseLeave = () => {
      setLineChartTooltip((prev) => ({ ...prev, visible: false }));
    };

    return (
      <div
        className={styles.trendChartContainer}
        style={{ height }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Y轴 */}
          {yTicks.map((tick, i) => (
            <g key={`y-${i}`}>
              <line
                x1={padding.left}
                y1={tick.y}
                x2={width - padding.right}
                y2={tick.y}
                stroke="#f0f0f0"
                strokeDasharray="4,4"
              />
              <text
                x={padding.left - 8}
                y={tick.y + 4}
                textAnchor="end"
                fontSize="11"
                fill="#999"
              >
                {tick.label}
              </text>
            </g>
          ))}

          {/* X轴日期标签 */}
          {chartData.map((d, i) => {
            // 根据间隔决定是否显示标签
            const showLabel = i % dateInterval === 0 || i === chartData.length - 1;
            return (
              <text
                key={`x-${i}`}
                x={xScale(i)}
                y={height - 20}
                textAnchor="middle"
                fontSize="10"
                fill={showLabel ? "#666" : "#ccc"}
                transform={`rotate(-45, ${xScale(i)}, ${height - 20})`}
              >
                {d.date.slice(5)}
              </text>
            );
          })}

          {/* 调用次数折线 */}
          <path
            d={callsPath}
            fill="none"
            stroke="#1890ff"
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          {/* Token折线 */}
          <path
            d={tokensPath}
            fill="none"
            stroke="#52c41a"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="6,3"
          />

          {/* 用户折线 */}
          <path
            d={usersPath}
            fill="none"
            stroke="#faad14"
            strokeWidth="2"
            strokeLinecap="round"
          />

          {/* 所有数据点 - 调用次数 */}
          {chartData.map((d, i) => (
            <circle
              key={`calls-${i}`}
              cx={xScale(i)}
              cy={chartHeight - (d.calls / maxCalls) * chartHeight + padding.top}
              r="4"
              fill="#1890ff"
              stroke="#fff"
              strokeWidth="2"
            />
          ))}

          {/* 所有数据点 - Token */}
          {chartData.map((d, i) => (
            <circle
              key={`tokens-${i}`}
              cx={xScale(i)}
              cy={chartHeight - (d.tokens / maxTokens) * chartHeight + padding.top}
              r="3"
              fill="#52c41a"
              stroke="#fff"
              strokeWidth="1.5"
            />
          ))}

          {/* 所有数据点 - 用户 */}
          {chartData.map((d, i) => (
            <circle
              key={`users-${i}`}
              cx={xScale(i)}
              cy={chartHeight - (d.users / maxUsers) * chartHeight + padding.top}
              r="3"
              fill="#faad14"
              stroke="#fff"
              strokeWidth="1.5"
            />
          ))}

          {/* 高亮当前悬浮的数据点 */}
          {lineChartTooltip.visible && (() => {
            const dataIndex = chartData.findIndex(d => d.date === lineChartTooltip.date);
            if (dataIndex === -1) return null;
            const x = xScale(dataIndex);
            return (
              <>
                {/* 垂直参考线 */}
                <line
                  x1={x}
                  y1={padding.top}
                  x2={x}
                  y2={chartHeight + padding.top}
                  stroke="#1890ff"
                  strokeWidth="1"
                  strokeDasharray="4,4"
                  opacity="0.5"
                />
                {/* 高亮的数据点 */}
                <circle
                  cx={x}
                  cy={chartHeight - (chartData[dataIndex].calls / maxCalls) * chartHeight + padding.top}
                  r="7"
                  fill="#1890ff"
                  stroke="#fff"
                  strokeWidth="3"
                />
                <circle
                  cx={x}
                  cy={chartHeight - (chartData[dataIndex].tokens / maxTokens) * chartHeight + padding.top}
                  r="5"
                  fill="#52c41a"
                  stroke="#fff"
                  strokeWidth="2"
                />
                <circle
                  cx={x}
                  cy={chartHeight - (chartData[dataIndex].users / maxUsers) * chartHeight + padding.top}
                  r="5"
                  fill="#faad14"
                  stroke="#fff"
                  strokeWidth="2"
                />
              </>
            );
          })()}
        </svg>

        {/* 悬浮 Tooltip */}
        {lineChartTooltip.visible && (
          <div
            className={styles.lineChartTooltip}
            style={{
              position: "absolute",
              left: lineChartTooltip.x,
              top: lineChartTooltip.y,
            }}
          >
            <div className={styles.tooltipDate}>{lineChartTooltip.date}</div>
            <div className={styles.tooltipRow}>
              <span className={styles.tooltipDot} style={{ background: "#1890ff" }} />
              <span>调用: {formatNumber(lineChartTooltip.calls)}</span>
            </div>
            <div className={styles.tooltipRow}>
              <span className={styles.tooltipDot} style={{ background: "#52c41a" }} />
              <span>Token: {formatTokens(lineChartTooltip.tokens)}</span>
            </div>
            <div className={styles.tooltipRow}>
              <span className={styles.tooltipDot} style={{ background: "#faad14" }} />
              <span>用户: {formatNumber(lineChartTooltip.users)}</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ============================================================
  // 渲染：柱状图（带悬浮效果）
  // ============================================================
  const renderBarChart = (
    chartData: { name: string; fullName?: string; value: number }[],
    height: number = 220,
  ) => {
    const maxValue = Math.max(...chartData.map((d) => d.value), 1);

    return (
      <div className={styles.barChartContainer} style={{ height }}>
        {chartData.map((item, index) => {
          const percentage = (item.value / maxValue) * 100;
          const fullName = item.fullName || item.name;
          const displayValue = formatTokens(item.value);
          return (
            <Tooltip
              key={index}
              title={`${fullName}: ${displayValue}`}
              mouseLeaveDelay={0}
              mouseEnterDelay={0}
              placement="top"
              getPopupContainer={(triggerNode) => triggerNode.parentElement as HTMLElement}
            >
              <div className={styles.barItem}>
                <div className={styles.barLabelRow}>
                  <span className={styles.barLabel}>{fullName}</span>
                  <span className={styles.barLabelValue}>{displayValue}</span>
                </div>
                <div className={styles.barTrack}>
                  <div
                    className={styles.barFill}
                    style={{
                      width: `${Math.max(percentage, 5)}%`,
                      background: BAR_COLORS[index % BAR_COLORS.length],
                    }}
                  />
                </div>
              </div>
            </Tooltip>
          );
        })}
      </div>
    );
  };

  // ============================================================
  // 渲染：用户列表
  // ============================================================
  const renderUserList = (users: UserRow[], metric: "calls" | "lastActive") => (
    <div className={styles.userList}>
      <div className={styles.userHeader}>
        <span className={styles.userHeaderRank}>#</span>
        <span className={styles.userHeaderName}>姓名</span>
        <span className={styles.userHeaderValue}>
          {metric === "calls" ? "调用次数" : "最后活跃"}
        </span>
      </div>
      {users.map((user, index) => (
        <div key={user.userId} className={styles.userItem}>
          <span
            className={`${styles.rank} ${
              index === 0
                ? styles.top1
                : index === 1
                ? styles.top2
                : index === 2
                ? styles.top3
                : styles.normal
            }`}
          >
            {index + 1}
          </span>
          <span className={styles.userName}>
            {user.name}
            <span className={styles.userId}>({user.userId})</span>
          </span>
          <span className={styles.userValue}>
            {metric === "calls"
              ? formatNumber(user.calls)
              : user.lastActive}
          </span>
        </div>
      ))}
    </div>
  );

  // ============================================================
  // 主渲染
  // ============================================================
  return (
    <div className={styles.businessOverviewPage}>
      {/* 页面筛选工具栏 */}
      <div className={styles.header}>
        <div className={styles.filterGroup}>
          <div className={styles.segmentedControl}>
            <span
              className={`${styles.segmentItem} ${timeRange === "day" ? styles.active : ""}`}
              onClick={() => handleModeChange("day")}
            >
              日
            </span>
            <span
              className={`${styles.segmentItem} ${timeRange === "week" ? styles.active : ""}`}
              onClick={() => handleModeChange("week")}
            >
              周
            </span>
            <span
              className={`${styles.segmentItem} ${timeRange === "month" ? styles.active : ""}`}
              onClick={() => handleModeChange("month")}
            >
              月
            </span>
            <span
              className={`${styles.segmentItem} ${timeRange === "custom" ? styles.active : ""}`}
              onClick={() => handleModeChange("custom")}
            >
              自定义
            </span>
          </div>
          <div className={styles.dateRangeDisplay}>
            <DatePicker
              className={styles.datePicker}
              value={startDate}
              onChange={handleStartDateChange}
              format="YYYY-MM-DD"
              disabledDate={disabledStartDate}
            />
            <span className={styles.dateRangeArrow}>→</span>
            <DatePicker
              className={styles.datePicker}
              value={calculatedEndDate}
              onChange={handleEndDateChange}
              disabled={timeRange !== "custom"}
              format="YYYY-MM-DD"
              disabledDate={disabledEndDate}
            />
          </div>
        </div>
        <Select
          className={styles.platformSelect}
          placeholder="选择平台"
          style={{ width: 180 }}
          value={platform}
          onChange={(v) => setPlatform(v)}
        >
          <Option value="all">全部平台</Option>
          {sources.map((source) => (
            <Option key={source} value={source}>
              {getPlatformDisplayName(source)}
            </Option>
          ))}
        </Select>
      </div>

      {/* ==================== 第一屏：核心运营指标 + 趋势分析 ==================== */}
      <div className={styles.sectionTitle}>
        <span>核心运营指标</span>
      </div>
      <div className={styles.metricsRow}>
        <div className={styles.metricCard} style={{ borderLeftColor: METRIC_BORDER_COLORS[0] }}>
          <div className={styles.metricLabel}>总调用次数</div>
          <div className={styles.metricValue}>
            {formatNumber(metricData.totalCalls)}
          </div>
          <div
            className={`${styles.metricChange} ${
              metricData.callsGrowth > 0 ? styles.positive : styles.negative
            }`}
          >
            {formatChange(metricData.callsGrowth)} 环比
          </div>
        </div>
        <div className={styles.metricCard} style={{ borderLeftColor: METRIC_BORDER_COLORS[1] }}>
          <div className={styles.metricLabel}>总Token消耗</div>
          <div className={styles.metricValue}>
            {formatTokens(metricData.totalTokens)}
          </div>
          <div
            className={`${styles.metricChange} ${
              metricData.tokensGrowth > 0 ? styles.positive : styles.negative
            }`}
          >
            {formatChange(metricData.tokensGrowth)} 环比
          </div>
        </div>
        <div className={styles.metricCard} style={{ borderLeftColor: METRIC_BORDER_COLORS[2] }}>
          <div className={styles.metricLabel}>总使用用户</div>
          <div className={styles.metricValue}>
            {formatNumber(platformData.totalUsers)}
          </div>
          <div
            className={`${styles.metricChange} ${
              platformData.userGrowth > 0 ? styles.positive : styles.negative
            }`}
          >
            {formatChange(platformData.userGrowth)} 环比
          </div>
        </div>
        <div className={styles.metricCard} style={{ borderLeftColor: METRIC_BORDER_COLORS[3] }}>
          <div className={styles.metricLabel}>接入平台数</div>
          <div className={styles.metricValue}>
            {formatNumber(platformData.totalPlatforms)}
          </div>
          <div
            className={`${styles.metricChange} ${
              platformData.platformGrowth > 0 ? styles.positive : styles.negative
            }`}
          >
            {formatChange(platformData.platformGrowth)} 环比
          </div>
        </div>
      </div>

      <div className={styles.trendCard}>
        <div className={styles.trendHeader}>
          <h3 className={styles.trendTitle}>{getTrendTitle()}</h3>
          <div className={styles.trendLegend}>
            <span className={styles.legendItem}>
              <span
                className={styles.legendLine}
                style={{ background: "#1890ff" }}
              />
              调用次数
            </span>
            <span className={styles.legendItem}>
              <span
                className={styles.legendLine}
                style={{ background: "#52c41a" }}
              />
              Token消耗
            </span>
            <span className={styles.legendItem}>
              <span
                className={styles.legendLine}
                style={{ background: "#faad14" }}
              />
              用户数
            </span>
          </div>
        </div>
        {renderLineChart(trendData)}
      </div>

      {/* 热门技能和工具 */}
      <Row gutter={[16, 16]} className={styles.skillRow}>
        <Col xs={24} lg={12}>
          <div className={styles.skillCard}>
            <div className={styles.cardTitle}>热门技能 Top5</div>
            {renderBarChart(
              (overviewStats?.top_skills || []).slice(0, 5).map((s: any) => ({
                name: s.skill_name,
                value: s.count
              })),
            )}
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className={styles.skillCard}>
            <div className={styles.cardTitle}>热门MCP服务 Top5</div>
            {renderBarChart(
              (overviewStats?.mcp_servers || []).slice(0, 5).map((s: any) => ({
                name: s.server_name,
                value: s.total_calls
              })),
            )}
          </div>
        </Col>
      </Row>

      {/* ==================== 模型使用分布 ==================== */}
      <Row gutter={[16, 16]} className={styles.modelRow}>
        <Col xs={24} lg={12}>
          <div className={styles.distributionCard}>
            <div className={styles.cardTitle}>模型使用分布</div>
            {renderPieChart(
              (overviewStats?.model_distribution || []).map((m: any) => ({
                name: truncateName(m.model_name, 11),
                fullName: m.model_name,
                value: m.count
              })),
            )}
            {renderLegend(
              (overviewStats?.model_distribution || []).map((m: any) => ({
                name: truncateName(m.model_name, 15),
                fullName: m.model_name,
                value: m.count
              })),
            )}
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className={styles.distributionCard}>
            <div className={styles.cardTitle}>各模型Token消耗</div>
            {renderBarChart(
              (overviewStats?.model_distribution || [])
                .sort((a: any, b: any) => b.total_tokens - a.total_tokens)
                .slice(0, 5)
                .map((m: any) => ({
                  name: m.model_name,
                  value: m.total_tokens
                })),
              260,
            )}
          </div>
        </Col>
      </Row>

      {/* ==================== 第二屏：用户分析 ==================== */}
      <div className={styles.sectionTitle}>
        <span>用户分析</span>
      </div>

      {/* 核心指标卡片 */}
      <Row gutter={[16, 16]} className={styles.statCardRow}>
        <Col xs={24} sm={12} lg={12}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>
              <span className={styles.icon} style={{ background: "#1890ff15", color: "#1890ff" }}>
                <Users size={18} />
              </span>
              <span>总会话数</span>
            </div>
            <div className={styles.statValue}>{formatNumber(metricData.sessionCount)}</div>
            <div
              className={`${styles.statChange} ${
                metricData.sessionGrowth > 0 ? styles.positive : styles.negative
              }`}
            >
              {metricData.sessionGrowth > 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              <span>{formatChange(metricData.sessionGrowth)}</span>
              <span style={{ marginLeft: 4, color: "#999", fontWeight: 400 }}>环比</span>
            </div>
          </div>
        </Col>
        <Col xs={24} sm={12} lg={12}>
          <div className={styles.statCard}>
            <div className={styles.statLabel}>
              <span className={styles.icon} style={{ background: "#52c41a15", color: "#52c41a" }}>
                <Clock size={18} />
              </span>
              <span>平均会话时长</span>
            </div>
            <div className={styles.statValue}>
              {Number(metricData.avgDuration).toFixed(1)}
              <span className={styles.suffix}>s</span>
            </div>
          </div>
        </Col>
      </Row>

      {/* 分布图 + 用户排行榜 */}
      <Row gutter={[16, 16]} className={styles.distributionRow}>
        <Col xs={24} lg={12}>
          <div className={styles.distributionCard}>
            <div className={styles.cardTitle}>平台用户分布{platform !== "all" ? ` · ${getPlatformDisplayName(platform)}` : ""}</div>
            {renderPieChart(platformData.platformUserDistribution.map(item => ({
              name: getPlatformDisplayName(item.name),
              fullName: getPlatformDisplayName(item.name),
              value: item.value,
            })))}
            {renderLegend(platformData.platformUserDistribution.map(item => ({
              name: getPlatformDisplayName(item.name),
              fullName: getPlatformDisplayName(item.name),
              value: item.value,
            })))}
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className={styles.distributionCard}>
            <div className={styles.cardTitle}>平台调用次数分布{platform !== "all" ? ` · ${getPlatformDisplayName(platform)}` : ""}</div>
            {renderPieChart(platformData.platformCallDistribution.map(item => ({
              name: getPlatformDisplayName(item.name),
              fullName: getPlatformDisplayName(item.name),
              value: item.value,
            })))}
            {renderLegend(platformData.platformCallDistribution.map(item => ({
              name: getPlatformDisplayName(item.name),
              fullName: getPlatformDisplayName(item.name),
              value: item.value,
            })))}
          </div>
        </Col>
      </Row>

      {/* 用户排行榜 */}
      <Row gutter={[16, 16]} className={styles.userRow}>
        <Col xs={24} lg={12}>
          <div className={styles.userCard}>
            <div className={styles.cardTitle}>调用数 Top5</div>
            {renderUserList(
              [...topUsers].sort((a, b) => b.calls - a.calls).slice(0, 5),
              "calls",
            )}
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className={styles.userCard}>
            <div className={styles.cardTitle}>最近活跃 Top5</div>
            {renderUserList(
              [...topUsers]
                .sort((a, b) => new Date(b.lastActive).getTime() - new Date(a.lastActive).getTime())
                .slice(0, 5),
              "lastActive",
            )}
          </div>
        </Col>
      </Row>
    </div>
  );
}
