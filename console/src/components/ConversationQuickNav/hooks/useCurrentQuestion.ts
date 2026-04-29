import { useState, useEffect, useCallback, useRef } from "react";

interface Question {
  id: string;
  index: number;
  text: string;
}

/**
 * 追踪当前滚动位置对应的问题
 * 通过检查所有问题元素位置，找到最接近视口顶部的问题
 */
export function useCurrentQuestion(questions: Question[]) {
  // 初始状态：如果有问题则默认第一个，否则null
  const [currentQuestionId, setCurrentQuestionId] = useState<string | null>(
    questions[0]?.id || null
  );

  // 当 questions 从空变为非空时，设置初始状态
  useEffect(() => {
    if (questions.length > 0 && currentQuestionId === null) {
      // 立即设置第一个问题为当前问题
      setCurrentQuestionId(questions[0].id);
    }
  }, [questions, currentQuestionId]);

  // 使用ref存储最新的问题列表，避免闭包问题
  const questionsRef = useRef(questions);
  questionsRef.current = questions;

  // 手动选择后暂时禁用自动检测的标记
  const manualSelectRef = useRef(false);
  const manualSelectTimeoutRef = useRef<number | null>(null);

  // 检查当前可见问题的函数
  const checkCurrentQuestion = useCallback(() => {
    // 如果刚进行了手动选择，跳过自动检测
    if (manualSelectRef.current) return;

    const currentQuestions = questionsRef.current;
    if (currentQuestions.length === 0) return;

    // 视口范围（考虑header）
    const viewportTop = 80; // header高度 + 一些边距
    const viewportBottom = window.innerHeight - 100;

    // 找到在视口内且最接近顶部的问题（只选一个）
    let closestId: string | null = null;
    let minTop = Infinity;

    // 按顺序检查所有问题（从上到下）
    for (const question of currentQuestions) {
      const element = document.getElementById(question.id);
      if (!element) continue;

      const rect = element.getBoundingClientRect();
      const top = rect.top;
      const bottom = rect.bottom;

      // 检查元素是否在视口内（至少部分可见）
      if (top < viewportBottom && bottom > viewportTop) {
        // 元素在视口内，计算到视口顶部的距离
        // 越接近viewportTop越好
        const distanceToViewportTop = Math.abs(top - viewportTop);

        // 只记录最小的距离
        if (distanceToViewportTop < minTop) {
          minTop = distanceToViewportTop;
          closestId = question.id;
        }
      }
    }

    // 如果没有找到在视口内的，找第一个完全在视口上方的（历史消息）
    if (!closestId) {
      // 找最接近viewportTop的上方的元素
      let maxBottom = -Infinity;
      for (const question of currentQuestions) {
        const element = document.getElementById(question.id);
        if (!element) continue;

        const rect = element.getBoundingClientRect();
        // 在视口上方，找bottom最大的（最接近视口顶部）
        if (rect.bottom <= viewportTop && rect.bottom > maxBottom) {
          maxBottom = rect.bottom;
          closestId = question.id;
        }
      }
    }

    // 如果还是没找到，用第一个问题
    if (!closestId && currentQuestions.length > 0) {
      closestId = currentQuestions[0].id;
    }

    if (closestId) {
      setCurrentQuestionId(prev => {
        // 只有变化时才更新，避免不必要的重渲染
        if (prev !== closestId) {
          return closestId;
        }
        return prev;
      });
    }
  }, []);

  // 当 questions 变化时，立即检查当前问题
  useEffect(() => {
    if (questions.length === 0) return;

    // 使用 setTimeout 确保 DOM 已更新后再检查位置
    const timer = setTimeout(checkCurrentQuestion, 100);
    return () => clearTimeout(timer);
  }, [questions, checkCurrentQuestion]);

  // 设置滚动监听
  useEffect(() => {
    if (questions.length === 0) return;

    // 找到滚动容器
    const scrollContainer = document.querySelector('[class*="bubble-list-scroll"]');
    if (!scrollContainer) return;

    // 使用RAF包装的滚动处理
    let rafId: number | null = null;
    const handleScroll = () => {
      if (rafId) {
        cancelAnimationFrame(rafId);
      }
      rafId = requestAnimationFrame(checkCurrentQuestion);
    };

    // 监听滚动容器
    scrollContainer.addEventListener('scroll', handleScroll, { passive: true });

    // 使用MutationObserver监听DOM变化（新消息加载）
    const mutationObserver = new MutationObserver(() => {
      // 延迟执行，等待 DOM 完成渲染
      setTimeout(checkCurrentQuestion, 100);
    });

    mutationObserver.observe(scrollContainer, {
      childList: true,
      subtree: true,
    });

    // 监听窗口大小变化
    const resizeObserver = new ResizeObserver(() => {
      handleScroll();
    });
    resizeObserver.observe(scrollContainer);

    // 立即执行初始检查（确保在监听器设置后检查当前位置）
    checkCurrentQuestion();

    return () => {
      scrollContainer.removeEventListener('scroll', handleScroll);
      if (rafId) {
        cancelAnimationFrame(rafId);
      }
      mutationObserver.disconnect();
      resizeObserver.disconnect();
      // 清理手动选择的超时
      if (manualSelectTimeoutRef.current) {
        clearTimeout(manualSelectTimeoutRef.current);
      }
    };
  }, [questions.length, checkCurrentQuestion]);

  // 手动设置当前问题的方法（点击时使用）
  const setCurrent = useCallback((id: string) => {
    // 设置手动选择标记，暂时禁用自动检测
    manualSelectRef.current = true;

    // 清除之前的超时
    if (manualSelectTimeoutRef.current) {
      clearTimeout(manualSelectTimeoutRef.current);
    }

    // 设置新的超时，800ms后恢复自动检测
    // 这个时间足够让滚动动画完成且不会立即被覆盖
    manualSelectTimeoutRef.current = window.setTimeout(() => {
      manualSelectRef.current = false;
      manualSelectTimeoutRef.current = null;
    }, 800);

    setCurrentQuestionId(id);
  }, []);

  return { currentQuestionId, setCurrent };
}