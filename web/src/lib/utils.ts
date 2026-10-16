import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "刚刚";
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`;
  return `${Math.floor(s / 86400)} 天前`;
}

export const DRAFT_STATUS: Record<string, { label: string; tone: "brand" | "green" | "gray" | "amber" }> = {
  pending_review: { label: "待审核", tone: "amber" },
  approved: { label: "可以发", tone: "green" },
  exported: { label: "已导出", tone: "gray" },
  rejected: { label: "不要了", tone: "gray" },
};

export const SOURCE_LABEL: Record<string, string> = {
  weibo: "微博", baidu: "百度", bilibili: "B站", douyin: "抖音", ai: "AI", user: "手动",
};

export const FREQ_LABEL: Record<string, string> = { daily: "每天", every_2_days: "每 2 天", weekly: "每周" };
