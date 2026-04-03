import React from 'react';
import { Bubble } from '@/chat';

interface StatusIndicatorProps {
  status: 'waiting' | 'processing';
}

const StatusIndicator: React.FC<StatusIndicatorProps> = ({ status }) => {
  return (
    <div className="processing-status-bar-status">
      <Bubble.Spin />
      <span>{status === 'waiting' ? '等待中...' : '处理中...'}</span>
    </div>
  );
};

export default StatusIndicator;
