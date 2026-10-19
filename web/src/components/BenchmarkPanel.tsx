import {
  AlertCircle, ArrowRight, CheckCircle2, Copy, ExternalLink, Flame, Image as ImageIcon, Layers, Lightbulb,
  KeyRound, ListOrdered, MessageSquareQuote, Plus, RefreshCw, Search, Sparkles, Target, Trash2, Type, UserRound, Wand2,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { Account, Benchmark, Candidate, Job, JobEvent } from "../api/client";
import { isActive, useClone, useCredentials, useFindCandidates, usePendingChat, useRemoveBenchmark } from "../api/hooks";
import { cn } from "../lib/utils";
import { MAX_BENCH } from "./CandidatePicker";
import { CandidateGallery, FindProgress, NoteGrid, uniqNotes } from "./CreatorGallery";
import { QrLogin } from "./QrLogin";
import { Avatar, Badge, Button, Card, CardBody, CardHead, ErrorText, Input, Label, Pills, Spinner, Textarea } from "./ui";

type Dict = Record<string, unknown>;
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v)).replace(/\*\*/g, "");
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const fmt = (v: unknown) => (Number(v) >= 10000 ? `${(Number(v) / 10000).toFixed(1)}万` : str(v));

const FIELD_LABEL: Record<string, string> = {
  theme: "账号主题", audience: "目标受众", content_style: "文案风格", image_style: "配图风格", topic_type: "选题方向", keywords: "关键词",
};

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
          desc={ready.length > 1 ? "几个账号的打法已经合成一套，每一块学谁的见下方" : "最多同时对标 3 个，多个会自动合成一套打法"}
          action={live.length < MAX_BENCH && !job && !adding && <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus />加对标账号</Button>} />
        <CardBody className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {benches.map((b) => <BenchCard key={b.id} account={account} bench={b} busy={!!job} />)}
        </CardBody>
      </Card>
      {job && <Analyzing job={job} />}
      {(live.length < MAX_BENCH || findJob) && finding}
      {adding && !findJob && <AddBenchmark account={account} onCancel={() => setAdding(false)} onStarted={() => setAdding(false)} />}
      {ready.length > 0 && Object.keys(plan).length > 0 && (
        <MergedPlan account={account} plan={plan} benches={ready} onGoTopics={onGoTopics} />
      )}
      {ready.length > 0 && <CreatorDetails benches={ready} />}
    </div>
  );
}

function XhsConnect() {
  return (
    <Card className="border-amber-200">
      <CardHead icon={<KeyRound />} title="先连上小红书" desc="找同领域的号、读对方作品都要用小红书登录态；建议用小号扫码，连上后会自动开始找" />
      <CardBody><QrLogin platform="xiaohongshu" /></CardBody>
    </Card>
  );
}

