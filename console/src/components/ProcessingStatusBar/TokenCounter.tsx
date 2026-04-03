import React, { useState, useEffect } from 'react';

interface TokenCounterProps {
  count: number;
}

function formatToken(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return count.toString();
}

const TokenCounter: React.FC<TokenCounterProps> = ({ count }) => {
  const [displayCount, setDisplayCount] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDisplayCount(count);
    }, 300); // 300ms 节流

    return () => clearTimeout(timer);
  }, [count]);

  return <span>{formatToken(displayCount)} tokens</span>;
};

export default TokenCounter;
