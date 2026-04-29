## Context

聊天页面使用 `AgentScopeRuntimeWebUI` 组件框架，消息列表通过 `Bubble.List` 渲染，消息数据存储在 `ChatAnywhereMessagesContext`。用户消息（`role === "user"`）包含问题文本，存储在 `cards[0].data.input[0].content` 中，可通过 `extractUserMessageText` 工具函数提取。

消息列表采用倒序布局（`order="desc"`），最新消息显示在顶部。消息 DOM 元素有 `id` 属性可用于定位跳转。

约束：
- 使用 `antd-style` 的 `createGlobalStyle` 定义样式
- 适配 dark mode
- 遵循现有品牌主题颜色（`#3769fc`）

## Goals / Non-Goals

**Goals:**
- 在聊天右侧渲染一个垂直悬浮导航条
- 显示用户问题的位置标记（圆点）
- 鼠标悬停显示问题序号和内容预览
- 点击圆点跳转到对应消息并高亮
- 实现平滑动效

**Non-Goals:**
- 不支持 assistant 消息的导航（只导航用户问题）
- 不实现搜索/过滤功能
- 不持久化导航状态
- 不影响现有滚动/消息渲染逻辑

## Decisions

### 1. 组件位置：消息区域内部（相对定位）

**选择：** 在 `Chat/index.tsx` 的 `.chatMessagesArea` div 内部添加组件，使用 `position: absolute` 定位在右侧。

**原因：**
- 组件需要与消息列表共享同一容器，便于位置计算
- 不影响 ChatSidebar 和其他布局元素
- 组件随消息区域一起滚动隐藏（悬浮条固定在可视区域）

**备选方案：**
- 放在 `AgentScopeRuntimeWebUILayout` 内部 → 需要修改框架组件，侵入性大
- 作为独立浮层 → 需要额外处理 z-index 和容器关系

### 2. 圆点位置计算：百分比定位

**选择：** 根据问题序号占总问题数的百分比计算圆点的垂直位置。

```
yPosition = (questionIndex / totalQuestions) * 100%
```

**原因：**
- 不依赖消息实际高度（消息高度动态变化）
- 不需要监听滚动事件实时计算
- 简单直观，符合用户直觉（第一个问题在上，最后一个在下）

**备选方案：**
- 基于消息 DOM 位置计算 → 需要监听滚动，复杂度高
- 固定间距 → 问题多时圆点过于密集

### 3. 跳转实现：DOM id 定位 + scrollIntoView

**选择：** 使用 `document.getElementById(messageId)` 定位消息元素，调用 `scrollIntoView({ behavior: "smooth" })` 滚动。

**原因：**
- 消息元素已有 `id` 属性
- `scrollIntoView` 是原生 API，性能好
- 实现简单，无需额外依赖

**备选方案：**
- 使用 Bubble.List ref 的 scrollToItem → API 不公开
- 手动计算 scrollTop → 复杂度高

### 4. 动效实现：CSS transition + keyframes

**选择：** 使用 CSS `transition` 处理交互状态变化，`@keyframes` 处理呼吸/脉冲效果。

**原因：**
- 性能优于 JS 动画
- 代码简洁，易于维护
- `antd-style` 支持嵌入 keyframes

### 5. 显示条件：至少 2 个用户问题

**选择：** 只有用户问题数 >= 2 时才显示悬浮条。

**原因：**
- 单个问题没有导航意义
- 避免不必要的 UI 元素
- 欢迎页无消息时自然隐藏

## Risks / Trade-offs

**[消息 id 不稳定] → 添加错误处理**
- 如果 `getElementById` 返回 null，静默失败，不执行滚动
- 使用 `try-catch` 包裹跳转逻辑

**[消息内容过长影响 Tooltip 显示] → 截断文本**
- 问题文本截断至 2 行，超出部分用 `...` 表示
- Tooltip 最大宽度 200px

**[问题数量过多导致圆点密集] → 预留扩展方案**
- 当前设计支持最多 20 个圆点，超出时仍渲染但可能密集
- 后续可添加"折叠显示"功能（不在本范围）

**[dark mode 适配] → 使用 CSS 变量**
- 颜色定义使用 `DESIGN_TOKENS`，自动适配主题
- Tooltip 背景和文字颜色根据主题切换