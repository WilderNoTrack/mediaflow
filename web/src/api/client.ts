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
  hits?: NoteCard[]; top?: NoteCard[]; notes?: NoteCard[];
  fit?: number; level?: string; reason?: string; learn?: string; platform?: string;
};
/** 能找对标的平台（抖音只看图文号） */
export type BenchPlatform = "xiaohongshu" | "douyin" | "weibo";
export const BENCH_PLATFORMS: { value: BenchPlatform; label: string; cred: string }[] = [
  { value: "xiaohongshu", label: "小红书", cred: "xhs_cookie" },
  { value: "douyin", label: "抖音图文", cred: "douyin_cookie" },
  { value: "weibo", label: "微博", cred: "weibo_cookie" },
];
export const platformLabel = (p?: string) =>
  ({ xiaohongshu: "小红书", douyin: "抖音", weibo: "微博", bilibili: "B站", zhihu: "知乎" } as Record<string, string>)[p ?? ""] ?? "小红书";
export type NoteCard = { title: string; likes: string; url: string; cover?: string; kind?: string; date?: string };
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
