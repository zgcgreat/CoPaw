import { createContext, useContextSelector } from 'use-context-selector';
import { IAgentScopeRuntimeWebUIInputContext, ProcessingState } from '@/chat';
import { useGetState } from 'ahooks';

const defaultProcessing: ProcessingState = {
  status: 'idle',
  startTime: null,
  tokenCount: 0,
  toolProgress: null,
};

export const ChatAnywhereInputContext = createContext<IAgentScopeRuntimeWebUIInputContext>({
  loading: false,
  setLoading: () => { },
  getLoading: () => false,
  disabled: false,
  setDisabled: () => { },
  getDisabled: () => false,
  processing: defaultProcessing,
  setProcessing: () => { },
});

export function ChatAnywhereInputContextProvider(props: {
  children: React.ReactNode | React.ReactNode[];
}) {
  const [loading, setLoading, getLoading] = useGetState<boolean | string>(false);
  const [disabled, setDisabled, getDisabled] = useGetState<boolean | string>(false);
  const [processing, setProcessingState] = useGetState<ProcessingState>(defaultProcessing);

  const setProcessing = (state: Partial<ProcessingState>) => {
    setProcessingState(prev => ({ ...prev, ...state }));
  };

  return <ChatAnywhereInputContext.Provider value={{
    loading,
    setLoading,
    getLoading,
    disabled,
    setDisabled,
    getDisabled,
    processing,
    setProcessing,
  }}>
    {props.children}
  </ChatAnywhereInputContext.Provider>;
}

export const useChatAnywhereInput = (selector: (v: Partial<IAgentScopeRuntimeWebUIInputContext>) => Partial<IAgentScopeRuntimeWebUIInputContext>) => {
  return useContextSelector(ChatAnywhereInputContext, selector);
}
