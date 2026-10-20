import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, ChevronDown, ChevronRight, FileText, ImageIcon, Loader2, Palette, PenLine, ScrollText, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap, type Account, type Job, type JobEvent } from "../api/client";
import { isActive, useDrafts, useTopics, useWrite } from "../api/hooks";
import { cn } from "../lib/utils";
import { ReportDialog } from "./BenchmarkPanel";
import { Badge, Button, ErrorText } from "./ui";

function useJob(jobId?: string) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId! } } })),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && !isActive(q.state.data) ? false : 1500),
  });
}

/** 对话里派出去的后台任务：边做边显示进度和完整过程，做完直接给结果卡片（草稿 / 对标方案）。 */
export function ChatJobCard({ account, jobId, draftId: forDraft }: { account: Account; jobId: string; draftId?: string }) {
  const qc = useQueryClient();
  const { data: job } = useJob(jobId);
  // 写完稿接着出图：出图任务的过程也接在这张卡片下面
  const { data: imgJob } = useJob((job?.result as { images_job_id?: string } | undefined)?.images_job_id);
  const done = job && !isActive(job);
  useEffect(() => {
    if (done) {
      qc.invalidateQueries({ queryKey: ["drafts", account.id] });
      qc.invalidateQueries({ queryKey: ["account", account.id] });
      qc.invalidateQueries({ queryKey: ["draft"] });
    }
  }, [done, qc, account.id]);
  if (!job) return null;
  const jobs = imgJob ? [job, imgJob] : [job];
  const log = <JobLog jobs={jobs} live={jobs.some(isActive)} />;
  let card: React.ReactNode = null;
  if (job.status === "failed") {
    card = (
      <Shell className="border-red-200 bg-red-50 text-red-700">
        <XCircle className="size-4 shrink-0" /><span className="min-w-0 flex-1">{FAIL[job.kind] ?? "没写成"}：{job.error || "未知错误"}</span>
      </Shell>
    );
  } else if (isActive(job)) card = <Running job={job} />;
  else {
    const draftId = (job.result as { draft_id?: string }).draft_id ?? forDraft;
    if (draftId) card = <DraftCard account={account} draftId={draftId} />;
    else if (job.kind === "clone_creator") card = <PlanCard account={account} />;
    else if (job.kind === "learn_visual") {
      const pages = (job.result as { pages?: string[] }).pages ?? [];
      card = (
        <Shell className="border-emerald-200">
          <Palette className="size-4 shrink-0 text-emerald-600" />
          <span className="min-w-0 flex-1">配图模板学好了：{pages.length} 种页（{pages.join("、")}），以后每篇照它出图</span>
          <Link to={`/accounts/${account.id}?tab=config`} className="shrink-0 text-xs font-medium text-indigo-600 hover:underline">去看看 →</Link>
        </Shell>
      );
    }
  }
  return <div className="space-y-1.5">{card}{log}</div>;
}

function Shell({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("ml-10 flex items-center gap-2 rounded-xl border bg-card px-3 py-2.5 text-sm shadow-sm", className)}>{children}</div>;
}

const LABEL: Record<string, string> = { write_draft: "正在写稿", clone_creator: "正在学习对标账号", revise_draft: "正在改稿", generate_images: "正在出图",
  learn_visual: "正在看图学配图模板" };
const FAIL: Record<string, string> = { clone_creator: "没学成", revise_draft: "没改成", generate_images: "没出成", learn_visual: "配图模板没学成" };

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

// ── 完整过程日志 ─────────────────────────────────────────────────────

const LOG_TITLE: Record<string, string> = { write_draft: "写作过程", revise_draft: "改稿过程", generate_images: "出图过程",
  clone_creator: "学习过程", learn_visual: "看图过程", find_benchmarks: "查找过程" };
const STAGE_ICON: Record<string, string> = { topic: "🔍", reference: "📎", write: "✍️", review: "🧐", image: "🖼", warning: "⚠️",
  error: "❌", done: "✅", visual: "🎨", find: "📚", detail: "📄", analyze: "🔬", adapt: "🧩" };
