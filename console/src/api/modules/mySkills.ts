import { request } from "../request";
import { buildAuthHeaders } from "../authHeaders";

export interface MySkill {
  skill_name: string;
  source: string;
  description: string;
  version: string | null;
  received_version: string | null;
  distributed_by: string | null;
  is_received: boolean;
  has_update: boolean;
}

function mergeHeaders(extra?: Record<string, string>): RequestInit {
  const base = buildAuthHeaders();
  const merged: Record<string, string> = { ...base, ...(extra || {}) };
  return { headers: new Headers(merged) };
}

export const mySkillsApi = {
  getCreatedSkills: async (
    sourceId: string,
    userId: string
  ): Promise<MySkill[]> => {
    const opts = mergeHeaders({
      "X-Source-Id": sourceId,
      "X-User-Id": userId,
    });
    const all = await request<MySkill[]>("/api/skills/mine", opts);
    return all.filter((s) => !s.is_received);
  },

  getReceivedSkills: async (
    sourceId: string,
    userId: string
  ): Promise<MySkill[]> => {
    const opts = mergeHeaders({
      "X-Source-Id": sourceId,
      "X-User-Id": userId,
    });
    const all = await request<MySkill[]>("/api/skills/received", opts);
    return all.filter((s) => s.is_received);
  },
};
