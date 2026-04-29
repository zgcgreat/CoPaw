import { useCallback } from "react";

const HIGHLIGHT_DURATION = 2000;
const HIGHLIGHT_CLASS = "quick-nav-highlight-flash";

/**
 * 滚动到指定消息并添加高亮闪烁效果
 * 如果消息未加载到DOM，提示用户手动滚动加载
 */
export function useScrollToMessage() {
  const scrollToMessage = useCallback((messageId: string) => {
    try {
      const messageElement = document.getElementById(messageId);

      if (messageElement) {
        // 消息已加载，直接滚动
        performScroll(messageElement);
        return;
      }

      // 消息未加载，提示用户
      console.warn(`消息尚未加载，请先滚动到历史区域加载更多消息`);

      // 尝试找到滚动容器并滚动到底部触发加载
      const scrollContainer = findScrollContainer();
      if (scrollContainer) {
        // 在desc/column-reverse模式下，尝试向上滚动触发LoadMore
        // 由于布局复杂性，这里使用scrollIntoView找到最近的可见消息
        const bubbles = document.querySelectorAll('.swe-bubble');
        if (bubbles.length > 0) {
          // 滚动到最底部的消息，触发LoadMore进入视口
          const lastVisibleBubble = Array.from(bubbles)
            .filter(b => b.getBoundingClientRect().top < 0)
            .pop();

          if (lastVisibleBubble) {
            lastVisibleBubble.scrollIntoView({ behavior: 'smooth', block: 'end' });
          }
        }
      }

    } catch (error) {
      console.error("Error scrolling to message:", error);
    }
  }, []);

  const performScroll = (messageElement: HTMLElement) => {
    messageElement.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });

    messageElement.classList.add(HIGHLIGHT_CLASS);

    setTimeout(() => {
      messageElement.classList.remove(HIGHLIGHT_CLASS);
    }, HIGHLIGHT_DURATION);
  };

  const findScrollContainer = (): HTMLElement | null => {
    const selectors = [
      '[class*="bubble-list-scroll"]',
      '[class*="bubble-list"]',
    ];

    for (const selector of selectors) {
      const containers = document.querySelectorAll(selector);
      for (const container of containers) {
        const style = window.getComputedStyle(container);
        if (style.overflow === 'auto' || style.overflow === 'scroll' ||
            style.overflowY === 'auto' || style.overflowY === 'scroll') {
          return container as HTMLElement;
        }
      }
    }

    return null;
  };

  return {
    scrollToMessage,
  };
}