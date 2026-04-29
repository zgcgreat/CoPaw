## 1. 基础结构搭建

- [x] 1.1 创建组件目录 `console/src/components/ConversationQuickNav/`
- [x] 1.2 创建类型定义文件 `types.ts`（QuestionInfo 接口、Props 类型）
- [x] 1.3 创建样式文件 `style.ts`（使用 antd-style createGlobalStyle）

## 2. 核心 Hooks 实现

- [x] 2.1 实现 `useQuestionMessages.ts`：从 ChatAnywhereMessagesContext 获取消息并筛选 user 消息
- [x] 2.2 实现 `useScrollToMessage.ts`：DOM id 定位 + scrollIntoView 跳转逻辑 + 高亮闪烁效果

## 3. 子组件实现

- [x] 3.1 实现 `NavDot.tsx`：圆点标记组件（呼吸动效、悬停放大、点击跳转）
- [x] 3.2 实现 `QuestionTooltip.tsx`：Tooltip 组件（显示问题序号和内容预览，截断至 2 行）

## 4. 主组件实现

- [x] 4.1 实现 `index.tsx` 主组件框架（读取 Context、计算位置、渲染 NavDot 列表）
- [x] 4.2 实现显示/隐藏逻辑（至少 2 个问题才显示，isSessionLoading 时隐藏）
- [x] 4.3 实现悬浮条出现动效（渐显 + 滑入，300ms）

## 5. 页面集成

- [x] 5.1 在 `Chat/index.tsx` 的 `.chatMessagesArea` div 内添加 ConversationQuickNav 组件
- [x] 5.2 调整组件定位样式（absolute 定位在右侧，合适的边距）

## 6. 动效与样式完善

- [x] 6.1 完善圆点呼吸/脉冲 keyframes 动效
- [x] 6.2 完善 Tooltip 滑入淡入动效
- [x] 6.3 完善跳转后消息高亮闪烁动效（添加 CSS 类，2 秒后移除）
- [x] 6.4 适配 dark mode（颜色、背景、文字）

## 7. 测试与验证

- [x] 7.1 手动测试：新建会话 → 不显示悬浮条
- [x] 7.2 手动测试：发送 2+ 个问题 → 显示悬浮条，圆点数量正确
- [x] 7.3 手动测试：悬停圆点 → Tooltip 显示正确
- [x] 7.4 手动测试：点击圆点 → 滚动到对应消息，高亮闪烁
- [ ] 7.5 手动测试：dark mode → 颜色适配正确
- [x] 7.6 运行 ESLint 和构建验证