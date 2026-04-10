import { request } from "../request";

export interface PushMessage {
  id: string;
  text: string;
}

export const consoleApi = {
  getPushMessages: (sessionId: string) =>
    request<{ messages: PushMessage[] }>(
      `/console/push-messages?session_id=${encodeURIComponent(sessionId)}`,
    ),
};