function FindError({ error }: { error: string }) {
  const login = /登录|扫码|Cookie/.test(error);
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
          { icon: <Search />, t: "找同领域的号", d: "按你的主题搜热门笔记和博主，给出粉丝、点赞中位数、爆款率和值得学的地方，你来挑" },
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
          <form className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); if (query.trim()) find.mutate({ query: query.trim(), prefer }, { onSuccess: () => onStarted?.() }); }}>
            <Input value={query} placeholder="方向，例如：通勤穿搭" onChange={(e) => setQuery(e.target.value)} />
            <Input value={prefer} placeholder="额外要求（可选），如：粉丝少一点、做图文的" onChange={(e) => setPrefer(e.target.value)} />
            <Button type="submit" variant="gradient" loading={find.isPending} disabled={!query.trim()}>{!find.isPending && <Search />}找候选</Button>
          </form>
          <ErrorText error={find.error} />
        </> : <>
          <div>
            <Label hint="每行一个：主页链接、笔记链接、博主名字或小红书号">对标账号</Label>
            <Textarea rows={3} value={links} placeholder={"https://www.xiaohongshu.com/user/profile/…\n程十安an"} onChange={(e) => setLinks(e.target.value)} />
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
  return (
    <div className={cn("group relative rounded-xl border-2 bg-card p-4", failed && "border-red-200 bg-red-50/40")}>
      <div className="flex items-center gap-3">
        {avatar ? <img src={avatar} alt="" referrerPolicy="no-referrer" className="size-10 rounded-full object-cover" /> : <Avatar name={b.creator_name || (b.target.startsWith("http") ? "红" : b.target) || "?"} size="sm" />}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate font-medium">{b.creator_name || (b.target.startsWith("http") ? "小红书账号" : b.target)}</span>
            {b.creator_url && <a href={b.creator_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="主页"><ExternalLink className="size-3" /></a>}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {b.status === "analyzing" ? <span className="text-indigo-600">正在拆解…</span>
              : failed ? <span className="text-red-600">没拆成</span>
              : [info.fans && `${str(info.fans)} 粉`, info.median_likes && `中位赞 ${fmt(info.median_likes)}`,
                info.hit_rate != null && `爆款率 ${Math.round(Number(info.hit_rate) * 100)}%`].filter(Boolean).join(" · ")}
          </div>
        </div>
      </div>
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
  { stage: "analyze", label: "拆解打法" },
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

// ─── 合成方案 ──────────────────────────────────────────────────────────────

function MergedPlan({ account, plan, benches, onGoTopics }: { account: Account; plan: Dict; benches: Benchmark[]; onGoTopics: () => void }) {
  const applied = (plan.applied ?? {}) as Dict;
  const profile = (applied.profile ?? {}) as Dict;
  const borrow = arr(plan.borrow) as Dict[];
  const pillars = arr(plan.pillars) as Dict[];
  const steps = arr(plan.steps).map(str);
  return (
    <div className="space-y-6">
      {str(plan.summary) && (
        <div className="rounded-xl bg-brand-gradient p-5 text-white">
          <div className="mb-1 flex items-center gap-1.5 text-xs opacity-80"><Flame className="size-3.5" />{benches.length > 1 ? `合成了 ${benches.length} 个账号的打法` : `学「${benches[0]?.creator_name}」的打法`}</div>
          <div className="font-medium leading-relaxed">{str(plan.summary)}</div>
        </div>
      )}
      {borrow.length > 0 && (
        <Section icon={<Layers />} title="每一块学谁">
          <div className="grid gap-2 sm:grid-cols-2">
            {borrow.map((x, i) => (
              <div key={i} className="rounded-lg border-2 px-3 py-2.5">
                <div className="mb-0.5 flex items-center gap-2">
                  <span className="font-medium">{str(x.aspect)}</span>
                  <Badge className="bg-fuchsia-50 text-fuchsia-700">学 {str(x.from)}</Badge>
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">{str(x.how)}</p>
              </div>
            ))}
          </div>
        </Section>
      )}
      <Card className="border-indigo-200">
        <CardHead icon={<CheckCircle2 />} title={`已按「${str(profile.theme) || str(plan.theme) || account.theme}」同步到你的账号`}
          desc="写稿、质检、找选题都会按这套打法来；不满意可以去「账号设定」里改，或跟小媒说"
          action={<Button size="sm" variant="gradient" onClick={onGoTopics}>去写复刻选题<ArrowRight /></Button>} />
        <CardBody className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2.5">
            <div className="text-xs font-medium text-muted-foreground">账号定位</div>
            {Object.entries(profile).map(([k, v]) => (
              <div key={k} className="text-sm"><span className="text-muted-foreground">{FIELD_LABEL[k] ?? k}：</span>{Array.isArray(v) ? v.join("、") : str(v)}</div>
            ))}
          </div>
          <div className="space-y-4">
            <div>
              <div className="mb-2 text-xs font-medium text-muted-foreground">写法规则（每篇都遵守）</div>
              <ol className="space-y-1.5 text-sm">
                {arr(applied.rules).map((r, i) => <li key={i} className="flex gap-2"><span className="text-indigo-500">{i + 1}.</span>{str(r)}</li>)}
              </ol>
            </div>
            <div className="text-sm"><span className="text-muted-foreground">复刻选题：</span>{arr(applied.topics).length} 个已放进选题库，写稿时会参考对应的原爆款结构</div>
          </div>
          {pillars.length > 0 && (
            <div className="md:col-span-2">
              <div className="mb-2 text-xs font-medium text-muted-foreground">你的内容栏目</div>
              <div className="grid gap-2 sm:grid-cols-3">
                {pillars.map((x, i) => (
                  <div key={i} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2"><span className="font-medium">{str(x.name)}</span>{str(x.share) && <span className="text-xs text-indigo-600">{str(x.share)}</span>}</div>
                    {str(x.from) && <div className="text-xs text-muted-foreground">学：{str(x.from)}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {steps.length > 0 && (
            <div className="md:col-span-2">
              <div className="mb-2 text-xs font-medium text-muted-foreground">起号建议</div>
              <ul className="grid gap-2 sm:grid-cols-2">
                {steps.map((s, i) => <li key={i} className="rounded-lg bg-indigo-50/60 px-3 py-2 text-sm">{s}</li>)}
              </ul>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

// ─── 各对标账号的拆解详情 ──────────────────────────────────────────────────

function CreatorDetails({ benches }: { benches: Benchmark[] }) {
  const [sel, setSel] = useState(benches[0]?.id ?? "");
  const b = benches.find((x) => x.id === sel) ?? benches[0];
  if (!b) return null;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-semibold">拆解详情</h3>
        {benches.length > 1 && <Pills value={b.id} onChange={setSel} items={benches.map((x) => ({ value: x.id, label: x.creator_name || x.target }))} />}
      </div>
      <CreatorDetail bench={b} />
    </div>
  );
}

function CreatorDetail({ bench: b }: { bench: Benchmark }) {
  const p = b.playbook as Dict;
  const hits = uniqNotes(b.samples as Dict[]).map((x) => ({
    title: str(x.title), url: str(x.url), cover: str(x.cover), kind: str(x.kind), date: str(x.date),
    likes: x.likes ? str(x.likes) : "",
  }));
  const myPillars: Dict[] = [];
  return (
    <div className="space-y-6">
      {str(p.summary) && (
        <div className="rounded-xl border-2 border-indigo-200 bg-indigo-50/50 p-4">
          <div className="mb-1 flex items-center gap-1.5 text-xs text-indigo-600"><Flame className="size-3.5" />「{b.creator_name}」靠什么火</div>
          <div className="text-sm font-medium leading-relaxed">{str(p.summary)}</div>
        </div>
      )}
      <div className="grid gap-6 md:grid-cols-2">
        <Section icon={<UserRound />} title="人设与受众">
          {str(p.persona) && <p><b className="font-medium">人设：</b>{str(p.persona)}</p>}
          {str(p.audience) && <p className="mt-2"><b className="font-medium">受众：</b>{str(p.audience)}</p>}
        </Section>
        <Section icon={<Target />} title="节奏与标签">
          {str(p.cadence) && <p><b className="font-medium">更新：</b>{str(p.cadence)}</p>}
          {str(p.tags) && <p className="mt-2"><b className="font-medium">标签：</b>{str(p.tags)}</p>}
        </Section>
      </div>

      <Section icon={<ListOrdered />} title="内容栏目">
        <div className="grid gap-3 sm:grid-cols-2">
          {(arr(p.pillars) as Dict[]).map((x, i) => {
            const mine = myPillars.find((m) => str(m.from) && str(x.name).includes(str(m.from)) || str(m.from).includes(str(x.name)));
            return (
              <div key={i} className="rounded-xl border-2 p-4">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-medium">{str(x.name)}</span>
                  {str(x.share) && <Badge className="bg-indigo-100 text-indigo-700">{str(x.share)}</Badge>}
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">{str(x.desc)}</p>
                {arr(x.examples).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">{arr(x.examples).slice(0, 3).map((e, j) => <span key={j} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{str(e)}</span>)}</div>
                )}
                {mine && <p className="mt-2 text-xs text-fuchsia-700">→ 你的栏目：{str(mine.name)}</p>}
              </div>
            );
          })}
        </div>
      </Section>

      <Section icon={<Type />} title="标题公式">
        <div className="space-y-2">
          {(arr(p.title_formulas) as Dict[]).map((f, i) => (
            <div key={i} className="flex flex-col gap-0.5 rounded-lg bg-slate-50 px-3 py-2 sm:flex-row sm:items-center sm:gap-3">
              <span className="font-medium text-indigo-700">{str(f.formula)}</span>
              {str(f.example) && <span className="text-xs text-muted-foreground">例：{str(f.example)}</span>}
            </div>
          ))}
        </div>
      </Section>

      <div className="grid gap-6 md:grid-cols-2">
        <Section icon={<MessageSquareQuote />} title="开头钩子">
          <ul className="space-y-1.5">{arr(p.hooks).map((h, i) => <li key={i}>· {str(h)}</li>)}</ul>
        </Section>
        <Section icon={<ListOrdered />} title="正文结构">
          <p className="whitespace-pre-wrap">{str(p.structure)}</p>
        </Section>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Section icon={<ImageIcon />} title="封面与配图"><p>{str(p.visual)}</p></Section>
        <Section icon={<Flame />} title="爆款规律">
          <p>{str(p.hit_pattern)}</p>
          {arr(p.audience_needs).length > 0 && <>
            <div className="mb-1 mt-3 text-xs font-medium text-muted-foreground">评论区在关心</div>
            <ul className="space-y-1">{arr(p.audience_needs).map((n, i) => <li key={i}>· {str(n)}</li>)}</ul>
          </>}
        </Section>
      </div>

      {arr(p.not_copyable).length > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-amber-500" />
          <div><div className="mb-1 font-medium">这些别照搬</div><ul className="space-y-0.5">{arr(p.not_copyable).map((n, i) => <li key={i}>· {str(n)}</li>)}</ul></div>
        </div>
      )}

      <Section icon={<Flame />} title={`TA 的爆款（${hits.length}）`}>
        <NoteGrid notes={hits} className="sm:grid-cols-4 lg:grid-cols-6" />
      </Section>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHead icon={icon} title={title} />
      <CardBody className="pt-4 text-sm leading-relaxed">{children}</CardBody>
    </Card>
  );
}
