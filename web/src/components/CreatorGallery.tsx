import { Check, CheckCircle2, ExternalLink, Heart, PlayCircle, RefreshCw, Search, SlidersHorizontal, Wand2 } from "lucide-react";
import { useState } from "react";
import { BENCH_PLATFORMS, platformLabel, type Account, type BenchPlatform, type Candidate, type Job, type JobEvent, type NoteCard } from "../api/client";
import { useClone, useCredentials, useFindCandidates } from "../api/hooks";
import { cn } from "../lib/utils";
import { hitText, isBenchmarked, MAX_BENCH } from "./CandidatePicker";
import { Avatar, Badge, Button, Card, CardBody, CardHead, ErrorText, Input, Pills, Spinner } from "./ui";

/** 在哪个平台找对标：小红书 / 抖音图文 / 微博；没连的平台提示先去连接 */
export function PlatformPick({ value, onChange }: { value: BenchPlatform; onChange: (v: BenchPlatform) => void }) {
  const { data: creds } = useCredentials();
  const cur = BENCH_PLATFORMS.find((p) => p.value === value)!;
  const ok = creds?.find((c) => c.key === cur.cred)?.configured ?? true;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-muted-foreground">在哪找</span>
      <Pills<BenchPlatform> value={value} onChange={onChange} items={BENCH_PLATFORMS.map((p) => ({ value: p.value, label: p.label }))} />
      {!ok && <span className="text-amber-600">{platformLabel(value)}还没连，先去首页「连接平台」里连上</span>}
      {ok && value !== "xiaohongshu" && <span className="text-muted-foreground">只找做图文的号，学到的打法会换成小红书的写法</span>}
    </div>
  );
}

const fmt = (n?: number) => (n == null ? "" : n >= 10000 ? `${(n / 10000).toFixed(1)}万` : String(n));

