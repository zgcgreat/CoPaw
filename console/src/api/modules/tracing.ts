import { request } from "../request";
import { buildAuthHeaders } from "../authHeaders";

// Types
export interface OverviewStats {
  online_users: number;
  online_user_ids: string[];
  total_users: number;
  model_distribution: ModelUsage[];
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  total_sessions: number;
  total_conversations: number;
  avg_duration_ms: number;
  top_tools: ToolUsage[];
  top_skills: SkillUsage[];
  top_mcp_tools: MCPToolUsage[];
  mcp_servers: MCPServerUsage[];
  daily_trend: DailyStats[];
}

export interface ModelUsage {
  model_name: string;
  count: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
}

export interface ToolUsage {
  tool_name: string;
  count: number;
  avg_duration_ms: number;
  error_count: number;
}

export interface SkillUsage {
  skill_name: string;
  count: number;
  avg_duration_ms: number;
}

export interface MCPToolUsage {
  tool_name: string;
  mcp_server: string;
  count: number;
  avg_duration_ms: number;
  error_count: number;
}

export interface MCPServerUsage {
  server_name: string;
  tool_count: number;
  total_calls: number;
  avg_duration_ms: number;
  error_count: number;
  tools: MCPToolUsage[];
}

export interface DailyStats {
  date: string;
  total_users: number;
  active_users: number;
  total_tokens: number;
  session_count: number;
}

export interface UserStats {
  user_id: string;
  model_usage: ModelUsage[];
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  total_sessions: number;
  total_conversations: number;
  avg_duration_ms: number;
  tools_used: ToolUsage[];
  skills_used: SkillUsage[];
}

export interface UserListItem {
  user_id: string;
  total_sessions: number;
  total_conversations: number;
  total_tokens: number;
  last_active: string | null;
}

export interface TraceListItem {
  trace_id: string;
  user_id: string;
  session_id: string;
  channel: string;
  start_time: string;
  duration_ms: number | null;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  model_name: string | null;
  status: string;
  skills_count: number;
}

export interface SessionListItem {
  session_id: string;
  user_id: string;
  channel: string;
  total_traces: number;
  total_tokens: number;
  total_skills: number;
  first_active: string | null;
  last_active: string | null;
}

export interface SessionStats {
  session_id: string;
  user_id: string;
  channel: string;
  model_usage: ModelUsage[];
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  total_traces: number;
  avg_duration_ms: number;
  tools_used: ToolUsage[];
  skills_used: SkillUsage[];
  mcp_tools_used: MCPToolUsage[];
  first_active: string | null;
  last_active: string | null;
}

export interface TraceDetail {
  trace: Trace;
  spans: Span[];
  llm_duration_ms: number;
  tool_duration_ms: number;
  tools_called: ToolCall[];
}

export interface Trace {
  trace_id: string;
  user_id: string;
  session_id: string;
  channel: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number | null;
  model_name: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  tools_used: string[];
  skills_used: string[];
  status: string;
  error: string | null;
  user_message: string | null;
  model_output: string | null;
}

export interface Span {
  span_id: string;
  trace_id: string;
  name: string;
  event_type: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number | null;
  model_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  tool_name: string | null;
  skill_name: string | null;
  tool_input: Record<string, unknown> | null;
  tool_output: string | null;
  error: string | null;
}

export interface ToolCall {
  tool_name: string;
  tool_input: Record<string, unknown> | null;
  tool_output: string | null;
  duration_ms: number | null;
  error: string | null;
}

// Timeline types for hierarchical display
export interface ToolCallInSkill {
  span_id: string;
  tool_name: string;
  mcp_server: string | null;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  status: string;
  error: string | null;
  skill_weight: number | null;
}

export interface SkillCallTimeline {
  span_id: string;
  skill_name: string;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  confidence: number;
  trigger_reason: string;
  tools: ToolCallInSkill[];
  total_tool_calls: number;
  tool_duration_ms: number;
}

export interface TimelineEvent {
  event_type: string;
  span_id: string | null;
  start_time: string;
  end_time: string | null;
  duration_ms: number;
  skill_name: string | null;
  confidence: number | null;
  trigger_reason: string | null;
  tool_name: string | null;
  mcp_server: string | null;
  model_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  children: TimelineEvent[];
}

export interface TraceDetailWithTimeline {
  trace: Trace;
  spans: Span[];
  timeline: TimelineEvent[];
  skill_invocations: SkillCallTimeline[];
  llm_duration_ms: number;
  tool_duration_ms: number;
  skill_duration_ms: number;
  total_skills: number;
  total_tools: number;
  total_llm_calls: number;
}

export interface UserMessageItem {
  trace_id: string;
  user_id: string;
  session_id: string;
  channel: string;
  user_message: string | null;
  input_tokens: number;
  output_tokens: number;
  model_name: string | null;
  start_time: string;
  duration_ms: number | null;
}

