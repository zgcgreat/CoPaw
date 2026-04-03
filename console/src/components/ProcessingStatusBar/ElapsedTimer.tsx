import React, { useState, useEffect, useRef } from 'react';

interface ElapsedTimerProps {
  startTime: number | null;
}

const ElapsedTimer: React.FC<ElapsedTimerProps> = ({ startTime }) => {
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!startTime) {
      setElapsed(0);
      return;
    }

    // 重置
    setElapsed(0);

    // 清除旧定时器
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    // 每秒更新
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [startTime]);

  return <span>{elapsed}s</span>;
};

export default ElapsedTimer;
