import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

const toDate = (iso: string) => new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - toDate(iso).getTime()) / 1000);
  if (s < 60) return "刚刚";
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`;
  return `${Math.floor(s / 86400)} 天前`;
}

export const dateStr = (iso: string) => toDate(iso).toLocaleDateString("zh-CN");

export const DRAFT_STATUS: Record<string, { label: string; cls: string }> = {
  pending_review: { label: "待审核", cls: "bg-amber-100 text-amber-700" },
  approved: { label: "可以发", cls: "bg-green-100 text-green-700" },
  exported: { label: "已导出", cls: "bg-blue-100 text-blue-700" },
  rejected: { label: "不要了", cls: "bg-gray-100 text-gray-600" },
};

/** 与 v1 一致的平台色 */
export const PLATFORMS: Record<string, { label: string; cls: string }> = {
  xiaohongshu: { label: "小红书", cls: "bg-rose-100 text-rose-600" },
  zhihu: { label: "知乎", cls: "bg-sky-100 text-sky-700" },
  weibo: { label: "微博", cls: "bg-orange-100 text-orange-700" },
  baidu: { label: "百度", cls: "bg-blue-100 text-blue-700" },
  bilibili: { label: "B站", cls: "bg-cyan-100 text-cyan-700" },
  douyin: { label: "抖音", cls: "bg-slate-100 text-slate-700" },
  wechat: { label: "微信文章", cls: "bg-emerald-100 text-emerald-700" },
  ai: { label: "AI 推荐", cls: "bg-indigo-100 text-indigo-700" },
  user: { label: "手动", cls: "bg-gray-100 text-gray-700" },
};

export const FREQ_LABEL: Record<string, string> = { daily: "每天", every_2_days: "每 2 天", weekly: "每周" };
