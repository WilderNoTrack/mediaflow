import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, FileText, ImageIcon, Loader2, PenLine, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap, type Account, type Job, type JobEvent } from "../api/client";
import { isActive, useDrafts, useTopics, useWrite } from "../api/hooks";
import { cn } from "../lib/utils";
import { ReportDialog } from "./BenchmarkPanel";
import { Badge, Button, ErrorText } from "./ui";

/** 对话里派出去的后台任务：边做边显示进度，做完直接给结果卡片（草稿 / 对标方案）。 */
export function ChatJobCard({ account, jobId }: { account: Account; jobId: string }) {
  const qc = useQueryClient();
  const { data: job } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId } } })),
    refetchInterval: (q) => (q.state.data && !isActive(q.state.data) ? false : 1500),
  });
  const done = job && !isActive(job);
  useEffect(() => {
    if (done) {
      qc.invalidateQueries({ queryKey: ["drafts", account.id] });
      qc.invalidateQueries({ queryKey: ["account", account.id] });
    }
  }, [done, qc, account.id]);
  if (!job) return null;
  if (job.status === "failed") {
    return (
      <Shell className="border-red-200 bg-red-50 text-red-700">
        <XCircle className="size-4 shrink-0" /><span className="min-w-0 flex-1">{job.kind === "clone_creator" ? "没学成" : "没写成"}：{job.error || "未知错误"}</span>
      </Shell>
    );
  }
  if (isActive(job)) return <Running job={job} />;
  const draftId = (job.result as { draft_id?: string }).draft_id;
  if (draftId) return <DraftCard account={account} draftId={draftId} />;
  if (job.kind === "clone_creator") return <PlanCard account={account} />;
  return null;
}

function Shell({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("ml-10 flex items-center gap-2 rounded-xl border bg-card px-3 py-2.5 text-sm shadow-sm", className)}>{children}</div>;
}

const LABEL: Record<string, string> = { write_draft: "正在写稿", clone_creator: "正在学习对标账号", revise_draft: "正在改稿" };

function Running({ job }: { job: Job }) {
  const events = job.events as JobEvent[];
  const last = events[events.length - 1];
  return (
    <Shell className="border-indigo-200">
      <Loader2 className="size-4 shrink-0 animate-spin text-indigo-500" />
      <div className="min-w-0 flex-1">
        <div className="font-medium">{job.status === "queued" ? "排队中…" : LABEL[job.kind] ?? "处理中"}</div>
        <div className="truncate text-xs text-muted-foreground">{last?.message ?? "准备中…"}{job.kind === "write_draft" && " · 一般 1-3 分钟，可以先去忙"}</div>
      </div>
    </Shell>
  );
}

/** 写好的稿子：封面 + 标题 + 打分 + 出图进度，点开去审核 */
export function DraftCard({ account, draftId }: { account: Account; draftId: string }) {
  const { data: drafts = [] } = useDrafts(account.id);
  const d = drafts.find((x) => x.id === draftId);
  if (!d) return null;
  const imgs = d.images_total ? `${d.images_done}/${d.images_total} 张图` : "";
  return (
    <Link to={`/drafts/${d.id}`} className="ml-10 flex gap-3 rounded-xl border-2 border-emerald-200 bg-card p-3 shadow-sm transition-colors hover:border-emerald-300">
      <div className="h-24 w-[72px] shrink-0 overflow-hidden rounded-lg bg-muted">
        {d.cover_url ? <img src={d.cover_url} alt="" className="size-full object-cover" />
          : <div className="flex size-full items-center justify-center text-muted-foreground">{d.images_busy ? <Loader2 className="size-4 animate-spin" /> : <ImageIcon className="size-4" />}</div>}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-1.5 text-xs text-emerald-700"><CheckCircle2 className="size-3.5" />写好了</div>
        <div className="mt-0.5 line-clamp-2 font-medium">{d.title}</div>
        {typeof d.reference?.title === "string" && <div className="mt-0.5 truncate text-xs text-muted-foreground">
          照着「{d.reference.title}」{Array.isArray(d.reference.extra) && d.reference.extra.length > 0 ? `等 ${d.reference.extra.length + 1} 篇` : ""}做的
        </div>}
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          {d.score != null && <Badge className={d.needs_attention ? "bg-amber-100 text-amber-700" : "bg-indigo-50 text-indigo-600"}>AI 打分 {d.score.toFixed(1)}</Badge>}
          {imgs && <span>{d.images_busy ? <>配图出到 {imgs}…</> : imgs}</span>}
        </div>
        <span className="mt-auto flex items-center gap-1 pt-1 text-xs font-medium text-indigo-600">打开看看、改改 <ArrowRight className="size-3" /></span>
      </div>
    </Link>
  );
}

/** 对标学完：一句话结果 + 看报告 */
function PlanCard({ account }: { account: Account }) {
  const [open, setOpen] = useState(false);
  const plan = account.bench_plan as { summary?: string; applied?: { topics?: string[] } };
  const n = plan.applied?.topics?.length ?? 0;
  return (
    <div className="ml-10 space-y-2 rounded-xl border-2 border-emerald-200 bg-card p-3 text-sm shadow-sm">
      <div className="flex items-center gap-1.5 text-xs text-emerald-700"><CheckCircle2 className="size-3.5" />学完了，设定已经帮你改好</div>
      {plan.summary && <p className="line-clamp-3 leading-relaxed">{plan.summary}</p>}
      <div className="flex flex-wrap gap-2 pt-1">
        <Link to={`/accounts/${account.id}?tab=topics`}><Button size="xs" variant="gradient">看 {n} 个复刻选题<ArrowRight /></Button></Link>
        <Button size="xs" variant="outline" onClick={() => setOpen(true)}><FileText />完整报告</Button>
      </div>
      {open && <ReportDialog account={account} onClose={() => setOpen(false)} />}
    </div>
  );
}

/** 小媒找的选题：每个都能直接点「写这篇」 */
export function TopicCards({ account, topics }: { account: Account; topics: { id: string; title: string; angle?: string }[] }) {
  const write = useWrite(account.id);
  const qc = useQueryClient();
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const { data: all = [] } = useTopics(account.id);
  const used = (id: string) => all.find((x) => x.id === id)?.status === "used";
  return (
    <div className="ml-10 space-y-2">
      <div className="divide-y rounded-xl border bg-card text-sm shadow-sm">
        {topics.map((t) => (
          <div key={t.id} className="flex items-center gap-2 px-3 py-2">
            <div className="min-w-0 flex-1">
              <div className="font-medium">{t.title}</div>
              {t.angle && <div className="truncate text-xs text-muted-foreground">{t.angle}</div>}
            </div>
            {jobs[t.id] || used(t.id) ? <span className="shrink-0 text-xs text-emerald-600">{jobs[t.id] ? "已开始写" : "写过了"}</span> : (
              <Button size="xs" variant="outline" className="shrink-0" disabled={write.isPending}
                onClick={() => write.mutate({ topic_id: t.id, hint: "", from_chat: true }, {
                  onSuccess: (j) => { setJobs((m) => ({ ...m, [t.id]: j.id })); qc.invalidateQueries({ queryKey: ["chat", account.id] }); },
                })}>
                <PenLine />写这篇
              </Button>
            )}
          </div>
        ))}
      </div>
      <ErrorText error={write.error} />
    </div>
  );
}
