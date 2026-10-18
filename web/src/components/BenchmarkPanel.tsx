import {
  AlertCircle, ArrowRight, BookOpen, CheckCircle2, Copy, ExternalLink, Flame, Image as ImageIcon, Lightbulb,
  ListOrdered, MessageSquareQuote, RefreshCw, Search, Sparkles, Target, Trash2, Type, UserRound, Wand2,
} from "lucide-react";
import { useState } from "react";
import type { Account, Job, JobEvent, S } from "../api/client";
import { isActive, useClone, useFindCreators, useRemoveBenchmark } from "../api/hooks";
import { cn } from "../lib/utils";
import { Avatar, Badge, Button, Card, CardBody, CardHead, ErrorText, Input, Label, Spinner } from "./ui";

type Bench = S["BenchmarkOut"];
type Dict = Record<string, unknown>;
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v)).replace(/\*\*/g, "");
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

const FIELD_LABEL: Record<string, string> = {
  theme: "账号主题", audience: "目标受众", content_style: "文案风格", image_style: "配图风格", topic_type: "选题方向", keywords: "关键词",
};

export function BenchmarkPanel({ account, jobs, onGoTopics }: { account: Account; jobs: Job[]; onGoTopics: () => void }) {
  const b = account.benchmark ?? null;
  const job = jobs.find((j) => j.kind === "clone_creator" && isActive(j));
  const [replacing, setReplacing] = useState(false);

  if (job || b?.status === "analyzing") return <Analyzing job={job} bench={b} />;
  if (!b || replacing || b.status === "failed") {
    return <StartForm account={account} failed={b?.status === "failed" ? b : null} onCancel={replacing ? () => setReplacing(false) : undefined}
      onStarted={() => setReplacing(false)} />;
  }
  return <Playbook account={account} bench={b} onReplace={() => setReplacing(true)} onGoTopics={onGoTopics} />;
}

// ─── 发起复刻 ──────────────────────────────────────────────────────────────

