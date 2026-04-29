# 业务概览页面 UI 样式修改 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修改业务概览页面柱状图颜色，将第5色改为柔和玫红 #e866a8

**Architecture:** 仅修改 TSX 文件中的 BAR_COLORS 常量数组，样式文件中的圆角已存在

**Tech Stack:** React, TypeScript, Less

---

## 修改范围

| 文件 | 修改内容 |
|------|----------|
| `console/src/pages/Analytics/BusinessOverview/index.tsx:41-47` | 修改 BAR_COLORS 数组第4、5个颜色 |

**无需修改样式文件**：`.barFill` 已有 `border-radius: 4px`

---

### Task 1: 修改柱状图颜色数组

**Files:**
- Modify: `console/src/pages/Analytics/BusinessOverview/index.tsx:41-47`

- [ ] **Step 1: 修改 BAR_COLORS 数组**

将第4个颜色从红色改为紫色，第5个颜色从紫色改为柔和玫红：

```typescript
// 柱状图颜色
const BAR_COLORS = [
  "linear-gradient(90deg, #1890ff 0%, #69c0ff 100%)",
  "linear-gradient(90deg, #52c41a 0%, #95de64 100%)",
  "linear-gradient(90deg, #faad14 0%, #ffe58f 100%)",
  "linear-gradient(90deg, #722ed1 0%, #b37feb 100%)",
  "linear-gradient(90deg, #e866a8 0%, #f0a0c0 100%)",
];
```

- [ ] **Step 2: 验证修改**

在浏览器中打开业务概览页面，确认柱状图颜色正确显示：
- 第1条：蓝色 #1890ff
- 第2条：绿色 #52c41a
- 第3条：黄色 #faad14
- 第4条：紫色 #722ed1
- 第5条：玫红 #e866a8

- [ ] **Step 3: 提交代码**

```bash
git add console/src/pages/Analytics/BusinessOverview/index.tsx
git commit -m "style(analytics): 调整柱状图颜色序列，第5色改为柔和玫红

- 将第4色从红色改为紫色 (#722ed1)
- 将第5色从紫色改为柔和玫红 (#e866a8)
- 符合设计文档规范"
```

---

## 验收标准

- [ ] 柱状图圆角为 4px（已存在）
- [ ] 柱状图颜色序列符合设计文档：蓝、绿、黄、紫、玫红
- [ ] 页面渲染正常，无控制台报错
