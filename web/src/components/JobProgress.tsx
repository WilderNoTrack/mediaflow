import { CheckCircle2, Loader2, X, XCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Job, JobEvent } from "../api/client";
import { isActive } from "../api/hooks";

const KIND = { write_draft: "AI 正在创作", generate_images: "正在生成配图", clone_creator: "正在拆解对标账号" } as const;
const STAGES = ["topic", "write", "review", "done"];
const CLONE_STAGES = ["find", "detail", "analyze", "adapt", "done"];

/** 右下角浮动的任务进度卡（对应 v1 的 GenerationProgress） */
export function JobDock({ jobs }: { jobs: Job[] }) {
  const [hidden, setHidden] = useState<string[]>([]);
  // 只显示进行中的任务和 2 分钟内刚结束的任务，避免旧任务一直挂着
  const recent = (j: Job) => !!j.finished_at && Date.now() - new Date(j.finished_at.endsWith("Z") || j.finished_at.includes("+") ? j.finished_at : j.finished_at + "Z").getTime() < 120_000;
  const shown = jobs.filter((j) => isActive(j) || (recent(j) && !hidden.includes(j.id))).slice(0, 3);
  if (!shown.length) return null;
  return (
    <div className="fixed bottom-6 right-6 z-50 w-80 space-y-3">
      {shown.map((j) => <JobCard key={j.id} job={j} onClose={() => setHidden([...hidden, j.id])} />)}
    </div>
  );
}

function JobCard({ job, onClose }: { job: Job; onClose: () => void }) {
  const events = job.events as JobEvent[];
  const last = events[events.length - 1];
  const draftId = (job.result as { draft_id?: string }).draft_id;
  const active = isActive(job);
  const seen = new Set(events.map((e) => e.stage));
  const stages = job.kind === "clone_creator" ? CLONE_STAGES : STAGES;
  const pct = job.status === "succeeded" ? 100 : Math.max(8, Math.round((stages.filter((s) => seen.has(s)).length / stages.length) * 100));
  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-xl">
      <div className="flex items-center gap-2 px-4 pt-3">
        {active ? <Loader2 className="size-4 animate-spin text-indigo-500" />
          : job.status === "succeeded" ? <CheckCircle2 className="size-4 text-green-600" /> : <XCircle className="size-4 text-red-600" />}
        <span className="flex-1 text-sm font-medium">
          {job.status === "queued" ? "排队中…" : active ? KIND[job.kind] : job.status === "succeeded" ? "完成" : "失败了"}
        </span>
        {!active && <button onClick={onClose} className="cursor-pointer text-muted-foreground hover:text-foreground" aria-label="关闭"><X className="size-4" /></button>}
      </div>
      <div className="px-4 pb-3 pt-1.5">
        <p className="line-clamp-2 text-xs text-muted-foreground">
          {job.status === "failed" ? job.error || "未知错误" : last?.message ?? "准备中…"}
        </p>
        {job.kind !== "generate_images" && (
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div className={`h-full rounded-full transition-all ${job.status === "failed" ? "bg-red-400" : "bg-brand-gradient"}`} style={{ width: `${pct}%` }} />
          </div>
        )}
        {draftId && job.status === "succeeded" && job.kind === "write_draft" && (
          <Link to={`/drafts/${draftId}`} className="mt-2 inline-block text-xs font-medium text-indigo-600 hover:underline">查看草稿 →</Link>
        )}
        {job.kind === "clone_creator" && job.status === "succeeded" && (
          <Link to={`/accounts/${job.account_id}?tab=bench`} className="mt-2 inline-block text-xs font-medium text-indigo-600 hover:underline">查看复刻方案 →</Link>
        )}
      </div>
    </div>
  );
}