const DIM: Record<string, string> = { hook: "吸引力", value: "价值感", voice: "人设口吻", fit: "贴合定位", rules: "守规矩" };
const toMs = (t?: string | null) => (t ? new Date(/Z|[+-]\d\d:\d\d$/.test(t) ? t : t + "Z").getTime() : 0);

function clock(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** 后台任务的每一步：做了什么、看到了什么、为什么这么定。进行中展开、实时追加；做完收起，想看再点开。 */
export function JobLog({ jobs, live }: { jobs: Job[]; live: boolean }) {
  const [open, setOpen] = useState<boolean | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const events = jobs.flatMap((j) => (j.events as JobEvent[]).map((e) => ({ ...e, job: j.kind })));
  const t0 = toMs(jobs[0].started_at ?? jobs[0].created_at) || toMs(events[0]?.at);
  const end = live ? Date.now() : Math.max(...jobs.map((j) => toMs(j.finished_at)), toMs(events.at(-1)?.at));
  const warns = events.filter((e) => e.stage === "warning").length;
  const shown = open ?? live;
  useEffect(() => {
    if (shown && live && list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [events.length, shown, live]);
  if (!events.length) return null;
  return (
    <div className="ml-10 rounded-lg border border-slate-200 bg-white/80 text-xs">
      <button onClick={() => setOpen(!shown)} className="flex w-full cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-left">
        <ScrollText className="size-3.5 shrink-0 text-indigo-500" />
        <span className="font-medium">{LOG_TITLE[jobs[0].kind] ?? "过程"}</span>
        <span className="text-muted-foreground">
          · {events.length} 步{t0 && end > t0 ? ` · ${live ? "已" : ""}用时 ${clock(end - t0)}` : ""}
          {warns > 0 && <span className="text-amber-600"> · {warns} 处提醒</span>}
        </span>
        <span className="ml-auto shrink-0 text-indigo-600">{shown ? "收起" : "展开看每一步"}</span>
        <ChevronDown className={cn("size-3.5 shrink-0 text-indigo-600 transition-transform", shown && "rotate-180")} />
      </button>
      {shown && (
        <div ref={list} className="max-h-[420px] space-y-0.5 overflow-y-auto border-t border-slate-100 px-1.5 py-1.5">
          {events.map((e, i) => <LogRow key={i} e={e} t={t0 ? toMs(e.at) - t0 : 0} first={i === 0 || events[i - 1].job !== e.job} />)}
          {live && <div className="flex items-center gap-1.5 px-1 py-0.5 text-muted-foreground"><Loader2 className="size-3 animate-spin" />进行中…</div>}
        </div>
      )}
    </div>
  );
}

function LogRow({ e, t, first }: { e: JobEvent & { job: string }; t: number; first: boolean }) {
  const detail = eventDetail(e);
  const [open, setOpen] = useState(false);
  const tone = e.stage === "warning" ? "text-amber-700" : e.stage === "error" ? "text-red-600" : e.stage === "done" ? "text-emerald-700" : "";
  return (
    <div>
      {first && e.job === "generate_images" && <div className="mt-1 border-t border-dashed border-slate-200 px-1 pt-1.5 font-medium text-muted-foreground">出图</div>}
      <button onClick={() => detail && setOpen(!open)}
        className={cn("flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left", detail && "cursor-pointer hover:bg-slate-100")}>
        <span className="w-9 shrink-0 tabular-nums text-muted-foreground">{clock(t)}</span>
        <span className="shrink-0">{STAGE_ICON[e.stage] ?? "•"}</span>
        <span className={cn("min-w-0 flex-1 break-words leading-relaxed", tone)}>{e.message}</span>
        {detail && <span className="flex shrink-0 items-center gap-0.5 pl-1 text-indigo-500">详情<ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} /></span>}
      </button>
      {open && detail && <div className="mb-1 ml-14 space-y-1.5 rounded-md bg-slate-50 px-2.5 py-2 leading-relaxed">{detail}</div>}
    </div>
  );
}

type Loose = Record<string, unknown>;
const arr = (v: unknown) => (Array.isArray(v) ? (v as Loose[]) : []);
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));

