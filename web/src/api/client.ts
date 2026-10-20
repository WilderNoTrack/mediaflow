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
/** 配图做法：账号默认怎么出图 */
export type AccountImageMode = "ai" | "mixed" | "card" | "photo" | "auto";
export const ACCOUNT_IMAGE_MODES: { value: AccountImageMode; label: string; desc: string; ai?: boolean }[] = [
  { value: "ai", label: "AI 画", desc: "整张图交给 AI 画，图上的字也让 AI 写（偶尔会写错字）", ai: true },
  { value: "mixed", label: "AI 画面 + 排字", desc: "AI 只画画面，标题和要点用代码排上去：字一定对，还能直接改", ai: true },
  { value: "card", label: "排版卡片", desc: "代码排的文字卡片（封面大字、清单、步骤、对比、金句），不用生图额度" },
  { value: "photo", label: "网上找图", desc: "去网上找真实照片当底图，再用代码叠字；会标出处，发之前确认能用" },
  { value: "auto", label: "自动", desc: "每张自己挑最合适的做法（有字的页排版，要真实感的找图，其余 AI 画）" },
];
/** 每张图的做法 */
export type ImageMode = "ai" | "ai_text" | "card" | "photo";
export const IMAGE_MODES: { value: ImageMode; label: string; ai?: boolean }[] = [
  { value: "ai", label: "AI 画", ai: true },
  { value: "ai_text", label: "AI 画面 + 排字", ai: true },
  { value: "card", label: "排版卡片" },
  { value: "photo", label: "网上找图" },
];
export const imageModeLabel = (m?: string) => IMAGE_MODES.find((x) => x.value === m)?.label ?? "";
export type ImageLayout = S["ImageLayout"];
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
