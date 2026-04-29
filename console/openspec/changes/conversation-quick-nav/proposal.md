## Why

用户在长对话中会提出多个问题，当需要回顾或跳转到历史问题时，只能通过滚动查找，效率低下。右侧快速定位悬浮框提供了一个可视化的导航入口，帮助用户快速识别问题数量、预览问题内容、一键跳转，提升长对话的浏览体验。

## What Changes

- 新增 `ConversationQuickNav` 组件，在聊天消息区域右侧渲染一个垂直悬浮导航条
- 组件包含多个圆点标记，每个圆点对应一个用户问题（`role === "user"` 的消息）
- 鼠标悬停圆点时显示 Tooltip：展示"第X次问题"和问题内容预览（截断至 2 行）
- 点击圆点后平滑滚动跳转到对应消息位置，并触发高亮闪烁动效
- 动效设计：悬浮条渐显滑入、圆点呼吸/脉冲效果、Tooltip 滑入淡入、跳转后消息高亮
- 组件仅在会话有至少 2 个问题时显示，单问题或欢迎页时隐藏

## Capabilities

### New Capabilities

- `conversation-quick-nav`: 聊天对话右侧快速定位悬浮框组件，提供问题导航、内容预览、快速跳转能力

### Modified Capabilities

无现有 capability 的 requirements 变化。

## Impact

**新增文件：**
- `console/src/components/ConversationQuickNav/index.tsx` - 主组件
- `console/src/components/ConversationQuickNav/style.ts` - CSS-in-JS 样式
- `console/src/components/ConversationQuickNav/types.ts` - 类型定义
- `console/src/components/ConversationQuickNav/hooks/useQuestionMessages.ts` - 获取并筛选用户消息
- `console/src/components/ConversationQuickNav/hooks/useScrollToMessage.ts` - 跳转逻辑
- `console/src/components/ConversationQuickNav/components/NavDot.tsx` - 圆点标记组件
- `console/src/components/ConversationQuickNav/components/QuestionTooltip.tsx` - Tooltip 组件

**修改文件：**
- `console/src/pages/Chat/index.tsx` - 在消息区域添加 ConversationQuickNav 组件

**依赖：**
- `ChatAnywhereMessagesContext` - 获取消息列表
- `ChatAnywhereSessionsContext` - 获取会话加载状态
- `extractUserMessageText` (utils.ts) - 提取用户问题文本

**不影响：**
- 现有消息渲染逻辑
- 现有滚动行为
- 其他组件功能