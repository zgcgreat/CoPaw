## Context

The CaseDetailDrawer component (`console/src/components/agentscope-chat/CaseDetailDrawer/index.tsx`) contains a "订阅为定时任务" button with a TODO placeholder. Users need a way to configure scheduled execution frequency when subscribing to a case as a recurring task.

The existing cronjob system (`console/src/api/types/cronjob.ts`) already supports:
- `CronJobSchedule` with `type: "cron"` and `cron` expression
- `CronJobDispatch` for channel-based dispatch
- `CronJobSpecInput` for creating new jobs

The popup will generate cron expressions from user-friendly inputs (frequency tabs, weekday/date selectors, time pickers) matching the design at `/Users/darinzanya/Documents/popup.html`.

## Goals / Non-Goals

**Goals:**
- Implement a modal popup for scheduled task configuration with three frequency modes (daily/weekly/monthly)
- Generate valid cron expressions from user selections
- Integrate with existing cronjob API for task creation
- Provide real-time preview of next execution time
- Handle edge cases (weekday/date boundary validation, time format validation)

**Non-Goals:**
- Backend changes (cronjob API already supports cron expressions)
- Mobile responsiveness (design is PC-focused per spec)
- Complex timezone handling (use server timezone or default)
- Cron expression parsing/editing (only generation from UI)

## Decisions

### 1. Component Location
**Decision:** Create `ScheduledTaskPopup` as a standalone component in `console/src/components/ScheduledTaskPopup/`

**Rationale:** Separation from CaseDetailDrawer enables reuse (e.g., sidebar task list could use it for editing). Matches existing pattern (ConsoleCronBubble, TenantTargetPicker are standalone).

**Alternatives:**
- Inline in CaseDetailDrawer: harder to maintain, no reuse potential
- In agentscope-chat folder: tight coupling to chat context

### 2. State Management
**Decision:** Local state with React hooks (`useState`) for frequency, time, weekdays, dates

**Rationale:** Simple form state, no cross-component sharing needed. Parent passes `onConfirm` callback.

**Alternatives:**
- Global state (Redux/Context): unnecessary complexity
- Form library (Formik/RCK): overkill for 3-4 inputs

### 3. Cron Expression Generation
**Decision:** Utility function in `utils/cron.ts` for expression generation and next-run calculation

**Rationale:** Pure function, easy to test, reusable. Format: `0 [min] [hour] [day] * [weekday]`

**Alternatives:**
- Inline generation: harder to test, no reuse
- External library: adds dependency, but could use `cron-validator` for validation

### 4. Preview Calculation
**Decision:** Calculate next run time client-side using dayjs

**Rationale:** Instant feedback, no API calls. Simple calculation based on current time + cron pattern.

**Alternatives:**
- Server-side preview: latency, unnecessary API calls
- No preview: users can't verify before submitting

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Date 29/30/31 may not exist in some months | Backend handles gracefully (cron schedulers auto-adjust); show tooltip warning |
| User confusion about "preview time" vs actual execution | Clear label "首次执行时间" with timezone note |
| Weekday UI uses Chinese labels (一二三四五六日) vs cron numbers (0-6) | Map correctly: 一→1, 日→0 (or use 7 for Sunday per cron standard) |
| Multi-select UX complexity | Single-click toggle, clear visual feedback, minimum 1 selection enforced |