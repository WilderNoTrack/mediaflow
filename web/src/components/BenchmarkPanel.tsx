import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle, ArrowRight, CheckCircle2, Copy, Download, ExternalLink, FileText, Flame, KeyRound, Layers, Lightbulb,
  Plus, RefreshCw, Search, Sparkles, Trash2, Wand2, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { platformLabel, type Account, type Benchmark, type BenchPlatform, type Candidate, type Job, type JobEvent } from "../api/client";
import { isActive, useClone, useCredentials, useFindCandidates, useIsAdmin, usePendingChat, useRemoveBenchmark } from "../api/hooks";
import { cn } from "../lib/utils";
import { hitText, MAX_BENCH } from "./CandidatePicker";
import { CandidateGallery, FindProgress, NoteGrid, PlatformPick, uniqNotes } from "./CreatorGallery";
import { QrLogin } from "./QrLogin";
import { Markdown } from "./Markdown";
import { Avatar, Badge, Button, Card, CardBody, CardHead, ErrorText, Input, Label, Modal, Pills, Spinner, Textarea } from "./ui";

type Dict = Record<string, unknown>;
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v)).replace(/\*\*/g, "");
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const fmt = (v: unknown) => (Number(v) >= 10000 ? `${(Number(v) / 10000).toFixed(1)}万` : str(v));


export function BenchmarkPanel({ account, jobs, onGoTopics, onOpenChat }: {
  account: Account; jobs: Job[]; onGoTopics: () => void; onOpenChat?: () => void;
}) {
  const benches = account.benchmarks;
  const plan = account.bench_plan as Dict;
  const found = account.bench_candidates as { theme?: string; candidates?: Candidate[] };
  const job = jobs.find((j) => j.kind === "clone_creator" && isActive(j));
  const findJob = jobs.find((j) => j.kind === "find_benchmarks" && isActive(j));
  const lastFind = jobs.find((j) => j.kind === "find_benchmarks");
  const findError = lastFind && lastFind.status === "failed" ? lastFind.error : "";
  const chatting = usePendingChat(account.id).some((t) => /对标|找.*号/.test(t));
  const { data: creds } = useCredentials();
  const xhsOk = creds?.find((c) => c.key === "xhs_cookie")?.configured ?? true;
  const find = useFindCandidates(account.id);
  const [adding, setAdding] = useState(false);
  const live = benches.filter((b) => b.status !== "failed");
  const ready = benches.filter((b) => b.status === "ready");
  const hasFound = !!found.theme;

  // 新建账号选了「对标起号」但还没连小红书：连上之后自动开始找
  const autoKey = `bench-autostart-${account.id}`;
  useEffect(() => {
    if (xhsOk && sessionStorage.getItem(autoKey) && !findJob && !find.isPending) {
      sessionStorage.removeItem(autoKey);
      if (account.theme) find.mutate({ query: account.theme, prefer: "" });
    }
  }, [xhsOk, autoKey, findJob, find, account.theme]);

  const finding = (
    <>
      {!xhsOk && <XhsConnect />}
      {findError && !findJob && <FindError error={findError} />}
      {chatting && <ChatHint onOpenChat={onOpenChat} />}
      {findJob ? <FindProgress job={findJob} />
        : hasFound ? <CandidateGallery account={account} found={found} collapsed={live.length > 0} />
        : null}
    </>
  );

  if (!benches.length && !job) {
    return (
      <div className="space-y-6">
        {!hasFound && !findJob && <Intro />}
        {finding}
        {!findJob && <AddBenchmark account={account} compact={hasFound} />}
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <Card>
        <CardHead icon={<Layers />} title={<>对标账号 <span className="font-normal text-muted-foreground">{live.length}/{MAX_BENCH}</span></>}
          desc={ready.length > 1 ? "几个账号的打法已经合成一套，每一块学谁写在完整报告里" : "最多同时对标 3 个，多个会自动合成一套打法"}
          action={live.length < MAX_BENCH && !job && !adding && <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus />加对标账号</Button>} />
        <CardBody className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {benches.map((b) => <BenchCard key={b.id} account={account} bench={b} busy={!!job} />)}
        </CardBody>
      </Card>
      {job && <Analyzing job={job} />}
      {(live.length < MAX_BENCH || findJob) && finding}
      {adding && !findJob && <AddBenchmark account={account} onCancel={() => setAdding(false)} onStarted={() => setAdding(false)} />}
      {ready.length > 0 && Object.keys(plan).length > 0 && (
        <PlanBrief account={account} plan={plan} benches={ready} onGoTopics={onGoTopics} />
      )}
      {ready.length > 0 && <Hits benches={ready} />}
    </div>
  );
}

function XhsConnect() {
  const admin = useIsAdmin();
  if (!admin)
    return (
      <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <AlertCircle className="mt-0.5 size-4 shrink-0" />管理员还没连上小红书，暂时找不了同领域的号。可以先去「选题」「写稿」，或者联系管理员扫码连接。
      </div>
    );
  return (
    <Card className="border-amber-200">
      <CardHead icon={<KeyRound />} title="先连上小红书" desc="找同领域的号、读对方作品都要用小红书登录态；建议用小号扫码，连上后会自动开始找" />
      <CardBody><QrLogin platform="xiaohongshu" /></CardBody>
    </Card>
  );
}

function FindError({ error }: { error: string }) {
  const admin = useIsAdmin();
  const login = /登录|扫码|Cookie/.test(error) && admin;
  return (
    <div className="space-y-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      <p className="flex items-start gap-2"><AlertCircle className="mt-0.5 size-4 shrink-0" />上次没找成：{error}</p>
      {login && <QrLogin platform="xiaohongshu" again />}
    </div>
  );
}

function ChatHint({ onOpenChat }: { onOpenChat?: () => void }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-sm text-indigo-700">
      <Spinner className="size-4" />
      <span className="flex-1">小媒正在小红书上按你说的找同领域的号，找到后会出现在这里，对话里也能直接勾选</span>
      {onOpenChat && <button className="cursor-pointer font-medium hover:underline lg:hidden" onClick={onOpenChat}>去看看</button>}
    </div>
  );
}