// API functions
export const tracingApi = {
  getOverview: async (
    startDate?: string,
    endDate?: string,
    sourceId?: string,
  ): Promise<OverviewStats> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (sourceId) params.append("source_id", sourceId);
    return request(`/tracing/overview?${params.toString()}`);
  },

  getUsers: async (
    page = 1,
    pageSize = 20,
    filters?: {
      user_id?: string;
      start_date?: string;
      end_date?: string;
      source_id?: string;
    },
  ): Promise<{
    items: UserListItem[];
    total: number;
    page: number;
    page_size: number;
  }> => {
    const params = new URLSearchParams();
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value && value !== "all") params.append(key, value);
      });
    }
    return request(`/tracing/users?${params.toString()}`);
  },

  getUserStats: async (
    userId: string,
    startDate?: string,
    endDate?: string,
    sourceId?: string,
  ): Promise<UserStats> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (sourceId) params.append("source_id", sourceId);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/tracing/users/${encodeURIComponent(userId)}${query}`);
  },

  getTraces: async (
    page = 1,
    pageSize = 20,
    filters?: {
      user_id?: string;
      session_id?: string;
      status?: string;
      start_date?: string;
      end_date?: string;
      source_id?: string;
    },
  ): Promise<{
    items: TraceListItem[];
    total: number;
    page: number;
    page_size: number;
  }> => {
    const params = new URLSearchParams();
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value);
      });
    }
    return request(`/tracing/traces?${params.toString()}`);
  },

  getTraceDetail: async (traceId: string): Promise<TraceDetail> => {
    return request(`/tracing/traces/${traceId}`);
  },

  getModelUsage: async (
    startDate?: string,
    endDate?: string,
    sourceId?: string,
  ): Promise<{ models: ModelUsage[] }> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (sourceId) params.append("source_id", sourceId);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/tracing/models${query}`);
  },

  getToolUsage: async (
    startDate?: string,
    endDate?: string,
    sourceId?: string,
  ): Promise<{ tools: ToolUsage[] }> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (sourceId) params.append("source_id", sourceId);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/tracing/tools${query}`);
  },

  getSessions: async (
    page = 1,
    pageSize = 20,
    filters?: {
      user_id?: string;
      session_id?: string;
      start_date?: string;
      end_date?: string;
      sourceId?: string;
    },
  ): Promise<{
    items: SessionListItem[];
    total: number;
    page: number;
    page_size: number;
  }> => {
    const params = new URLSearchParams();
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value);
      });
    }
    return request(`/tracing/sessions?${params.toString()}`);
  },

  getSessionStats: async (
    sessionId: string,
    startDate?: string,
    endDate?: string,
    sourceId?: string,
  ): Promise<SessionStats> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (sourceId) params.append("source_id", sourceId);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(
      `/tracing/sessions/${encodeURIComponent(sessionId)}${query}`,
    );
  },

  getUserMessages: async (
    page = 1,
    pageSize = 20,
    filters?: {
      user_id?: string;
      session_id?: string;
      start_date?: string;
      end_date?: string;
      query?: string;
      sourceId?: string;
    },
  ): Promise<{
    items: UserMessageItem[];
    total: number;
    page: number;
    page_size: number;
  }> => {
    const params = new URLSearchParams();
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value);
      });
    }
    return request(`/tracing/user-messages?${params.toString()}`);
  },

  exportUserMessages: async (
    filters?: {
      user_id?: string;
      session_id?: string;
      start_date?: string;
      end_date?: string;
      query?: string;
      sourceId?: string;
    },
    format: string = "xlsx",
  ): Promise<Blob> => {
    const params = new URLSearchParams();
    params.append("format", format);
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value);
      });
    }
    // Use the proper API URL and include authorization token
    const { getApiUrl } = await import("../config");
    const url = getApiUrl(`/tracing/user-messages/export?${params.toString()}`);
    const headers = new Headers(buildAuthHeaders());
    const response = await fetch(url, { headers });
    if (!response.ok) {
      // Try to parse error message from response
      let errorMessage = `Export failed: ${response.status} ${response.statusText}`;
      try {
        const errorData = await response.json();
        console.error("Export error response:", errorData);
        if (errorData.detail) {
          errorMessage = errorData.detail;
        }
      } catch {
        // Ignore JSON parse error
      }
      throw new Error(errorMessage);
    }
    return response.blob();
  },

  // Timeline with skill hierarchy
  getTraceTimeline: async (traceId: string): Promise<TraceDetailWithTimeline> => {
    return request(`/tracing/traces/${traceId}/timeline`);
  },

  // Business Overview APIs
  getSources: async (
    startDate?: string,
    endDate?: string,
  ): Promise<{ sources: string[] }> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/tracing/sources${query}`);
  },

  getChannelDistribution: async (
    sourceId?: string,
    startDate?: string,
    endDate?: string,
  ): Promise<{
    platformUserDistribution: { name: string; value: number }[];
    platformCallDistribution: { name: string; value: number }[];
    totalPlatforms: number;
  }> => {
    const params = new URLSearchParams();
    if (sourceId) params.append("source_id", sourceId);
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/tracing/channel-distribution${query}`);
  },

  getGrowthStats: async (
    startDate: string,
    endDate: string,
    timeRange: string = "day",
    sourceId?: string,
  ): Promise<{
    callsGrowth: number;
    tokensGrowth: number;
    sessionGrowth: number;
    userGrowth: number;
    platformGrowth: number;
  }> => {
    const params = new URLSearchParams();
    params.append("start_date", startDate);
    params.append("end_date", endDate);
    params.append("time_range", timeRange);
    if (sourceId) params.append("source_id", sourceId);
    return request(`/tracing/growth-stats?${params.toString()}`);
  },

  getDailyTrend: async (
    startDate?: string,
    endDate?: string,
    sourceId?: string,
  ): Promise<{
    trendData: { date: string; calls: number; tokens: number; users: number }[];
  }> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (sourceId) params.append("source_id", sourceId);
    const query = params.toString() ? `?${params.toString()}` : "";
    return request(`/tracing/daily-trend${query}`);
  },
};