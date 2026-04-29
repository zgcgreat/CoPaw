import dayjs from "dayjs";

export type FrequencyType = "daily" | "weekly" | "monthly";

export interface ScheduleConfig {
  frequency: FrequencyType;
  hour: number;
  minute: number;
  weekdays?: number[];
  dates?: number[];
}

export const WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];

export const WEEKDAY_MAP: Record<string, number> = {
  "一": 1,
  "二": 2,
  "三": 3,
  "四": 4,
  "五": 5,
  "六": 6,
  "日": 0,
};

export const CRON_WEEKDAY_MAP: Record<string, number> = {
  "一": 1,
  "二": 2,
  "三": 3,
  "四": 4,
  "五": 5,
  "六": 6,
  "日": 7,
};

export function weekdayLabelToNumber(label: string, useCronStandard = false): number {
  const map = useCronStandard ? CRON_WEEKDAY_MAP : WEEKDAY_MAP;
  return map[label] ?? 0;
}

export function weekdayNumberToLabel(num: number): string {
  if (num === 0 || num === 7) return "日";
  return WEEKDAY_LABELS[num - 1] ?? "";
}

export function generateCronExpression(config: ScheduleConfig): string {
  const { frequency, hour, minute, weekdays, dates } = config;
  const paddedMinute = minute.toString().padStart(2, "0");
  const paddedHour = hour.toString().padStart(2, "0");

  switch (frequency) {
    case "daily":
      return `${paddedMinute} ${paddedHour} * * *`;
    case "weekly":
      if (!weekdays || weekdays.length === 0) {
        throw new Error("Weekly frequency requires at least one weekday");
      }
      const weekdayStr = weekdays
        .map((w) => (w === 0 ? 7 : w))
        .sort((a, b) => a - b)
        .join(",");
      return `${paddedMinute} ${paddedHour} * * ${weekdayStr}`;
    case "monthly":
      if (!dates || dates.length === 0) {
        throw new Error("Monthly frequency requires at least one date");
      }
      const dateStr = dates.sort((a, b) => a - b).join(",");
      return `${paddedMinute} ${paddedHour} ${dateStr} * *`;
    default:
      throw new Error(`Unknown frequency type: ${frequency}`);
  }
}

export function validateHour(value: string | number): number {
  const num = typeof value === "string" ? parseInt(value, 10) : value;
  if (isNaN(num) || num < 0) return 0;
  if (num > 23) return 23;
  return num;
}

export function validateMinute(value: string | number): number {
  const num = typeof value === "string" ? parseInt(value, 10) : value;
  if (isNaN(num) || num < 0) return 0;
  if (num > 59) return 59;
  return num;
}

export function formatTimeValue(value: number): string {
  return value.toString().padStart(2, "0");
}

export function parseTimeString(timeStr: string): { hour: number; minute: number } {
  const parts = timeStr.split(":");
  if (parts.length !== 2) {
    return { hour: 9, minute: 0 };
  }
  return {
    hour: validateHour(parts[0]),
    minute: validateMinute(parts[1]),
  };
}

export function calculateNextRun(config: ScheduleConfig): dayjs.Dayjs {
  const now = dayjs();
  const { frequency, hour, minute, weekdays, dates } = config;

  const targetTime = now.hour(hour).minute(minute).second(0).millisecond(0);

  switch (frequency) {
    case "daily":
      if (targetTime.isAfter(now)) {
        return targetTime;
      }
      return targetTime.add(1, "day");

    case "weekly":
      if (!weekdays || weekdays.length === 0) {
        return now.add(1, "day");
      }
      const sortedWeekdays = weekdays
        .map((w) => (w === 0 ? 7 : w))
        .sort((a, b) => a - b);

      for (const wd of sortedWeekdays) {
        const targetDay = wd === 7 ? 0 : wd;
        let candidate = targetTime.day(targetDay);
        if (candidate.isAfter(now)) {
          return candidate;
        }
      }
      return targetTime.day(sortedWeekdays[0] === 7 ? 0 : sortedWeekdays[0]).add(7, "day");

    case "monthly":
      if (!dates || dates.length === 0) {
        return now.add(1, "month");
      }
      const sortedDates = dates.sort((a, b) => a - b);
      const currentDayOfMonth = now.date();

      for (const d of sortedDates) {
        if (d > currentDayOfMonth) {
          return targetTime.date(d);
        }
      }
      return targetTime.date(sortedDates[0]).add(1, "month");

    default:
      return now.add(1, "day");
  }
}

export function formatNextRunPreview(config: ScheduleConfig): string {
  const nextRun = calculateNextRun(config);
  const { frequency, weekdays, dates } = config;

  const timeStr = nextRun.format("HH:mm");
  let patternStr = "";

  switch (frequency) {
    case "daily":
      patternStr = "每天自动执行";
      break;
    case "weekly":
      if (!weekdays || weekdays.length === 0) break;
      const wdLabels = weekdays
        .sort((a, b) => a - b)
        .map((w) => weekdayNumberToLabel(w));
      patternStr = `每周${wdLabels.join("")}执行`;
      break;
    case "monthly":
      if (!dates || dates.length === 0) break;
      const dateLabels = dates.sort((a, b) => a - b).map((d) => `${d}日`);
      patternStr = `每月${dateLabels.join("、")}执行`;
      break;
  }

  let nextRunStr = "";
  if (frequency === "monthly" && dates && dates.length > 0) {
    const nextDate = nextRun.date();
    nextRunStr = `下月${nextDate}日 ${timeStr} 首次执行`;
  } else if (frequency === "weekly") {
    const nextWeekday = weekdayNumberToLabel(nextRun.day() === 0 ? 7 : nextRun.day());
    if (nextRun.isAfter(dayjs().add(7, "day"))) {
      nextRunStr = `下周${nextWeekday} ${timeStr} 首次执行`;
    } else {
      nextRunStr = `本周${nextWeekday} ${timeStr} 首次执行`;
    }
  } else {
    if (nextRun.isAfter(dayjs().add(1, "day"))) {
      nextRunStr = `明天 ${timeStr} 首次执行`;
    } else {
      nextRunStr = `今天 ${timeStr} 首次执行`;
    }
  }

  return `${nextRunStr}，${patternStr}`;
}

export function hasDateBoundaryWarning(dates: number[]): boolean {
  return dates.some((d) => d >= 29);
}

export interface CreateScheduledTaskOptions {
  cronExpression: string;
  name: string;
  userId: string;
  sessionId?: string;
  caseValue: string;
  channel?: string;
}

export function buildCronJobSpec(options: CreateScheduledTaskOptions): import("../api/types/cronjob").CronJobSpecInput {
  const { cronExpression, name, userId, sessionId, caseValue, channel } = options;

  return {
    id: `${name}-${Date.now()}`,
    name,
    enabled: true,
    schedule: {
      type: "cron",
      cron: cronExpression,
    },
    task_type: "agent",
    request: {
      input: [
        {
          role: "user",
          type: "message",
          content: [
            { type: "text", text: caseValue }
          ]
        }
      ],
      session_id: sessionId,
      user_id: userId,
    },
    dispatch: {
      type: "channel",
      channel: channel || "default",
      target: {
        user_id: userId,
        session_id: sessionId || "",
      },
      mode: "final",
    },
    meta: {
      creator_user_id: userId,
    },
  };
}