function Intro() {
  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Copy />} title="对标起号" desc="找 1-3 个同领域做起来的小红书账号，学 TA 们的打法，内容换成你的主题" />
      <CardBody className="grid gap-3 sm:grid-cols-3">
        {[
          { icon: <Search />, t: "找同领域的号", d: "按你的主题搜热门笔记和博主，给出粉丝、平时点赞、爆款多不多和值得学的地方，你来挑" },
          { icon: <Wand2 />, t: "逐个拆打法", d: "每个账号读 60 篇作品、细看 5 篇爆款：人设、栏目、标题公式、开头、结构、封面、节奏" },
          { icon: <Sparkles />, t: "合成一套给你用", d: "每一块挑最值得学的那个，自动更新账号定位和写法规则，生成对应爆款的复刻选题" },
        ].map((s, i) => (
          <div key={s.t} className="rounded-xl bg-indigo-50/60 p-4">
            <div className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-indigo-700 [&_svg]:size-4">{s.icon}{i + 1}. {s.t}</div>
            <p className="text-xs leading-relaxed text-muted-foreground">{s.d}</p>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

// ─── 加对标：帮我找 / 我有链接 ─────────────────────────────────────────────

function AddBenchmark({ account, onCancel, onStarted, compact }: { account: Account; onCancel?: () => void; onStarted?: () => void; compact?: boolean }) {
  const [mode, setMode] = useState<"find" | "link">(compact ? "link" : "find");
  const find = useFindCandidates(account.id);
  const clone = useClone(account.id);
  const [query, setQuery] = useState(account.theme);
  const [prefer, setPrefer] = useState("");
  const [platform, setPlatform] = useState<BenchPlatform>("xiaohongshu");
  const [links, setLinks] = useState("");
  const [theme, setTheme] = useState(account.theme);
  const slots = MAX_BENCH - account.benchmarks.filter((b) => b.status !== "failed").length;
  const targets = links.split(/\n+/).map((x) => x.trim()).filter(Boolean);

  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Plus />} title={compact ? "没有想要的？" : "加对标账号"} desc={compact ? "换个方向再找，或者直接贴你想对标的号" : `还能加 ${slots} 个；默认找同领域的，学得最像`}
        action={onCancel && <Button size="sm" variant="ghost" onClick={onCancel}>取消</Button>} />
      <CardBody className="space-y-4">
        <Pills<"find" | "link"> value={mode} onChange={setMode} items={[
          { value: "find", label: "帮我找同领域的号" }, { value: "link", label: "我有想对标的号" },
        ]} />
        {mode === "find" ? <>
          <PlatformPick value={platform} onChange={setPlatform} />
          <form className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); if (query.trim()) find.mutate({ query: query.trim(), prefer, platform }, { onSuccess: () => onStarted?.() }); }}>
            <Input value={query} placeholder="方向，例如：通勤穿搭" onChange={(e) => setQuery(e.target.value)} />
            <Input value={prefer} placeholder="额外要求（可选），如：粉丝少一点、最近还在更" onChange={(e) => setPrefer(e.target.value)} />
            <Button type="submit" variant="gradient" loading={find.isPending} disabled={!query.trim()}>{!find.isPending && <Search />}找候选</Button>
          </form>
          <ErrorText error={find.error} />
        </> : <>
          <div>
            <Label hint="每行一个：主页链接或作品链接（小红书、抖音、微博都行）、博主名字或小红书号">对标账号</Label>
            <Textarea rows={3} value={links} placeholder={"https://www.xiaohongshu.com/user/profile/…\nhttps://www.douyin.com/user/…\n程十安an"} onChange={(e) => setLinks(e.target.value)} />
          </div>
          {!account.theme && (
            <div>
              <Label hint="对方的打法会换到这个主题上">我想做的主题</Label>
              <Input value={theme} placeholder="例如：职场新人理财" onChange={(e) => setTheme(e.target.value)} />
            </div>
          )}
          <ErrorText error={clone.error} />
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">{targets.length > slots ? `最多再加 ${slots} 个` : "可以跨领域，但同领域学得最像"}</span>
            <Button variant="gradient" className="ml-auto" disabled={!targets.length || targets.length > slots || !theme.trim()} loading={clone.isPending}
              onClick={() => clone.mutate({ targets, theme: theme.trim() }, { onSuccess: () => { setLinks(""); onStarted?.(); } })}>
              {!clone.isPending && <Wand2 />}开始学习{targets.length ? ` ${targets.length} 个` : ""}
            </Button>
          </div>
        </>}
        <p className="text-xs text-muted-foreground">学的是方法，不会照抄对方的句子。</p>
      </CardBody>
    </Card>
  );
}

