## ADDED Requirements

### Requirement: 显示快速定位悬浮条
系统 SHALL 在聊天消息区域右侧显示一个垂直悬浮导航条，当会话中存在至少 2 个用户问题时。

#### Scenario: 有多个问题时显示悬浮条
- **WHEN** 用户打开一个包含 3 个用户问题的会话
- **THEN** 消息区域右侧显示垂直悬浮导航条，包含 3 个圆点标记

#### Scenario: 单个问题时不显示悬浮条
- **WHEN** 用户打开一个只有 1 个用户问题的会话
- **THEN** 不显示快速定位悬浮条

#### Scenario: 无消息时不显示悬浮条
- **WHEN** 用户新建会话，没有消息
- **THEN** 不显示快速定位悬浮条

#### Scenario: 会话加载时不显示悬浮条
- **WHEN** 会话正在加载消息
- **THEN** 不显示快速定位悬浮条

### Requirement: 圆点标记定位
系统 SHALL 为每个用户问题渲染一个圆点标记，圆点的垂直位置根据问题序号占总问题数的百分比确定。

#### Scenario: 圆点位置计算
- **WHEN** 会话有 4 个用户问题
- **THEN** 第 1 个问题的圆点位于顶部 25% 位置
- **AND** 第 2 个问题的圆点位于 50% 位置
- **AND** 第 3 个问题的圆点位于 75% 位置
- **AND** 第 4 个问题的圆点位于底部位置

### Requirement: 鼠标悬停显示 Tooltip
系统 SHALL 在用户鼠标悬停圆点标记时，在圆点左侧显示 Tooltip，包含问题序号和问题内容预览。

#### Scenario: 显示 Tooltip
- **WHEN** 用户鼠标悬停在第 3 个问题的圆点上
- **THEN** 圆点左侧显示 Tooltip
- **AND** Tooltip 第一行显示"第 3 次问题"
- **AND** Tooltip 显示问题文本预览（截断至 2 行）

#### Scenario: 鼠标离开隐藏 Tooltip
- **WHEN** 用户鼠标离开圆点
- **THEN** Tooltip 消失（200ms 淡出动画）

### Requirement: 点击圆点跳转到消息
系统 SHALL 在用户点击圆点标记时，平滑滚动到对应的消息位置。

#### Scenario: 点击圆点跳转
- **WHEN** 用户点击第 3 个问题的圆点
- **THEN** 消息列表平滑滚动到第 3 个问题的消息位置
- **AND** 消息显示高亮闪烁效果（2 秒后消失）

#### Scenario: 消息不存在时静默处理
- **WHEN** 用户点击圆点但对应消息元素无法找到
- **THEN** 不执行滚动，无错误提示

### Requirement: 悬浮条动效
系统 SHALL 为悬浮条及其元素提供平滑的动效。

#### Scenario: 悬浮条出现动效
- **WHEN** 悬浮条从隐藏变为显示
- **THEN** 悬浮条以 300ms 渐显 + 滑入动画出现

#### Scenario: 圆点呼吸动效
- **WHEN** 悬浮条显示时
- **THEN** 每个圆点有呼吸/脉冲动画效果

#### Scenario: 圆点悬停放大
- **WHEN** 用户鼠标悬停在圆点上
- **THEN** 圆点放大至 1.67 倍（150ms 过渡）

#### Scenario: Tooltip 滑入动效
- **WHEN** Tooltip 显示时
- **THEN** Tooltip 以 200ms 滑入 + 淡入动画出现

#### Scenario: 消息高亮动效
- **WHEN** 跳转到消息后
- **THEN** 消息元素背景闪烁高亮效果，2 秒后消失

### Requirement: 适配 dark mode
系统 SHALL 使悬浮条及其元素颜色适配 dark mode 主题。

#### Scenario: dark mode 颜色适配
- **WHEN** 用户切换到 dark mode
- **THEN** 圆点颜色使用品牌色 `#3769fc`
- **AND** Tooltip 背景使用深色
- **AND** Tooltip 文字使用浅色