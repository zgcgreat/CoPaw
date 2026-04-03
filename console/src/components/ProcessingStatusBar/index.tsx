import { useContextSelector } from 'use-context-selector';
import { ChatAnywhereInputContext } from '@/chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereInputContext';
import { useProviderContext } from '@/chat';
import StatusIndicator from './StatusIndicator';
import TokenCounter from './TokenCounter';
import ElapsedTimer from './ElapsedTimer';
import ToolProgress from './ToolProgress';
import Style from './style';

const ProcessingStatusBar = () => {
  const { getPrefixCls } = useProviderContext();
  const prefixCls = getPrefixCls('processing-status-bar');

  const processing = useContextSelector(ChatAnywhereInputContext, v => v.processing);

  if (processing.status === 'idle') return null;

  return (
    <>
      <Style />
      <div className={prefixCls}>
        <StatusIndicator status={processing.status} />
        <div className={`${prefixCls}-divider`} />
        {processing.toolProgress && (
          <>
            <ToolProgress progress={processing.toolProgress} />
            <div className={`${prefixCls}-divider`} />
          </>
        )}
        <TokenCounter count={processing.tokenCount} />
        <div className={`${prefixCls}-divider`} />
        <ElapsedTimer startTime={processing.startTime} />
      </div>
    </>
  );
};

export default ProcessingStatusBar;
