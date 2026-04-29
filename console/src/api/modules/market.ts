import { request } from "../request";
import { buildAuthHeaders } from "../authHeaders";

export interface MarketSkill {
  item_id: string;
  name: string;
  description: string;
  version: string;
  creator_id: string;
  creator_name: string;
  category_id: number | null;
  bbk_ids: string[];
  status: "active" | "inactive";
  created_at: string | null;
  updated_at: string | null;
  call_count: number;
  user_count: number;
}

export interface MarketSkillDetail extends MarketSkill {
  user_stats: Array<{
    user_id: string;
    user_name: string;
    call_count: number;
  }>;
}

export interface Category {
  id: number;
  source_id: string;
  name: string;
  sort_order: number;
}

export interface PublishSkillRequest {
  name: string;
  description: string;
  creator_id: string;
  creator_name: string;
  category_id?: number;
  bbk_ids?: string[];
  skill_json: Record<string, unknown>;
  skill_md?: string;
}

export interface DistributeRequest {
  target_type: "all" | "bbk_id" | "user_id";
  target_values: string[];
}

export interface DistributeResponse {
  distributed_count: number;
  item_id: string;
}

function mergeHeaders(extra?: Record<string, string>): RequestInit {
  const base = buildAuthHeaders();
  const merged: Record<string, string> = { ...base, ...(extra || {}) };
  return { headers: new Headers(merged) };
}

export const marketApi = {
  listCategories: async (sourceId: string): Promise<Category[]> => {
    const opts = mergeHeaders({ "X-Source-Id": sourceId });
    return request<Category[]>("/api/marketplace/categories", opts);
  },

  listMarketSkills: async (
    sourceId: string,
    bbkId: string,
    categoryId?: number
  ): Promise<MarketSkill[]> => {
    let url = "/api/marketplace/skills";
    const params = new URLSearchParams();
    if (categoryId !== undefined) {
      params.append("category_id", String(categoryId));
    }
    if (params.toString()) {
      url += `?${params.toString()}`;
    }
    const opts = mergeHeaders({
      "X-Source-Id": sourceId,
      "X-Bbk-Id": bbkId,
    });
    return request<MarketSkill[]>(url, opts);
  },

  getSkillDetail: async (
    sourceId: string,
    itemId: string,
    bbkId: string
  ): Promise<MarketSkillDetail | null> => {
    const opts = mergeHeaders({
      "X-Source-Id": sourceId,
      "X-Bbk-Id": bbkId,
    });
    return request<MarketSkillDetail | null>(
      `/api/marketplace/skills/${itemId}`,
      opts
    );
  },

  publishSkill: async (
    sourceId: string,
    userId: string,
    userName: string,
    data: PublishSkillRequest
  ): Promise<MarketSkill> => {
    const opts: RequestInit = {
      method: "POST",
      headers: new Headers({
        "Content-Type": "application/json",
        "X-Source-Id": sourceId,
        "X-User-Id": userId,
        "X-User-Name": encodeURIComponent(userName),
        "X-Manager": "true",
      }),
      body: JSON.stringify(data),
    };
    return request<MarketSkill>("/api/marketplace/skills", opts);
  },

  unpublishSkill: async (
    sourceId: string,
    itemId: string,
    userId: string,
    userName: string
  ): Promise<void> => {
    const opts: RequestInit = {
      method: "DELETE",
      headers: new Headers({
        "X-Source-Id": sourceId,
        "X-User-Id": userId,
        "X-User-Name": encodeURIComponent(userName),
        "X-Manager": "true",
      }),
    };
    return request<void>(`/api/marketplace/skills/${itemId}`, opts);
  },

  distributeSkill: async (
    sourceId: string,
    itemId: string,
    userId: string,
    userName: string,
    data: DistributeRequest
  ): Promise<DistributeResponse> => {
    const opts: RequestInit = {
      method: "POST",
      headers: new Headers({
        "Content-Type": "application/json",
        "X-Source-Id": sourceId,
        "X-User-Id": userId,
        "X-User-Name": encodeURIComponent(userName),
        "X-Manager": "true",
      }),
      body: JSON.stringify(data),
    };
    return request<DistributeResponse>(
      `/api/marketplace/skills/${itemId}/distribute`,
      opts
    );
  },
};
