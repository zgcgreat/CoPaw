## 1. Utility Functions

- [x] 1.1 Create `console/src/utils/cron.ts` with cron expression generator function
- [x] 1.2 Add time validation and auto-correction functions (hour 0-23, minute 0-59)
- [x] 1.3 Add next execution time calculation function using dayjs
- [x] 1.4 Add weekday mapping (一→1, 二→2, ..., 日→0 or 7)
- [x] 1.5 Add unit tests for cron utility functions

## 2. ScheduledTaskPopup Component

- [x] 2.1 Create `console/src/components/ScheduledTaskPopup/` directory structure
- [x] 2.2 Implement `index.tsx` with modal structure (header, body, footer)
- [x] 2.3 Add frequency tab switcher component (每天/每周/每月)
- [x] 2.4 Implement time picker input fields with validation on blur
- [x] 2.5 Implement weekday selector grid with multi-select toggle
- [x] 2.6 Implement date selector grid (1-31) with multi-select toggle
- [x] 2.7 Add preview section with real-time next execution calculation
- [x] 2.8 Implement confirm/cancel button handlers
- [x] 2.9 Add styles in `index.module.less` matching design HTML
- [x] 2.10 Add TypeScript types/interfaces for component props and state

## 3. API Integration

- [x] 3.1 Create or extend cronjob API module for task creation
- [x] 3.2 Add function to create CronJobSpecInput from popup selections + caseData
- [x] 3.3 Implement success/error feedback (toast notification)
- [x] 3.4 Handle loading state during API call

## 4. CaseDetailDrawer Integration

- [x] 4.1 Import ScheduledTaskPopup component into CaseDetailDrawer
- [x] 4.2 Add state for popup visibility control
- [x] 4.3 Connect "订阅为定时任务" button click to open popup
- [x] 4.4 Pass caseData to popup for task creation context
- [x] 4.5 Handle popup confirm callback to create scheduled task

## 5. Testing

- [x] 5.1 Add component tests for ScheduledTaskPopup (rendering, interactions)
- [x] 5.2 Test frequency tab switching behavior
- [x] 5.3 Test time input validation and auto-correction
- [x] 5.4 Test weekday/date multi-select behavior
- [x] 5.5 Test cron expression generation for each frequency type
- [x] 5.6 Test confirm button enable/disable logic
- [x] 5.7 Verify integration with CaseDetailDrawer