function Ext({ url, children }: { url?: unknown; children: React.ReactNode }) {
  const u = str(url);
  return u.startsWith("http") ? <a href={u} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{children}</a> : <>{children}</>;
}

function Sec({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><div className="mb-0.5 font-medium text-foreground/80">{title}</div>{children}</div>;
}

/** 每种事件带的数据 → 人能看懂的详情（没有可展开的返回 null） */
function eventDetail(e: JobEvent): React.ReactNode {
  const d = (e.data ?? {}) as Loose;
  const out: React.ReactNode[] = [];
  const sources = arr(d.sources);
  if (sources.length) {
    const label = new Map(sources.map((x) => [str(x.source), str(x.label)]));
    out.push(<Sec key="src" title="热点来源">
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">{sources.map((x) => (
        <span key={str(x.source)} className={x.ok ? "text-emerald-700" : x.mode === "off" ? "text-muted-foreground" : "text-red-600"}>
          {x.ok ? "✓" : x.mode === "off" ? "–" : "✗"} {str(x.label)}{x.ok ? ` ${str(x.count)} 条` : ""}{x.note ? `（${str(x.note)}）` : x.mode === "off" ? "（未启用）" : ""}
        </span>))}</div>
    </Sec>);
    const hot = arr(d.hot);
    if (hot.length) out.push(<Sec key="hot" title={`抓到的热点（前 ${hot.length} 条）`}>
      <ol className="list-decimal space-y-0.5 pl-4">{hot.map((h, i) => (
        <li key={i}><span className="text-muted-foreground">[{label.get(str(h.source)) || str(h.source)}]</span> <Ext url={h.url}>{str(h.title)}</Ext>
          {h.heat ? <span className="text-muted-foreground"> · {str(h.heat)}</span> : null}</li>))}</ol>
    </Sec>);
  }
  const cands = arr(d.candidates);
  if (cands.length) {
    out.push(<Sec key="cand" title="候选选题（按账号定位和热点想的，选了第一个）">
      <ol className="list-decimal space-y-1 pl-4">{cands.map((c, i) => (
        <li key={i} className={i === Number(d.picked ?? 0) ? "font-medium" : ""}>
          {i === Number(d.picked ?? 0) && "★ "}<Ext url={c.url}>{str(c.title)}</Ext>
          {c.angle ? <div className="font-normal text-muted-foreground">角度：{str(c.angle)}</div> : null}
          {c.reason ? <div className="font-normal text-muted-foreground">为什么写：{str(c.reason)}</div> : null}
        </li>))}</ol>
      {Number(d.skipped_dups) > 0 && <div className="mt-0.5 text-muted-foreground">另有 {str(d.skipped_dups)} 个和以前写过的太像，跳过了</div>}
    </Sec>);
  } else if (e.stage === "topic" && (d.angle || d.reason)) {
    out.push(<Sec key="topic" title="这个选题">
      {d.angle ? <div>角度：{str(d.angle)}</div> : null}{d.reason ? <div>为什么写：{str(d.reason)}</div> : null}
      {d.source ? <div className="text-muted-foreground">来源：<Ext url={d.url}>{str(d.source)}</Ext></div> : null}
    </Sec>);
  }
  const ref = d.reference as Loose | undefined;
  if (ref && ref.title) {
    out.push(<Sec key="ref" title="主参考帖">
      <div><Ext url={ref.url}>「{str(ref.title)}」</Ext> <span className="text-muted-foreground">{str(ref.creator) || "同领域博主"} · {str(ref.likes) || "?"} 赞</span></div>
      {ref.why ? <div className="text-muted-foreground">为什么选它：{str(ref.why)}</div> : null}
    </Sec>);
    const extra = arr(d.extra_posts);
    if (extra.length) out.push(<Sec key="extra" title="文案还参考了">
      <ul className="space-y-0.5">{extra.map((x, i) => <li key={i}>· <Ext url={x.url}>「{str(x.title)}」</Ext> <span className="text-muted-foreground">{str(x.creator)} · {str(x.likes) || "?"} 赞</span></li>)}</ul>
    </Sec>);
  }
  const fb = Array.isArray(d.feedback) ? (d.feedback as string[]) : [];
  if (fb.length) out.push(<Sec key="fb" title="这一轮要落实的意见">
    <ol className="list-decimal space-y-0.5 pl-4">{fb.map((x, i) => <li key={i}>{x}</li>)}</ol>
  </Sec>);
  const fit = d.title_fit as Loose | undefined;
  if (fit) out.push(<Sec key="fit" title="标题改短">
    <div>「{str(fit.before)}」（{str(fit.before).length} 字）→「{str(fit.after)}」（{str(fit.after).length} 字）</div>
  </Sec>);
  if (e.stage === "review" && d.title) {
    const ev = (d.evaluation ?? {}) as Loose;
    const dims = (ev.dimensions ?? {}) as Record<string, number>;
    out.push(<Sec key="ver" title="这一版">
      <div>标题：{str(d.title)}</div>
      <div className="text-muted-foreground">正文 {str(d.body_len)} 字 · 标签 {arr(d.tags).length || (Array.isArray(d.tags) ? d.tags.length : 0)} 个 · 配图 {str(d.images)} 张</div>
    </Sec>);
    if (Object.keys(dims).length) out.push(<Sec key="dims" title={`AI 打分 ${str(d.score)}`}>
      <div className="flex flex-wrap gap-1">{Object.entries(dims).map(([k, v]) => (
        <span key={k} className={cn("rounded px-1.5 py-0.5", v >= 8 ? "bg-emerald-50 text-emerald-700" : v >= 7 ? "bg-slate-100" : "bg-amber-50 text-amber-700")}>{DIM[k] ?? k} {v}</span>))}</div>
    </Sec>);
    const violated = Array.isArray(ev.violated_rules) ? (ev.violated_rules as string[]) : [];
    if (violated.length) out.push(<Sec key="vr" title="没遵守的规则"><ul className="space-y-0.5 text-red-600">{violated.map((x, i) => <li key={i}>· {x}</li>)}</ul></Sec>);
    const items = arr(ev.items);
    const issues = Array.isArray(d.issues) ? (d.issues as string[]) : [];
    if (items.length) out.push(<Sec key="items" title="AI 挑的问题">
      <ul className="space-y-1">{items.map((it, i) => (
        <li key={i}><Badge className={it.level === "must" ? "bg-red-50 text-red-600" : "bg-slate-100 text-slate-600"}>{it.level === "must" ? "必须改" : "可以更好"}</Badge>{" "}
          {it.where ? <span className="text-muted-foreground">{str(it.where)}：</span> : null}{str(it.problem)}
          {it.fix ? <div className="text-muted-foreground">改法：{str(it.fix)}</div> : null}</li>))}</ul>
    </Sec>);
    else if (issues.length) out.push(<Sec key="iss" title="问题"><ul className="space-y-0.5">{issues.map((x, i) => <li key={i}>· {x}</li>)}</ul></Sec>);
  }
  const changes = arr(d.changes);
  if (changes.length) out.push(<Sec key="ch" title={`这一版改了 ${changes.length} 处`}>
    <ul className="space-y-1">{changes.map((c, i) => (
      <li key={i}>{c.where ? <span className="font-medium">{str(c.where)}：</span> : null}
        {c.before ? <><span className="text-muted-foreground line-through">{str(c.before)}</span> → </> : null}{str(c.after)}
        {c.why ? <div className="text-muted-foreground">为什么：{str(c.why)}</div> : null}</li>))}</ul>
  </Sec>);
  return out.length ? <>{out}</> : null;
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