function StartForm({ account, failed, onCancel, onStarted }: {
  account: Account; failed: Bench | null; onCancel?: () => void; onStarted: () => void;
}) {
  const clone = useClone(account.id);
  const find = useFindCreators();
  const [target, setTarget] = useState(failed?.target ?? "");
  const [theme, setTheme] = useState(failed?.theme || account.theme);
  const [q, setQ] = useState("");

  return (
    <div className="space-y-6">
      <Card className="border-indigo-200">
        <CardHead icon={<Copy />} title="复刻一个对标账号"
          desc="给一个在小红书上做起来的账号，照着 TA 的打法起号，只把内容换成你的主题"
          action={onCancel && <Button size="sm" variant="ghost" onClick={onCancel}>取消</Button>} />
        <CardBody className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              { icon: <BookOpen />, t: "读作品挑爆款", d: "最近 60 篇作品，按互动排出爆款，细看前 5 篇正文和热评" },
              { icon: <Wand2 />, t: "拆打法", d: "人设、内容栏目、标题公式、开头钩子、正文结构、封面风格、更新节奏" },
              { icon: <Sparkles />, t: "换成你的主题", d: "自动更新账号定位和写法规则，生成 8 个对应爆款的复刻选题" },
            ].map((s, i) => (
              <div key={s.t} className="rounded-xl bg-indigo-50/60 p-4">
                <div className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-indigo-700 [&_svg]:size-4">{s.icon}{i + 1}. {s.t}</div>
                <p className="text-xs leading-relaxed text-muted-foreground">{s.d}</p>
              </div>
            ))}
          </div>

          {failed && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>上次拆解「{failed.creator_name || failed.target}」没成功：{failed.error || "未知错误"}</div>
            </div>
          )}

          <div className="space-y-4">
            <div>
              <Label hint="主页链接、笔记链接、博主名字或小红书号都行">对标账号</Label>
              <Input value={target} placeholder="例如 https://www.xiaohongshu.com/user/profile/… 或 程十安an" onChange={(e) => setTarget(e.target.value)} />
            </div>
            <div>
              <Label hint="对方的打法会换到这个主题上">我想做的主题</Label>
              <Input value={theme} placeholder="例如：职场新人理财" onChange={(e) => setTheme(e.target.value)} />
            </div>
            <ErrorText error={clone.error} />
            <Button variant="gradient" size="lg" className="w-full" disabled={!target.trim() || !theme.trim()} loading={clone.isPending}
              onClick={() => clone.mutate({ target: target.trim(), theme: theme.trim(), platform: "xiaohongshu" }, { onSuccess: onStarted })}>
              {!clone.isPending && <Wand2 />}开始拆解（约 1-2 分钟）
            </Button>
            <p className="text-xs text-muted-foreground">需要先在「数据来源」里连上小红书。复刻的是方法，不会照抄对方的句子。</p>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHead icon={<Search />} title="不知道对标谁？" desc="输入领域关键词或博主名，按粉丝从高到低列出小红书博主" />
        <CardBody className="space-y-3">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) find.mutate(q.trim()); }}>
            <Input value={q} placeholder="例如：理财、穿搭、考研" onChange={(e) => setQ(e.target.value)} />
            <Button type="submit" variant="outline" loading={find.isPending}>{!find.isPending && <Search />}找博主</Button>
          </form>
          <ErrorText error={find.error} />
          {find.data && find.data.length === 0 && <p className="text-sm text-muted-foreground">没搜到，换个词试试</p>}
          <div className="space-y-2">
            {find.data?.map((c) => (
              <div key={c.url} className="flex items-center gap-3 rounded-xl border-2 bg-card p-3 transition-all hover:border-indigo-300">
                <Avatar name={c.name} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{c.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{c.fans && `${c.fans} 粉`}{c.posts && ` · ${c.posts} 篇`}{c.desc && ` · ${c.desc}`}</div>
                </div>
                <a href={c.url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="打开主页"><ExternalLink className="size-4" /></a>
                <Button size="xs" variant={target === c.url ? "gradient" : "outline"} onClick={() => setTarget(c.url)}>
                  {target === c.url ? "已选" : "选它"}
                </Button>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

// ─── 拆解中 ────────────────────────────────────────────────────────────────

const STEPS = [
  { stage: "find", label: "找到博主、读作品" },
  { stage: "detail", label: "细看爆款正文和热评" },
  { stage: "analyze", label: "拆解打法" },
  { stage: "adapt", label: "换成你的主题出方案" },
];

function Analyzing({ job, bench }: { job?: Job; bench: Bench | null }) {
  const events = (job?.events ?? []) as JobEvent[];
  const seen = new Set(events.map((e) => e.stage));
  const cur = Math.max(0, ...STEPS.map((s, i) => (seen.has(s.stage) ? i : 0)));
  const last = events[events.length - 1];
  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Wand2 />} title={`正在拆解${bench?.creator_name ? `「${bench.creator_name}」` : "对标账号"}`}
        desc="大约 1-2 分钟，可以先去别的页面，好了会自动更新" />
      <CardBody className="space-y-3">
        {STEPS.map((s, i) => {
          const done = i < cur;
          const active = i === cur;
          return (
            <div key={s.stage} className="flex items-center gap-3 text-sm">
              {done ? <CheckCircle2 className="size-5 text-green-500" /> : active ? <Spinner className="size-5" />
                : <div className="size-5 rounded-full border-2 border-muted" />}
              <span className={cn(!done && !active && "text-muted-foreground")}>{s.label}</span>
            </div>
          );
        })}
        {last && <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-muted-foreground">{last.message}</p>}
        {events.filter((e) => e.stage === "warning").map((e, i) => (
          <p key={i} className="text-xs text-amber-600">⚠ {e.message}</p>
        ))}
      </CardBody>
    </Card>
  );
}

// ─── 复刻方案 ──────────────────────────────────────────────────────────────

function Playbook({ account, bench: b, onReplace, onGoTopics }: {
  account: Account; bench: Bench; onReplace: () => void; onGoTopics: () => void;
}) {
  const clone = useClone(account.id);
  const remove = useRemoveBenchmark(account.id);
  const p = b.playbook as Dict;
  const info = b.creator_info as Dict;
  const applied = ((b.plan as Dict).applied ?? {}) as Dict;
  const myPillars = arr((b.plan as Dict).pillars) as Dict[];
  const steps = arr((b.plan as Dict).steps).map(str);
  const profile = (applied.profile ?? {}) as Dict;

  const stats = [
    info.fans && { k: "粉丝", v: str(info.fans) },
    info["获赞与收藏"] && { k: "获赞与收藏", v: str(info["获赞与收藏"]) },
    info.per_week && { k: "每周更新", v: `${str(info.per_week)} 篇` },
    info.median_likes && { k: "点赞中位数", v: Number(info.median_likes) >= 10000 ? `${(Number(info.median_likes) / 10000).toFixed(1)}万` : str(info.median_likes) },
    info.hit_rate != null && { k: "爆款率", v: `${Math.round(Number(info.hit_rate) * 100)}%` },
    info.video_share != null && { k: "视频占比", v: `${Math.round(Number(info.video_share) * 100)}%` },
  ].filter(Boolean) as { k: string; v: string }[];

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-start gap-4 p-6">
          <Avatar name={b.creator_name || "?"} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-lg font-semibold">{b.creator_name}</span>
              <Badge className="bg-rose-100 text-rose-600">小红书对标</Badge>
              {b.creator_url && <a href={b.creator_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ExternalLink className="size-3" />主页</a>}
            </div>
            {str(info.desc) && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{str(info.desc)}</p>}
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
              {stats.map((s) => (
                <div key={s.k}><div className="text-sm font-semibold">{s.v}</div><div className="text-xs text-muted-foreground">{s.k}</div></div>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" loading={clone.isPending} onClick={() => clone.mutate({ target: b.target, theme: b.theme || account.theme, platform: b.platform })}>
              {!clone.isPending && <RefreshCw />}重新拆解
            </Button>
            <Button size="sm" variant="outline" onClick={onReplace}><Copy />换一个</Button>
            <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-red-600" loading={remove.isPending}
              onClick={() => { if (confirm("不再对标这个账号？已经同步到账号的定位和规则会保留，没用过的复刻选题会收起。")) remove.mutate(b.id); }}>
              {!remove.isPending && <Trash2 />}
            </Button>
          </div>
        </div>
        {str(p.summary) && (
          <div className="mx-6 mb-6 rounded-xl bg-brand-gradient p-4 text-white">
            <div className="mb-1 flex items-center gap-1.5 text-xs opacity-80"><Flame className="size-3.5" />TA 靠什么火</div>
            <div className="font-medium leading-relaxed">{str(p.summary)}</div>
          </div>
        )}
        <ErrorText error={clone.error} />
      </Card>

      {/* 已同步到账号 */}
      <Card className="border-indigo-200">
        <CardHead icon={<CheckCircle2 />} title={`已按「${str(profile.theme) || b.theme || account.theme}」同步到你的账号`}
          desc="写稿、质检、找选题都会按这套打法来；不满意可以去「配置」里改，或跟小媒说"
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

      <Section icon={<Flame />} title={`TA 的爆款（${b.samples.length}）`}>
        <div className="divide-y">
          {(b.samples as Dict[]).map((x, i) => (
            <div key={i} className="flex items-center gap-3 py-2.5">
              <span className="w-5 text-center text-xs font-semibold text-muted-foreground">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm">{str(x.title)}</div>
                <div className="text-xs text-muted-foreground">{[str(x.kind), str(x.date), x.likes && `${str(x.likes)} 赞`, x.collects && `${str(x.collects)} 收藏`].filter(Boolean).join(" · ")}</div>
              </div>
              {str(x.url) && <a href={str(x.url)} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="看原帖"><ExternalLink className="size-4" /></a>}
            </div>
          ))}
        </div>
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
