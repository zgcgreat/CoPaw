import { useProviderContext } from "@/chat";
import Input from "./Input";
import MessageList from "./MessageList";
import ProcessingStatusBar from "@/components/ProcessingStatusBar";
import Style from './styles';
import useChatController from "./hooks/useChatController";

export default function Chat() {
  const prefixCls = useProviderContext().getPrefixCls('chat-anywhere-chat');
  const { handleSubmit, handleCancel } = useChatController();

  return <>
    <Style />
    <div className={prefixCls}>
      <MessageList onSubmit={handleSubmit} />
      <ProcessingStatusBar />
      <Input onCancel={handleCancel} onSubmit={handleSubmit} />
    </div>
  </>;
}