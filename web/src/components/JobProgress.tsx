import { Check, CheckCircle2, Loader2, X, XCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Job, JobEvent } from "../api/client";
import { isActive } from "../api/hooks";
import { cn } from "../lib/utils";

const WRITE_STEPS = [["topic", "定选题"], ["write", "写稿"], ["review", "质检"], ["done", "完成"]] as const;
const CLONE_STEPS = [["find", "读作品"], ["detail", "看爆款"], ["analyze", "拆打法"], ["adapt", "合成方案"]] as const;
const HIDDEN_KEY = "mf.hiddenJobs";

const finishedAt = (j: Job) => (j.finished_at ? new Date(/Z|[+-]\d\d:\d\d$/.test(j.finished_at) ? j.finished_at : j.finished_at + "Z").getTime() : 0);

/** 工作台顶部的任务条：进行中的写稿显示步骤，刚写完的给一个入口，失败的说原因。不再用浮层挡内容。 */
export function JobStrip({ jobs }: { jobs: Job[] }) {
  const [hidden, setHidden] = useState<string[]>(() => JSON.parse(sessionStorage.getItem(HIDDEN_KEY) || "[]"));
  const hide = (id: string) => {
    const next = [...hidden, id];
    setHidden(next);
    sessionStorage.setItem(HIDDEN_KEY, JSON.stringify(next));
  };
  const shown = jobs.filter((j) => {
    if (isActive(j)) return true;
    if (!["write_draft", "clone_creator"].includes(j.kind) || hidden.includes(j.id)) return false; // 配图任务结束后在草稿页看结果即可
    return Date.now() - finishedAt(j) < 10 * 60_000;
  }).slice(0, 2);
  if (!shown.length) return null;
  return <div className="mb-5 space-y-2">{shown.map((j) => <JobRow key={j.id} job={j} onClose={() => hide(j.id)} />)}</div>;
}

function JobRow({ job, onClose }: { job: Job; onClose: () => void }) {
  const events = job.events as JobEvent[];
  const last = events[events.length - 1];
  const draftId = (job.result as { draft_id?: string }).draft_id;
  const title = (job.result as { title?: string }).title;
  const active = isActive(job);

  if (job.kind === "generate_images") {
    return (
      <div className="flex items-center gap-2 rounded-xl border bg-card px-4 py-2.5 text-sm">
        <Loader2 className="size-4 animate-spin text-indigo-500" />正在生成配图<span className="truncate text-xs text-muted-foreground">{last?.message}</span>
      </div>
    );
  }
  const clone = job.kind === "clone_creator";
  if (job.status === "failed") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
        <XCircle className="size-4 shrink-0" /><span className="font-medium">{clone ? "复刻没做成" : "没写成"}</span>
        <span className="min-w-0 flex-1 truncate text-xs">{job.error || "未知错误"}</span>
        <button onClick={onClose} className="cursor-pointer opacity-60 hover:opacity-100" aria-label="知道了"><X className="size-4" /></button>
      </div>
    );
  }
  if (!active) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-800">
        <CheckCircle2 className="size-4 shrink-0" />
        {clone ? <>
        <span className="min-w-0 flex-1 truncate">复刻方案做好了：定位、规则和复刻选题已同步</span>
        <Link to={`/accounts/${job.account_id}?tab=bench`} className="shrink-0 font-medium hover:underline">查看复刻方案 →</Link>
        </> : <>
        <span className="min-w-0 flex-1 truncate">写好了{title ? `：${title}` : last?.message ? `：${last.message.replace(/^草稿已保存：/, "")}` : ""}</span>
        {draftId && <Link to={`/drafts/${draftId}`} className="shrink-0 font-medium hover:underline">去审核 →</Link>}
        </>}
        <button onClick={onClose} className="cursor-pointer opacity-60 hover:opacity-100" aria-label="关闭"><X className="size-4" /></button>
      </div>
    );
  }
  const STEPS = clone ? CLONE_STEPS : WRITE_STEPS;
  const seen = new Set(events.map((e) => e.stage));
  const cur = STEPS.findIndex(([s]) => !seen.has(s));
  return (
    <div className="rounded-xl border border-indigo-200 bg-card px-4 py-3">
      <div className="mb-2.5 flex items-center gap-2 text-sm font-medium">
        <Loader2 className="size-4 animate-spin text-indigo-500" />{job.status === "queued" ? "排队中…" : clone ? "正在复刻对标账号" : "AI 正在写稿"}
        <span className="truncate text-xs font-normal text-muted-foreground">{last?.message ?? "准备中…"}</span>
      </div>
      <div className="flex items-center gap-1.5">
        {STEPS.map(([s, label], i) => {
          const done = seen.has(s);
          const now = i === cur;
          return (
            <div key={s} className="flex flex-1 items-center gap-1.5">
              <span className={cn("flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                done ? "bg-indigo-500 text-white" : now ? "border-2 border-indigo-400 text-indigo-500" : "bg-muted text-muted-foreground")}>
                {done ? <Check className="size-3" /> : i + 1}
              </span>
              <span className={cn("text-xs", done || now ? "text-foreground" : "text-muted-foreground")}>{label}</span>
              {i < STEPS.length - 1 && <span className={cn("h-px flex-1", done ? "bg-indigo-300" : "bg-border")} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
