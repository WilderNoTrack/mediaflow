import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });

export type S = components["schemas"];
export type Account = S["AccountDetail"];
export type AccountSummary = S["AccountSummary"];
export type Draft = S["DraftOut"];
export type DraftDetail = S["DraftDetail"];
export type Topic = S["TopicOut"];
export type Job = S["JobOut"];
export type ChatMessage = S["ChatMessageOut"];
export type Benchmark = S["BenchmarkOut"];
/** 对标候选（后端 find_candidates 返回的一条） */
export type Candidate = {
  name: string; url: string; avatar?: string; fans?: string; desc?: string;
  median_likes?: number; hit_rate?: number; per_week?: number | null; last_post?: string;
  hits?: { title: string; likes: string; url: string }[]; top?: { title: string; likes: string; url: string }[];
  fit?: number; level?: string; reason?: string; learn?: string;
};
export type JobEvent = { at: string; stage: string; message: string; data: Record<string, unknown> };

export class ApiError extends Error {
  constructor(message: string, public status: number, public body: unknown) {
    super(message);
  }
}

/** openapi-fetch 返回 {data, error}，这里统一成「成功返回数据、失败抛错」。 */
export async function unwrap<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || !response.ok) {
    const detail = (error as { detail?: unknown })?.detail;
    const msg = typeof detail === "string" ? detail : `请求失败（${response.status}）`;
    throw new ApiError(msg, response.status, error);
  }
  return data as T;
}
