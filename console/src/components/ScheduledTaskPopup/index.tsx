import { useState, useCallback, useMemo } from "react";
import { Modal, Tooltip } from "antd";
import { useAppMessage } from "../../hooks/useAppMessage";
import {
  FrequencyType,
  ScheduleConfig,
  WEEKDAY_LABELS,
  validateHour,
  validateMinute,
  formatTimeValue,
  formatNextRunPreview,
  generateCronExpression,
  hasDateBoundaryWarning,
} from "../../utils/cron";
import styles from "./index.module.less";

export interface ScheduledTaskPopupProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (cronExpression: string, config: ScheduleConfig) => Promise<void>;
  onSuccess?: () => void;
  caseValue?: string;
}

interface TimeState {
  hour: number;
  minute: number;
}

const DEFAULT_TIME: TimeState = { hour: 9, minute: 0 };
const DEFAULT_WEEKDAYS = [1];
const DEFAULT_DATES = [1];

export default function ScheduledTaskPopup({
  open,
  onClose,
  onConfirm,
  onSuccess,
  caseValue,
}: ScheduledTaskPopupProps) {
  const { message } = useAppMessage();
  const [frequency, setFrequency] = useState<FrequencyType>("daily");
  const [time, setTime] = useState<TimeState>(DEFAULT_TIME);
  const [weekdays, setWeekdays] = useState<number[]>(DEFAULT_WEEKDAYS);
  const [dates, setDates] = useState<number[]>(DEFAULT_DATES);
  const [loading, setLoading] = useState(false);
  // 临时输入值，允许用户自由编辑
  const [hourInput, setHourInput] = useState<string>(formatTimeValue(DEFAULT_TIME.hour));
  const [minuteInput, setMinuteInput] = useState<string>(formatTimeValue(DEFAULT_TIME.minute));

  const handleFrequencyChange = useCallback((newFrequency: FrequencyType) => {
    setFrequency(newFrequency);
    setTime(DEFAULT_TIME);
    setHourInput(formatTimeValue(DEFAULT_TIME.hour));
    setMinuteInput(formatTimeValue(DEFAULT_TIME.minute));
    if (newFrequency === "weekly") {
      setWeekdays(DEFAULT_WEEKDAYS);
    } else if (newFrequency === "monthly") {
      setDates(DEFAULT_DATES);
    }
  }, []);

  const handleHourInputChange = useCallback((value: string) => {
    // 允许用户自由输入，只过滤非数字字符
    const filtered = value.replace(/[^\d]/g, "");
    setHourInput(filtered);
  }, []);

  const handleMinuteInputChange = useCallback((value: string) => {
    // 允许用户自由输入，只过滤非数字字符
    const filtered = value.replace(/[^\d]/g, "");
    setMinuteInput(filtered);
  }, []);

  const handleHourInputBlur = useCallback(() => {
    // blur 时校验并格式化
    const hour = validateHour(hourInput);
    setTime((prev) => ({ ...prev, hour }));
    setHourInput(formatTimeValue(hour));
  }, [hourInput]);

  const handleMinuteInputBlur = useCallback(() => {
    // blur 时校验并格式化
    const minute = validateMinute(minuteInput);
    setTime((prev) => ({ ...prev, minute }));
    setMinuteInput(formatTimeValue(minute));
  }, [minuteInput]);

  const toggleWeekday = useCallback((day: number) => {
    setWeekdays((prev) => {
      if (prev.includes(day)) {
        if (prev.length === 1) return prev;
        return prev.filter((d) => d !== day);
      }
      return [...prev, day].sort((a, b) => a - b);
    });
  }, []);

  const toggleDate = useCallback((date: number) => {
    setDates((prev) => {
      if (prev.includes(date)) {
        if (prev.length === 1) return prev;
        return prev.filter((d) => d !== date);
      }
      return [...prev, date].sort((a, b) => a - b);
    });
  }, []);

  const scheduleConfig: ScheduleConfig = useMemo(() => {
    return {
      frequency,
      hour: time.hour,
      minute: time.minute,
      weekdays: frequency === "weekly" ? weekdays : undefined,
      dates: frequency === "monthly" ? dates : undefined,
    };
  }, [frequency, time, weekdays, dates]);

  const previewText = useMemo(() => {
    try {
      return formatNextRunPreview(scheduleConfig);
    } catch {
      return "";
    }
  }, [scheduleConfig]);

  const isConfirmDisabled = useMemo(() => {
    if (frequency === "weekly" && weekdays.length === 0) return true;
    if (frequency === "monthly" && dates.length === 0) return true;
    return false;
  }, [frequency, weekdays, dates]);

  const showDateWarning = useMemo(() => {
    return frequency === "monthly" && hasDateBoundaryWarning(dates);
  }, [frequency, dates]);

  const handleConfirm = useCallback(async () => {
    if (isConfirmDisabled) return;

    setLoading(true);
    try {
      const cronExpression = generateCronExpression(scheduleConfig);
      await onConfirm(cronExpression, scheduleConfig);
      message.success("定时任务创建成功");
      onClose();
      onSuccess?.();
    } catch (error) {
      message.error("创建失败，请重试");
    } finally {
      setLoading(false);
    }
  }, [isConfirmDisabled, scheduleConfig, onConfirm, message, onClose, onSuccess]);

  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);

  return (
    <Modal
      open={open}
      onCancel={handleClose}
      footer={null}
      width={400}
      centered
      closable={false}
      className={styles.modal}
      styles={{
        body: { padding: 0 },
      }}
    >
      <div className={styles.header}>
        <span className={styles.title}>定时设置</span>
        <button className={styles.closeBtn} onClick={handleClose} type="button">
          ✕
        </button>
      </div>

      <div className={styles.body}>
        <div className={styles.section}>
          <label className={styles.label}>执行频次</label>
          <div className={styles.tabs}>
            <button
              className={`${styles.tab} ${frequency === "daily" ? styles.tabActive : ""}`}
              onClick={() => handleFrequencyChange("daily")}
              type="button"
            >
              每天
            </button>
            <button
              className={`${styles.tab} ${frequency === "weekly" ? styles.tabActive : ""}`}
              onClick={() => handleFrequencyChange("weekly")}
              type="button"
            >
              每周
            </button>
            <button
              className={`${styles.tab} ${frequency === "monthly" ? styles.tabActive : ""}`}
              onClick={() => handleFrequencyChange("monthly")}
              type="button"
            >
              每月
            </button>
          </div>
        </div>

        {frequency === "weekly" && (
          <div className={styles.section}>
            <label className={styles.label}>选择星期</label>
            <div className={styles.weekdayGrid}>
              {WEEKDAY_LABELS.map((label, index) => {
                const dayNum = index === 6 ? 0 : index + 1;
                const isSelected = weekdays.includes(dayNum);
                return (
                  <button
                    key={label}
                    className={`${styles.weekdayItem} ${isSelected ? styles.weekdaySelected : ""}`}
                    onClick={() => toggleWeekday(dayNum)}
                    type="button"
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {frequency === "monthly" && (
          <div className={styles.section}>
            <label className={styles.label}>选择日期</label>
            <div className={styles.dateGrid}>
              {Array.from({ length: 31 }, (_, i) => i + 1).map((date) => {
                const isSelected = dates.includes(date);
                return (
                  <button
                    key={date}
                    className={`${styles.dateItem} ${isSelected ? styles.dateSelected : ""}`}
                    onClick={() => toggleDate(date)}
                    type="button"
                  >
                    {date}
                  </button>
                );
              })}
            </div>
            {showDateWarning && (
              <Tooltip title="部分月份不存在该日期，将顺延至当月最后一天执行">
                <span className={styles.dateWarning}>⚠️ 29/30/31日可能不存在</span>
              </Tooltip>
            )}
          </div>
        )}

        <div className={styles.section}>
          <label className={styles.label}>选择时间</label>
          <div className={styles.timePicker}>
            <input
              className={styles.timeInput}
              type="text"
              value={hourInput}
              onChange={(e) => handleHourInputChange(e.target.value)}
              onBlur={handleHourInputBlur}
              maxLength={2}
            />
            <span className={styles.timeUnit}>时</span>
            <span className={styles.timeSeparator}>:</span>
            <input
              className={styles.timeInput}
              type="text"
              value={minuteInput}
              onChange={(e) => handleMinuteInputChange(e.target.value)}
              onBlur={handleMinuteInputBlur}
              maxLength={2}
            />
            <span className={styles.timeUnit}>分</span>
          </div>
        </div>

        {previewText && (
          <div className={styles.preview}>
            <p className={styles.previewText}>
              📌 <span className={styles.previewHighlight}>{previewText}</span>
            </p>
          </div>
        )}
      </div>

      <div className={styles.footer}>
        <button
          className={styles.btnCancel}
          onClick={handleClose}
          type="button"
          disabled={loading}
        >
          取消
        </button>
        <button
          className={styles.btnConfirm}
          onClick={handleConfirm}
          type="button"
          disabled={isConfirmDisabled || loading}
        >
          {loading ? "创建中..." : "确认"}
        </button>
      </div>
    </Modal>
  );
}