// ─── 对标账号卡片 ──────────────────────────────────────────────────────────

function BenchCard({ account, bench: b, busy }: { account: Account; bench: Benchmark; busy: boolean }) {
  const clone = useClone(account.id);
  const remove = useRemoveBenchmark(account.id);
  const info = b.creator_info as Dict;
  const avatar = str(info.avatar);
  const failed = b.status === "failed";
  const crossed = (arr((account.bench_plan as Dict).fit) as Fit[]).some((f) => f.benchmark_id === b.id);
  return (
    <div className={cn("group relative rounded-xl border-2 bg-card p-4", failed && "border-red-200 bg-red-50/40")}>
      <div className="flex items-center gap-3">
        {avatar ? <img src={avatar} alt="" referrerPolicy="no-referrer" className="size-10 rounded-full object-cover" /> : <Avatar name={b.creator_name || (b.target.startsWith("http") ? platformLabel(b.platform).slice(0, 1) : b.target) || "?"} size="sm" />}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate font-medium">{b.creator_name || (b.target.startsWith("http") ? `${platformLabel(b.platform)}账号` : b.target)}</span>
            {b.platform && b.platform !== "xiaohongshu" && <Badge className="shrink-0 bg-slate-100 text-slate-600">{platformLabel(b.platform)}</Badge>}
            {b.creator_url && <a href={b.creator_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="主页"><ExternalLink className="size-3" /></a>}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {b.status === "analyzing" ? <span className="text-indigo-600">正在学习…</span>
              : failed ? <span className="text-red-600">没拆成</span>
              : [info.fans && `${str(info.fans)} 粉`, info.median_likes && `平时点赞 ${fmt(info.median_likes)}`,
                info.hit_rate != null && hitText(Number(info.hit_rate))].filter(Boolean).join(" · ")}
          </div>
        </div>
      </div>
      {str((b.playbook as Dict).domain) && (
        <div className="mt-2"><Badge className={crossed ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}>做{str((b.playbook as Dict).domain)}{crossed && " · 和你不是一个领域"}</Badge></div>
      )}
      {failed && <p className="mt-2 flex items-start gap-1 text-xs text-red-600"><AlertCircle className="mt-0.5 size-3 shrink-0" />{b.error || "未知错误"}</p>}
      <div className="mt-3 flex gap-1.5 border-t pt-2">
        {failed && (
          <Button size="xs" variant="outline" loading={clone.isPending} disabled={busy}
            onClick={() => clone.mutate({ targets: [b.target], theme: b.theme || account.theme })}>{!clone.isPending && <RefreshCw />}重试</Button>
        )}
        <Button size="xs" variant="ghost" className="ml-auto text-muted-foreground hover:text-red-600" loading={remove.isPending} disabled={busy}
          onClick={() => { if (failed || confirm(`不再对标「${b.creator_name || b.target}」？它的复刻选题会收起，剩下的对标会重新合成方案。`)) remove.mutate(b.id); }}>
          {!remove.isPending && <Trash2 />}不对标了
        </Button>
      </div>
      <ErrorText error={clone.error ?? remove.error} />
    </div>
  );
}

// ─── 拆解中 ────────────────────────────────────────────────────────────────

const STEPS = [
  { stage: "find", label: "找到博主、读作品" },
  { stage: "detail", label: "细看爆款正文和热评" },
  { stage: "analyze", label: "总结打法" },
  { stage: "adapt", label: "合成一套、换成你的主题" },
];

function Analyzing({ job }: { job: Job }) {
  const events = (job.events ?? []) as JobEvent[];
  const last = events[events.length - 1];
  const cur = last ? Math.max(0, STEPS.findIndex((s) => s.stage === last.stage)) : 0;
  const synthOnly = !arr((job.payload as Dict).benchmark_ids).length;
  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Wand2 />} title={synthOnly ? "正在重新合成方案" : "正在学习对标账号"}
        desc="每个账号大约 1 分钟，可以先去别的页面，好了会自动更新" />
      <CardBody className="space-y-3">
        {(synthOnly ? STEPS.slice(3) : STEPS).map((s) => {
          const i = STEPS.indexOf(s);
          const done = i < cur;
          const active = i === cur || (synthOnly && i === 3);
          return (
            <div key={s.stage} className="flex items-center gap-3 text-sm">
              {done ? <CheckCircle2 className="size-5 text-green-500" /> : active ? <Spinner className="size-5" />
                : <div className="size-5 rounded-full border-2 border-muted" />}
              <span className={cn(!done && !active && "text-muted-foreground")}>{s.label}</span>
            </div>
          );
        })}
        {last && <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-muted-foreground">{last.message}</p>}
        {events.filter((e) => e.stage === "warning").map((e, i) => <p key={i} className="text-xs text-amber-600">⚠ {e.message}</p>)}
      </CardBody>
    </Card>
  );
}

