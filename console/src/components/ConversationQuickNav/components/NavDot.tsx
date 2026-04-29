import React, { useState } from "react";
import { QuestionTooltip } from "./QuestionTooltip";

interface NavDotProps {
  /** 问题序号（1, 2, 3...） */
  index: number;
  /** 问题文本 */
  text: string;
  /** 消息 ID，用于跳转 */
  messageId: string;
  /** 点击回调 */
  onClick: (messageId: string) => void;
  /** 是否为当前活动的问题 */
  isCurrent?: boolean;
}

export function NavDot({
  index,
  text,
  messageId,
  onClick,
  isCurrent = false,
}: NavDotProps) {
  const [isHovered, setIsHovered] = useState(false);

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    onClick(messageId);
  };

  // 当前活动或hover时显示蓝色
  const isActive = isCurrent || isHovered;

  return (
    <div
      className={`quick-nav-dot ${isActive ? "quick-nav-dot--active" : ""}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={handleClick}
      tabIndex={0}
      role="button"
      aria-label={`第 ${index} 次问题: ${text}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(messageId);
        }
      }}
    >
      <QuestionTooltip
        index={index}
        text={text}
        visible={isHovered}
      />
    </div>
  );
}