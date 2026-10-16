import { CheckCircle2, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import type { Job, JobEvent } from "../api/client";
import { isActive } from "../api/hooks";
import { Spinner } from "./ui";

const KIND = { write_draft: "写稿", generate_images: "配图" } as const;

export function JobProgress({ job }: { job: Job }) {
  const events = job.events as JobEvent[];
  const last = events[events.length - 1];
  const draftId = (job.result as { draft_id?: string }).draft_id;
  return (
    <div className="flex items-start gap-2 rounded-lg bg-surface px-3 py-2 text-sm">
      <div className="pt-0.5">
        {isActive(job) ? <Spinner /> : job.status === "succeeded" ? <CheckCircle2 className="size-4 text-emerald-600" /> : <XCircle className="size-4 text-red-600" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="font-medium">
          {KIND[job.kind]}
          {job.status === "queued" && <span className="ml-1 font-normal text-muted">排队中</span>}
        </div>
        <div className="truncate text-muted">
          {job.status === "failed" ? job.error || "失败了" : last?.message ?? "准备中…"}
        </div>
        {draftId && job.status === "succeeded" && job.kind === "write_draft" && (
          <Link to={`/drafts/${draftId}`} className="text-brand hover:underline">查看草稿 →</Link>
        )}
      </div>
    </div>
  );
}