// ─── 学完了：三行摘要 + 完整报告 ──────────────────────────────────────────

type Fit = { benchmark_id: string; creator: string; domain?: string; note?: string };

function PlanBrief({ account, plan, benches, onGoTopics }: { account: Account; plan: Dict; benches: Benchmark[]; onGoTopics: () => void }) {
  const [open, setOpen] = useState(false);
  const applied = (plan.applied ?? {}) as Dict;
  const nProfile = Object.keys((applied.profile ?? {}) as Dict).length;
  const nRules = arr(applied.rules).length;
  const nTopics = arr(applied.topics).length;
  const first = str(arr(plan.steps)[0]);
  const fit = arr(plan.fit) as Fit[];
  const theme = str(plan.theme) || account.theme;
  const changed = [nProfile && `账号定位 ${nProfile} 项`, nRules && `${nRules} 条写法规则`, nTopics && `${nTopics} 个复刻选题`].filter(Boolean).join("、");
  const rows = [
    { icon: <Lightbulb />, t: "学到了什么", d: str(plan.summary) },
    { icon: <CheckCircle2 />, t: "已经帮你改好", d: changed ? `${changed}，以后写稿都会照着来` : "" },
    { icon: <ArrowRight />, t: "先做这一步", d: first },
  ].filter((r) => r.d);
  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Flame />} title={benches.length > 1 ? `学完了 ${benches.length} 个账号，合成了一套打法` : `学完了「${benches[0]?.creator_name}」`}
        desc={`已按「${theme}」换好；详细分析都在报告里，想看再看`}
        action={<Button size="sm" variant="gradient" onClick={onGoTopics}>去写复刻选题<ArrowRight /></Button>} />
      <CardBody className="space-y-3">
        {rows.map((r) => (
          <div key={r.t} className="flex gap-3 text-sm">
            <span className="mt-0.5 text-indigo-500 [&_svg]:size-4">{r.icon}</span>
            <div className="min-w-0"><span className="font-medium">{r.t}：</span><span className="text-slate-700">{r.d}</span></div>
          </div>
        ))}
        {fit.map((f) => (
          <div key={f.benchmark_id} className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-amber-500" />
            <span>「{f.creator}」{f.domain ? `主要做${f.domain}，` : ""}和「{theme}」不是一个领域。{(f.note || "能学标题、结构和封面，选题要换成你领域里的事").replace(/[。；;，,\s]+$/, "")}。想学得更像，可以再找个同领域的号。</span>
          </div>
        ))}
        <div className="flex flex-wrap gap-2 border-t pt-3">
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}><FileText />查看完整报告</Button>
          <a href={reportUrl(account.id, true)} download className="inline-flex"><Button size="sm" variant="ghost"><Download />下载 .md</Button></a>
        </div>
      </CardBody>
      {open && <ReportDialog account={account} onClose={() => setOpen(false)} />}
    </Card>
  );
}

