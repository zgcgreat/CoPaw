interface QuestionTooltipProps {
  /** 问题序号 */
  index: number;
  /** 问题文本 */
  text: string;
  /** 是否显示 */
  visible: boolean;
}

export function QuestionTooltip({
  index,
  text,
  visible,
}: QuestionTooltipProps) {
  return (
    <div
      className={`quick-nav-tooltip ${visible ? "quick-nav-tooltip--visible" : ""}`}
    >
      <div className="quick-nav-tooltip-content">
        <strong># {index}</strong>
        <span>{text}</span>
      </div>
    </div>
  );
}