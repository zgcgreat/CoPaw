import React, { useState } from "react";
import { useQuestionMessages } from "./hooks/useQuestionMessages";
import { useScrollToMessage } from "./hooks/useScrollToMessage";
import { useCurrentQuestion } from "./hooks/useCurrentQuestion";
import { NavDot } from "./components/NavDot";
import { ConversationQuickNavProps } from "./types";
import Style from "./style";

export default function ConversationQuickNav({
  minQuestions = 1,
}: ConversationQuickNavProps) {
  const { questions, shouldShow } = useQuestionMessages(minQuestions);
  const { scrollToMessage } = useScrollToMessage();
  const { currentQuestionId, setCurrent } = useCurrentQuestion(questions);
  const [isContainerHovered, setIsContainerHovered] = useState(false);

  if (!shouldShow) {
    return null;
  }

  const handleClick = (messageId: string) => {
    // 点击后立即切换高亮
    setCurrent(messageId);
    scrollToMessage(messageId);
  };

  return (
    <>
      <Style />
      <div
        className={`conversation-quick-nav ${isContainerHovered ? "conversation-quick-nav--hovered" : ""}`}
        onMouseEnter={() => setIsContainerHovered(true)}
        onMouseLeave={() => setIsContainerHovered(false)}
      >
        {questions.map((question) => {
          const isCurrent = question.id === currentQuestionId;
          return (
            <NavDot
              key={question.id}
              index={question.index}
              text={question.text}
              messageId={question.id}
              onClick={handleClick}
              isCurrent={isCurrent}
            />
          );
        })}
      </div>
    </>
  );
}