const reportUrl = (id: string, download = false) => `/api/accounts/${id}/benchmark/report${download ? "?download=true" : ""}`;

export function ReportDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["bench-report", account.id, (account.bench_plan as Dict).updated_at],
    queryFn: async () => {
      const r = await fetch(reportUrl(account.id));
      if (!r.ok) throw new Error(`报告没打开（${r.status}）`);
      return r.text();
    },
  });
  return (
    <Modal className="max-w-3xl" onClose={onClose}>
      <div className="flex items-center justify-between gap-3 border-b px-5 py-3">
        <div className="flex items-center gap-2 font-semibold"><FileText className="size-4 text-indigo-500" />对标报告</div>
        <div className="flex items-center gap-1">
          <a href={reportUrl(account.id, true)} download><Button size="sm" variant="ghost"><Download />下载 .md</Button></a>
          <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="关闭"><X className="size-4" /></button>
        </div>
      </div>
      <div className="max-h-[75vh] overflow-y-auto px-6 py-5">
        {isLoading ? <Spinner /> : error ? <ErrorText error={error} /> : <Markdown text={data ?? ""} />}
      </div>
    </Modal>
  );
}

/** 几个对标各自的爆款轮流排（A1 B1 C1 A2…），不会被赞最多的那个号占满 */
function interleave<T>(groups: T[][]): T[] {
  const out: T[] = [];
  for (let i = 0; i < Math.max(0, ...groups.map((g) => g.length)); i++) groups.forEach((g) => { if (i < g.length) out.push(g[i]); });
  return out;
}

function Hits({ benches }: { benches: Benchmark[] }) {
  const many = benches.length > 1;
  const hits = uniqNotes(interleave(benches.map((b) => (b.samples as Dict[]).map((x): Dict => ({ ...x, by: b.creator_name })))))
    .slice(0, 12).map((x) => ({
      title: str(x.title), url: str(x.url), cover: str(x.cover), kind: str(x.kind), date: str(x.date),
      likes: x.likes ? str(x.likes) : "", author: many ? str(x.by) : "",
    }));
  if (!hits.length) return null;
  return (
    <Card>
      <CardHead icon={<Flame />} title={benches.length > 1 ? "TA 们的爆款" : "TA 的爆款"} desc={many ? "每个对标轮流取几篇，复刻选题就是照着这些来的，点开能看原帖" : "复刻选题就是照着这些来的，点开能看原帖"} />
      <CardBody className="pt-4"><NoteGrid notes={hits} className="sm:grid-cols-4 lg:grid-cols-6" /></CardBody>
    </Card>
  );
}
