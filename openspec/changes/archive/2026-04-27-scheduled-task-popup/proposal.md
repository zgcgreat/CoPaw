## Why

Users viewing case details currently cannot subscribe to a case as a scheduled task directly from the CaseDetailDrawer. The "订阅为定时任务" button exists but has no implementation (TODO placeholder). This feature enables users to schedule periodic execution of case-based tasks with flexible frequency options (daily/weekly/monthly).

## What Changes

- **New popup modal component** for scheduled task configuration with three frequency modes (每天/每周/每月)
- **Frequency selection tabs** allowing users to switch between daily, weekly, and monthly execution patterns
- **Time picker inputs** for specifying execution time (hour/minute)
- **Weekday selector** (weekly mode) - multi-select grid for Monday through Sunday
- **Date selector** (monthly mode) - multi-select grid for days 1-31
- **Preview section** showing next execution time and execution pattern summary
- **Cron expression generation** from user selections for backend scheduling
- **Integration with existing cronjob API** to create scheduled tasks

## Capabilities

### New Capabilities
- `scheduled-task-popup`: Modal component for configuring scheduled task frequency and time, generating cron expressions, and integrating with the cronjob creation API

### Modified Capabilities
- None - this is a new feature, not modifying existing spec-level behavior

## Impact

- **Frontend**: New `ScheduledTaskPopup` component in `console/src/components/`
- **CaseDetailDrawer**: Update to trigger popup on "订阅为定时任务" button click
- **API**: Use existing `CronJobSpecInput` and related types from `console/src/api/types/cronjob.ts`
- **No backend changes**: Existing cronjob API supports the required cron expression format