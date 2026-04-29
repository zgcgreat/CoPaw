import React from "react";
import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import ScheduledTaskPopup from ".";
import type { ScheduleConfig } from "@/utils/cron";

const mocks = vi.hoisted(() => ({
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({ message: mocks.message }),
}));

describe("ScheduledTaskPopup", () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onConfirm: vi.fn().mockResolvedValue(undefined),
    caseValue: "测试任务",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders modal when open", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      expect(screen.getByText("定时设置")).toBeInTheDocument();
      expect(screen.getAllByText("每天")[0]).toBeInTheDocument();
      expect(screen.getAllByText("每周")[0]).toBeInTheDocument();
      expect(screen.getAllByText("每月")[0]).toBeInTheDocument();
    });

    it("renders time picker inputs", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const inputs = screen.getAllByRole("textbox");
      expect(inputs.length).toBe(2);
    });

    it("renders cancel and confirm buttons", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const cancelBtns = screen.getAllByText("取消");
      const confirmBtns = screen.getAllByText("确认");
      expect(cancelBtns.length).toBeGreaterThan(0);
      expect(confirmBtns.length).toBeGreaterThan(0);
    });
  });

  describe("Frequency tab switching", () => {
    it("shows daily tab as active by default", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const dailyTabs = screen.getAllByText("每天");
      const activeTab = dailyTabs.find((el) =>
        el.closest("button")?.className.includes("tabActive")
      );
      expect(activeTab).toBeTruthy();
    });

    it("switches to weekly mode and shows weekday selector", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const weeklyTabs = screen.getAllByText("每周");
      fireEvent.click(weeklyTabs[0]);

      expect(screen.getByText("选择星期")).toBeInTheDocument();
      expect(screen.getByText("一")).toBeInTheDocument();
      expect(screen.getByText("日")).toBeInTheDocument();
    });

    it("switches to monthly mode and shows date selector", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const monthlyTabs = screen.getAllByText("每月");
      fireEvent.click(monthlyTabs[0]);

      expect(screen.getByText("选择日期")).toBeInTheDocument();
      expect(screen.getByText("1")).toBeInTheDocument();
      expect(screen.getByText("31")).toBeInTheDocument();
    });

    it("resets settings when switching frequency", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);

      // Switch to weekly and select a weekday
      const weeklyTabs = screen.getAllByText("每周");
      fireEvent.click(weeklyTabs[0]);
      fireEvent.click(screen.getByText("三"));

      // Switch back to daily
      const dailyTabs = screen.getAllByText("每天");
      fireEvent.click(dailyTabs[0]);

      // Switch to weekly again - should have default selection (Monday)
      fireEvent.click(weeklyTabs[0]);
      const mondayBtn = screen.getAllByText("一").find((el) => el.closest("button"));
      expect(mondayBtn?.closest("button")?.className.includes("weekdaySelected")).toBe(true);
    });
  });

  describe("Time input validation", () => {
    it("validates hour on blur (clamps to 23)", async () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];

      fireEvent.change(inputs[0], { target: { value: "25" } });
      fireEvent.blur(inputs[0]);

      await waitFor(() => {
        expect(inputs[0].value).toBe("23");
      });
    });

    it("validates minute on blur (clamps to 59)", async () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];

      fireEvent.change(inputs[1], { target: { value: "99" } });
      fireEvent.blur(inputs[1]);

      await waitFor(() => {
        expect(inputs[1].value).toBe("59");
      });
    });

    it("pads single digit with zero on blur", async () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];

      fireEvent.change(inputs[0], { target: { value: "9" } });
      fireEvent.blur(inputs[0]);

      await waitFor(() => {
        expect(inputs[0].value).toBe("09");
      });
    });

    it("handles invalid input gracefully", async () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];

      fireEvent.change(inputs[0], { target: { value: "abc" } });
      fireEvent.blur(inputs[0]);

      await waitFor(() => {
        // Should default to 0 when invalid
        expect(inputs[0].value).toBe("00");
      });
    });
  });

  describe("Weekday multi-select behavior", () => {
    it("selects weekday on click", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const weeklyTabs = screen.getAllByText("每周");
      fireEvent.click(weeklyTabs[0]);

      const wednesdayBtn = screen.getAllByText("三").find((el) => el.closest("button"));
      fireEvent.click(wednesdayBtn!);

      expect(wednesdayBtn?.closest("button")?.className.includes("weekdaySelected")).toBe(true);
    });

    it("toggles weekday selection off", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const weeklyTabs = screen.getAllByText("每周");
      fireEvent.click(weeklyTabs[0]);

      // Monday is selected by default
      const mondayBtn = screen.getAllByText("一").find((el) => el.closest("button"));
      expect(mondayBtn?.closest("button")?.className.includes("weekdaySelected")).toBe(true);

      // Select Wednesday
      const wednesdayBtn = screen.getAllByText("三").find((el) => el.closest("button"));
      fireEvent.click(wednesdayBtn!);

      // Deselect Monday
      fireEvent.click(mondayBtn!);
      expect(mondayBtn?.closest("button")?.className.includes("weekdaySelected")).toBe(false);
    });

    it("prevents deselecting last remaining weekday", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const weeklyTabs = screen.getAllByText("每周");
      fireEvent.click(weeklyTabs[0]);

      // Only Monday is selected by default
      const mondayBtn = screen.getAllByText("一").find((el) => el.closest("button"));

      // Try to deselect Monday - should remain selected
      fireEvent.click(mondayBtn!);
      expect(mondayBtn?.closest("button")?.className.includes("weekdaySelected")).toBe(true);
    });

    it("allows selecting multiple weekdays", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const weeklyTabs = screen.getAllByText("每周");
      fireEvent.click(weeklyTabs[0]);

      fireEvent.click(screen.getAllByText("三").find((el) => el.closest("button"))!);
      fireEvent.click(screen.getAllByText("五").find((el) => el.closest("button"))!);

      expect(screen.getAllByText("一").find((el) => el.closest("button"))?.closest("button")?.className.includes("weekdaySelected")).toBe(true);
      expect(screen.getAllByText("三").find((el) => el.closest("button"))?.closest("button")?.className.includes("weekdaySelected")).toBe(true);
      expect(screen.getAllByText("五").find((el) => el.closest("button"))?.closest("button")?.className.includes("weekdaySelected")).toBe(true);
    });
  });

  describe("Date multi-select behavior", () => {
    it("selects date on click", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const monthlyTabs = screen.getAllByText("每月");
      fireEvent.click(monthlyTabs[0]);

      const date15Btn = screen.getAllByText("15").find((el) => el.closest("button"));
      fireEvent.click(date15Btn!);

      expect(date15Btn?.closest("button")?.className.includes("dateSelected")).toBe(true);
    });

    it("toggles date selection off", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const monthlyTabs = screen.getAllByText("每月");
      fireEvent.click(monthlyTabs[0]);

      // Date 1 is selected by default
      const date1Btn = screen.getAllByText("1").find((el) => el.closest("button"));
      expect(date1Btn?.closest("button")?.className.includes("dateSelected")).toBe(true);

      // Select date 15
      const date15Btn = screen.getAllByText("15").find((el) => el.closest("button"));
      fireEvent.click(date15Btn!);

      // Deselect date 1
      fireEvent.click(date1Btn!);
      expect(date1Btn?.closest("button")?.className.includes("dateSelected")).toBe(false);
    });

    it("prevents deselecting last remaining date", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const monthlyTabs = screen.getAllByText("每月");
      fireEvent.click(monthlyTabs[0]);

      // Only date 1 is selected by default
      const date1Btn = screen.getAllByText("1").find((el) => el.closest("button"));

      // Try to deselect date 1 - should remain selected
      fireEvent.click(date1Btn!);
      expect(date1Btn?.closest("button")?.className.includes("dateSelected")).toBe(true);
    });

    it("shows warning when selecting dates 29-31", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const monthlyTabs = screen.getAllByText("每月");
      fireEvent.click(monthlyTabs[0]);

      fireEvent.click(screen.getAllByText("31").find((el) => el.closest("button"))!);

      expect(screen.getByText(/29\/30\/31日可能不存在/)).toBeInTheDocument();
    });
  });

  describe("Cron expression generation", () => {
    it("generates daily cron expression", async () => {
      const onConfirm = vi.fn().mockResolvedValue(undefined);
      render(<ScheduledTaskPopup {...defaultProps} onConfirm={onConfirm} />);

      fireEvent.click(screen.getAllByText("确认")[0]);

      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalled();
        const [cronExpr, config] = onConfirm.mock.calls[0];
        expect(cronExpr).toMatch(/^\d{2} \d{2} \* \* \*$/);
        expect(config.frequency).toBe("daily");
      });
    });

    it("generates weekly cron expression", async () => {
      const onConfirm = vi.fn().mockResolvedValue(undefined);
      render(<ScheduledTaskPopup {...defaultProps} onConfirm={onConfirm} />);

      fireEvent.click(screen.getAllByText("每周")[0]);
      fireEvent.click(screen.getAllByText("三").find((el) => el.closest("button"))!);
      fireEvent.click(screen.getAllByText("确认")[0]);

      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalled();
        const [cronExpr, config] = onConfirm.mock.calls[0];
        expect(cronExpr).toMatch(/^\d{2} \d{2} \* \* [\d,]+$/);
        expect(config.frequency).toBe("weekly");
        expect(config.weekdays).toContain(1);
        expect(config.weekdays).toContain(3);
      });
    });

    it("generates monthly cron expression", async () => {
      const onConfirm = vi.fn().mockResolvedValue(undefined);
      render(<ScheduledTaskPopup {...defaultProps} onConfirm={onConfirm} />);

      fireEvent.click(screen.getAllByText("每月")[0]);
      fireEvent.click(screen.getAllByText("15").find((el) => el.closest("button"))!);
      fireEvent.click(screen.getAllByText("确认")[0]);

      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalled();
        const [cronExpr, config] = onConfirm.mock.calls[0];
        expect(cronExpr).toMatch(/^\d{2} \d{2} [\d,]+ \* \*$/);
        expect(config.frequency).toBe("monthly");
        expect(config.dates).toContain(1);
        expect(config.dates).toContain(15);
      });
    });
  });

  describe("Confirm button enable/disable logic", () => {
    it("confirm button is enabled for daily mode by default", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      const confirmBtns = screen.getAllByText("确认").filter((el) => el.closest("button"));
      expect(confirmBtns[0]?.closest("button")?.hasAttribute("disabled")).toBe(false);
    });

    it("confirm button is enabled when weekdays are selected", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      fireEvent.click(screen.getAllByText("每周")[0]);

      const confirmBtns = screen.getAllByText("确认").filter((el) => el.closest("button"));
      expect(confirmBtns[0]?.closest("button")?.hasAttribute("disabled")).toBe(false);
    });

    it("confirm button is enabled when dates are selected", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      fireEvent.click(screen.getAllByText("每月")[0]);

      const confirmBtns = screen.getAllByText("确认").filter((el) => el.closest("button"));
      expect(confirmBtns[0]?.closest("button")?.hasAttribute("disabled")).toBe(false);
    });

    it("shows loading state during API call", async () => {
      const slowConfirm = vi.fn().mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      );
      render(<ScheduledTaskPopup {...defaultProps} onConfirm={slowConfirm} />);

      fireEvent.click(screen.getAllByText("确认")[0]);

      await waitFor(() => {
        expect(screen.getByText("创建中...")).toBeInTheDocument();
      });

      await waitFor(() => {
        expect(screen.getAllByText("确认").length).toBeGreaterThan(0);
      });
    });
  });

  describe("Close handlers", () => {
    it("closes on cancel button click", () => {
      const onClose = vi.fn();
      render(<ScheduledTaskPopup {...defaultProps} onClose={onClose} />);

      fireEvent.click(screen.getAllByText("取消")[0]);
      expect(onClose).toHaveBeenCalled();
    });

    it("closes on close button click", () => {
      const onClose = vi.fn();
      render(<ScheduledTaskPopup {...defaultProps} onClose={onClose} />);

      fireEvent.click(screen.getByText("✕"));
      expect(onClose).toHaveBeenCalled();
    });

    it("calls onConfirm and closes on successful confirm", async () => {
      const onClose = vi.fn();
      const onConfirm = vi.fn().mockResolvedValue(undefined);

      render(<ScheduledTaskPopup {...defaultProps} onClose={onClose} onConfirm={onConfirm} />);

      fireEvent.click(screen.getAllByText("确认")[0]);

      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
        expect(mocks.message.success).toHaveBeenCalledWith("定时任务创建成功");
      });
    });

    it("shows error message on failed confirm", async () => {
      const onConfirm = vi.fn().mockRejectedValue(new Error("API error"));

      render(<ScheduledTaskPopup {...defaultProps} onConfirm={onConfirm} />);

      fireEvent.click(screen.getAllByText("确认")[0]);

      await waitFor(() => {
        expect(mocks.message.error).toHaveBeenCalledWith("创建失败，请重试");
      });
    });
  });

  describe("Preview section", () => {
    it("shows preview for daily frequency", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);

      expect(screen.getByText(/首次执行/)).toBeInTheDocument();
      expect(screen.getByText(/每天自动执行/)).toBeInTheDocument();
    });

    it("shows preview for weekly frequency", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      fireEvent.click(screen.getAllByText("每周")[0]);
      fireEvent.click(screen.getAllByText("三").find((el) => el.closest("button"))!);
      fireEvent.click(screen.getAllByText("五").find((el) => el.closest("button"))!);

      expect(screen.getByText(/每周一三五执行/)).toBeInTheDocument();
    });

    it("shows preview for monthly frequency", () => {
      render(<ScheduledTaskPopup {...defaultProps} />);
      fireEvent.click(screen.getAllByText("每月")[0]);
      fireEvent.click(screen.getAllByText("15").find((el) => el.closest("button"))!);

      expect(screen.getByText(/每月1日、15日执行/)).toBeInTheDocument();
    });
  });
});