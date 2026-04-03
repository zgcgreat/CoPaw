import React from 'react';
import { ToolProgress as IToolProgress } from '@/chat';

interface ToolProgressProps {
  progress: IToolProgress;
}

const ToolProgress: React.FC<ToolProgressProps> = ({ progress }) => {
  const { total, completed, failed } = progress;

  return (
    <span className="processing-status-bar-tool-progress">
      工具: {completed}/{total} 完成
      {failed > 0 && <span className="failed"> ({failed} 失败)</span>}
    </span>
  );
};

export default ToolProgress;