/** 按标题+日期去重（老数据里可能有平台重复返回的同一篇） */
export function uniqNotes<T extends { title?: unknown; date?: unknown; url?: unknown }>(xs: T[]): T[] {
  const seen = new Set<string>();
  return xs.filter((x) => {
    const k = `${String(x.title ?? "")}|${String(x.date ?? "")}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

const GRADIENTS = ["from-rose-100 to-orange-100", "from-indigo-100 to-purple-100", "from-emerald-100 to-sky-100", "from-amber-100 to-pink-100"];

/** 一篇笔记，长得像小红书首页的卡片：3:4 封面 + 两行标题 + 点赞 */
export function NoteTile({ n, i = 0, small }: { n: NoteCard; i?: number; small?: boolean }) {
  const [broken, setBroken] = useState(false);
  return (
    <a href={n.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
      className="group block min-w-0 overflow-hidden rounded-xl bg-card ring-1 ring-black/5 transition-shadow hover:shadow-md">
      <div className="relative aspect-[3/4] overflow-hidden bg-slate-100">
        {n.cover && !broken ? (
          <img src={n.cover} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)}
            className="size-full object-cover transition-transform duration-300 group-hover:scale-105" />
        ) : (
          <div className={cn("flex size-full items-center justify-center bg-gradient-to-br p-3 text-center font-semibold leading-relaxed text-slate-700", GRADIENTS[i % GRADIENTS.length], small ? "text-[10px]" : "text-sm")}>
            {n.title}
          </div>
        )}
        {n.kind === "视频" && <PlayCircle className="absolute right-1.5 top-1.5 size-4 text-white drop-shadow" />}
      </div>
      <div className={cn("space-y-1", small ? "p-1.5" : "p-2")}>
        {n.cover && !broken && <div className={cn("line-clamp-2 leading-snug", small ? "text-[11px]" : "text-xs font-medium")}>{n.title}</div>}
        {(n.likes || n.author) && (
          <div className="flex items-center justify-between gap-1 text-[11px] text-muted-foreground">
            {n.author && <span className="truncate">{n.author}</span>}
            {n.likes && <span className="flex shrink-0 items-center gap-0.5"><Heart className="size-3" />{n.likes}</span>}
          </div>
        )}
      </div>
    </a>
  );
}

export function NoteGrid({ notes, className }: { notes: NoteCard[]; className?: string }) {
  return (
    <div className={cn("grid grid-cols-3 gap-2 sm:grid-cols-6", className)}>
      {notes.map((n, i) => <NoteTile key={(n.url || n.title) + i} n={n} i={i} />)}
    </div>
  );
}

type Found = { theme?: string; prefer?: string; platform?: string; candidates?: Candidate[]; notes?: string[] };

/** 对标页里的候选：每个号一行，像小红书主页一样能看到 TA 最火的几篇，勾选 1-3 个开始学 */
export function CandidateGallery({ account, found, collapsed }: { account: Account; found: Found; collapsed?: boolean }) {
  const clone = useClone(account.id);
  const find = useFindCandidates(account.id);
  const [picked, setPicked] = useState<string[]>([]);
  const [tuning, setTuning] = useState(false);
  const [query, setQuery] = useState(found.theme || account.theme);
  const [prefer, setPrefer] = useState(found.prefer || "");
  const [platform, setPlatform] = useState<BenchPlatform>((found.platform as BenchPlatform) || "xiaohongshu");
  const [open, setOpen] = useState(!collapsed);
  const cands = found.candidates ?? [];
  const slots = MAX_BENCH - account.benchmarks.filter((b) => b.status !== "failed").length;
  const toggle = (url: string) =>
    setPicked((p) => (p.includes(url) ? p.filter((x) => x !== url) : p.length >= slots ? p : [...p, url]));
  const again = (q = query, p = prefer, pf: string = tuning ? platform : found.platform || "xiaohongshu") =>
    find.mutate({ query: q.trim() || account.theme, prefer: p, platform: pf });
  const where = platformLabel(found.platform);

  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Search />}
        title={<>按「{found.theme}」在{where}找到的同领域账号 <span className="font-normal text-muted-foreground">{cands.length}</span></>}
        desc={slots > 0 ? `看看各自最火的几篇，挑 ${slots > 1 ? `1-${slots}` : "1"} 个学；点封面看原帖${found.prefer ? `（要求：${found.prefer}）` : ""}` : `已经对标 ${MAX_BENCH} 个了，想换就先在上面删掉一个`}
        action={
          <div className="flex gap-1.5">
            {collapsed && <Button size="sm" variant="ghost" onClick={() => setOpen((o) => !o)}>{open ? "收起" : "展开看看"}</Button>}
            <Button size="sm" variant="outline" onClick={() => setTuning((t) => !t)}><SlidersHorizontal />改要求</Button>
            <Button size="sm" variant="outline" loading={find.isPending} onClick={() => again()}>{!find.isPending && <RefreshCw />}换一批</Button>
          </div>
        } />
      {tuning && (
        <div className="space-y-2 border-b bg-slate-50/60 px-5 py-3">
          <PlatformPick value={platform} onChange={setPlatform} />
          <form className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]"
            onSubmit={(e) => { e.preventDefault(); again(query, prefer, platform); setTuning(false); }}>
            <Input value={query} placeholder="方向，例如：通勤穿搭" onChange={(e) => setQuery(e.target.value)} />
            <Input value={prefer} placeholder="额外要求：粉丝少一点、最近还在更…" onChange={(e) => setPrefer(e.target.value)} />
            <Button type="submit" variant="gradient" disabled={!query.trim()}><Search />重新找</Button>
          </form>
        </div>
      )}
      {open && (
        <CardBody className="space-y-4">
          <ErrorText error={find.error} />
          {!cands.length && <p className="text-sm text-muted-foreground">这次没找到合适的同领域账号，点「改要求」换个说法，或者直接贴想对标的号。</p>}
          {cands.map((c) => {
            const done = isBenchmarked(account, c);
            const on = picked.includes(c.url);
            const full = !on && picked.length >= slots;
            const notes = uniqNotes(c.notes?.length ? c.notes : [...(c.hits ?? []), ...(c.top ?? [])]).slice(0, 6);
            return (
              <div key={c.url} onClick={() => !done && slots > 0 && toggle(c.url)}
                className={cn("rounded-2xl border-2 p-4 transition-all", done ? "border-emerald-200 bg-emerald-50/30" : "cursor-pointer",
                  !done && (on ? "border-indigo-400 bg-indigo-50/30 shadow-md ring-2 ring-indigo-100" : "hover:border-indigo-300"),
                  full && !done && "opacity-60")}>
                <div className="mb-3 flex items-start gap-3">
                  {c.avatar ? <img src={c.avatar} alt="" referrerPolicy="no-referrer" className="size-14 shrink-0 rounded-full object-cover ring-2 ring-white" />
                    : <Avatar name={c.name} />}
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-base font-semibold">{c.name}</span>
                      {c.level && <Badge className="bg-indigo-50 text-indigo-600">{c.level}</Badge>}
                      {c.platform && c.platform !== "xiaohongshu" && <Badge className="bg-slate-100 text-slate-600">{platformLabel(c.platform)}</Badge>}
                      <a href={c.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"><ExternalLink className="size-3" />主页</a>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {[c.fans && `${c.fans} 粉丝`, c.median_likes != null && `平时点赞 ${fmt(c.median_likes)}`,
                        c.hit_rate != null && hitText(c.hit_rate), c.per_week && `每周约 ${c.per_week} 篇`,
                        c.last_post && `最近更新 ${c.last_post}`].filter(Boolean).join(" · ")}
                    </div>
                    {c.desc && <div className="line-clamp-1 text-xs text-muted-foreground/80">{c.desc}</div>}
                    {(c.reason || c.learn) && (
                      <div className="flex flex-wrap items-center gap-1.5 pt-0.5 text-xs">
                        {c.reason && <span className="text-indigo-600">💡 {c.reason}</span>}
                        {c.learn && <span className="rounded bg-fuchsia-50 px-1.5 py-0.5 text-fuchsia-700">最该学：{c.learn}</span>}
                      </div>
                    )}
                  </div>
                  {done ? <Badge className="shrink-0 bg-emerald-50 text-emerald-600"><CheckCircle2 className="size-3" />在学了</Badge>
                    : slots > 0 && (
                      <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-lg border-2 transition-colors",
                        on ? "border-indigo-500 bg-indigo-500 text-white" : "border-gray-300 bg-white")}>{on && <Check className="size-4" />}</span>
                    )}
                </div>
                {notes.length > 0 && <NoteGrid notes={notes} />}
              </div>
            );
          })}
          {found.notes && found.notes.length > 0 && <p className="text-xs text-muted-foreground">{found.notes.join("；")}</p>}
          <ErrorText error={clone.error} />
          {slots > 0 && cands.length > 0 && (
            <div className="sticky bottom-3 z-10 flex items-center gap-3 rounded-xl border bg-card/95 px-4 py-3 shadow-lg backdrop-blur-sm">
              <span className="text-sm text-muted-foreground">{picked.length ? `已选 ${picked.length} 个` : "点卡片勾选"}，最多 {slots} 个；多个会合成一套打法</span>
              <Button variant="gradient" className="ml-auto" disabled={!picked.length} loading={clone.isPending}
                onClick={() => clone.mutate({ targets: picked, names: picked.map((u) => cands.find((c) => c.url === u)?.name ?? ""), theme: account.theme || found.theme }, { onSuccess: () => setPicked([]) })}>
                {!clone.isPending && <Wand2 />}学习选中的{picked.length ? ` ${picked.length} 个` : ""}
              </Button>
            </div>
          )}
        </CardBody>
      )}
    </Card>
  );
}

const FIND_STEPS = [
  { stage: "search", label: "搜这个方向最热的笔记，看都是谁写的" },
  { stage: "probe", label: "挨个看博主主页：粉丝、平时点赞、爆款多不多、更新勤不勤" },
  { stage: "pick", label: "判断是不是同领域、值不值得学、最该学什么" },
];

/** 找候选进行中：步骤 + 最新进度 + 封面骨架 */
export function FindProgress({ job }: { job: Job }) {
  const events = (job.events ?? []) as JobEvent[];
  const last = events[events.length - 1];
  const cur = last ? Math.max(0, FIND_STEPS.findIndex((s) => s.stage === last.stage)) : 0;
  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Search />} title={`正在${platformLabel(String((job.payload as Record<string, unknown>).platform ?? ""))}上找「${String((job.payload as Record<string, unknown>).query ?? "")}」的同领域账号`}
        desc="大约半分钟到一分钟，找到后直接在这里挑" />
      <CardBody className="space-y-4">
        <div className="space-y-2.5">
          {FIND_STEPS.map((s, i) => (
            <div key={s.stage} className="flex items-center gap-3 text-sm">
              {i < cur ? <CheckCircle2 className="size-5 text-green-500" /> : i === cur ? <Spinner className="size-5" /> : <div className="size-5 rounded-full border-2 border-muted" />}
              <span className={cn(i > cur && "text-muted-foreground")}>{s.label}</span>
            </div>
          ))}
        </div>
        {last && <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-muted-foreground">{last.message}</p>}
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {Array.from({ length: 6 }, (_, i) => <div key={i} className="aspect-[3/4] animate-pulse rounded-xl bg-slate-100" style={{ animationDelay: `${i * 120}ms` }} />)}
        </div>
      </CardBody>
    </Card>
  );
}
