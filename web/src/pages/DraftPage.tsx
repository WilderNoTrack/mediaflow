import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronLeft, Copy, Download, Heart, Image as ImageIcon,
  MessageCircle, RefreshCw, Save, Sparkles, Star, Tag, ThumbsDown, ThumbsUp, Trash2, Wand2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { DraftDetail, JobEvent, S } from "../api/client";
import { api, unwrap } from "../api/client";
import { isActive, useAccount, useActiveJobs, useDraft, useDraftActions, useRevise, useRules, useSystem } from "../api/hooks";
import { ImageSettingsDialog } from "../components/ImageSettingsDialog";
import { Badge, Button, Card, CardBody, CardHead, Empty, ErrorText, Segmented, Spinner, Textarea } from "../components/ui";
import { cn, timeAgo } from "../lib/utils";

export function DraftPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: d, isLoading } = useDraft(id);
  const act = useDraftActions(id);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [copied, setCopied] = useState(false);
  const [imgIdx, setImgIdx] = useState(0);

  useEffect(() => {
    if (!d) return;
    setTitle(d.title);
    setBody(d.body);
    setTags(d.tags.join(" "));
  }, [d?.id, d?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const tagList = tags.split(/[,，\s#]+/).map((t) => t.trim()).filter(Boolean);
  const dirty = !!d && (title !== d.title || body !== d.body || tagList.join(",") !== d.tags.join(","));
  const save = () => act.update.mutate({ title, body, tags: tagList });

  // Ctrl/Cmd+S 保存；有未保存修改时离开页面提醒
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); if (dirty) save(); } };
    const onLeave = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", onLeave);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("beforeunload", onLeave); };
  });

  if (isLoading) return <div className="flex justify-center py-20"><Spinner className="size-6" /></div>;
  if (!d) return <div className="p-10"><Empty title="草稿不存在" action={<Link to="/"><Button size="sm">回到首页</Button></Link>} /></div>;

  const copy = async () => {
    const { text } = (await unwrap(api.GET("/api/drafts/{draft_id}/text", { params: { path: { draft_id: id } } }))) as { text: string };
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const exportZip = () => {
    window.location.href = `/api/drafts/${id}/export`;
    setTimeout(() => { qc.invalidateQueries({ queryKey: ["draft", id] }); qc.invalidateQueries({ queryKey: ["drafts"] }); }, 1500);
  };
  const back = `/accounts/${d.account_id}?tab=contents`;
  const titleLen = [...title].length;
  const status = d.status === "exported" ? "approved" : d.status;

  return (
    <div className="min-h-full bg-slate-50">
      <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur-sm">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5 sm:px-5">
          <Link to={back} className="flex items-center gap-1 rounded-lg px-1.5 py-1 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"><ArrowLeft className="size-4" />草稿</Link>
          <div className="hidden text-xs text-muted-foreground sm:block">
            {d.score != null && `质检 ${d.score.toFixed(1)} · `}{d.attempts > 1 ? `自动改了 ${d.attempts - 1} 轮 · ` : ""}{timeAgo(d.created_at)}
            {d.status === "exported" && <Badge className="ml-2 bg-blue-50 text-blue-600">已导出过</Badge>}
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Segmented<"pending_review" | "approved" | "rejected">
              value={status as "pending_review" | "approved" | "rejected"}
              onChange={(v) => act.update.mutate({ status: v })}
              items={[
                { value: "pending_review", label: "待审核" },
                { value: "approved", label: "可以发", icon: <CheckCircle2 /> },
                { value: "rejected", label: "不要了" },
              ]}
            />
            <span className="mx-1 hidden h-5 w-px bg-border sm:block" />
            <Button variant={dirty ? "default" : "ghost"} size="sm" disabled={!dirty} loading={act.update.isPending} onClick={save} title="Ctrl+S">
              <Save />{dirty ? "保存" : "已保存"}
            </Button>
            <Button variant="outline" size="sm" onClick={copy}>{copied ? <Check /> : <Copy />}{copied ? "已复制" : "复制文案"}</Button>
            <Button variant="gradient" size="sm" onClick={exportZip}><Download />导出图文包</Button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[1fr_360px]">
        <div className="min-w-0 space-y-5">
          {d.needs_attention && (
            <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <AlertTriangle className="size-4 shrink-0" />
              <span className="flex-1">AI 自动改了几轮还没完全达标，留下的是最好的一版。发之前看看质检意见，或者让 AI 再改一轮。</span>
              <a href="#qc" className="shrink-0 font-medium hover:underline">看质检 ↓</a>
            </div>
          )}
          <Card>
            <div className="flex items-center gap-3 border-b px-5 py-3">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="标题"
                className="min-w-0 flex-1 bg-transparent text-lg font-semibold outline-none placeholder:text-muted-foreground"
              />
              <span className={cn("shrink-0 text-xs", titleLen > 20 ? "font-medium text-red-500" : "text-muted-foreground")} title="小红书标题最多 20 字">{titleLen}/20</span>
            </div>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="正文"
              rows={18}
              className="block w-full resize-y bg-transparent px-5 py-4 text-[15px] leading-7 outline-none"
            />
            <div className="flex items-center gap-2 border-t px-5 py-3">
              <Tag className="size-4 shrink-0 text-muted-foreground" />
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="标签，用空格隔开"
                className="min-w-0 flex-1 bg-transparent text-sm text-indigo-700 outline-none placeholder:text-muted-foreground"
              />
              <span className="shrink-0 text-xs text-muted-foreground">{body.replace(/\s/g, "").length} 字 · {tagList.length} 个标签</span>
            </div>
          </Card>
          <ErrorText error={act.update.error} />
          <Evaluation d={d} dirty={dirty} />
          <FeedbackCard d={d} />
          <div className="pb-4 text-right">
            <button className="cursor-pointer text-xs text-muted-foreground hover:text-red-600" onClick={() => { if (confirm("删除这篇草稿？删了找不回来。")) act.remove.mutate(undefined, { onSuccess: () => nav(back) }); }}>
              <Trash2 className="mr-1 inline size-3" />删除这篇
            </button>
          </div>
        </div>
        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <PhonePreview d={d} title={title} body={body} tags={tagList} idx={imgIdx} onIdx={setImgIdx} />
          <ImagesCard d={d} i={imgIdx} setI={setImgIdx} />
        </div>
      </div>
    </div>
  );
}

function ImagesCard({ d, i, setI }: { d: DraftDetail; i: number; setI: (i: number) => void }) {
  const act = useDraftActions(d.id);
  const cur = d.images[i];
  const done = d.images.filter((x) => x.status === "done").length;
  const skipped = d.images.length > 0 && d.images.every((x) => x.status === "skipped");
  const { data: sys } = useSystem();
  const [setup, setSetup] = useState(false);
  return (
    <Card>
      <CardHead icon={<ImageIcon />} title="配图" action={<span className="text-xs text-muted-foreground">{done}/{d.images.length} 张</span>} />
      <CardBody className="space-y-3">
        {setup && <ImageSettingsDialog onClose={() => setSetup(false)} />}
        {skipped && (sys?.image_configured
          ? <div className="flex items-center gap-2 rounded-lg bg-indigo-50 px-3 py-2 text-xs text-indigo-700">
              <span className="flex-1">AI 配图已经配好了，这篇写的时候还没配，点一下就出图。</span>
              <Button size="xs" loading={act.images.isPending} onClick={() => act.images.mutate(undefined)}>现在出图</Button>
            </div>
          : <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
              <span className="flex-1">还没配置 AI 配图，所以没出图。填一个生图 Key 就能自动出图，也可以先导出文案。</span>
              <Button size="xs" variant="outline" onClick={() => setSetup(true)}>去配置</Button>
            </div>)}
        {d.images.length > 1 && (
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {d.images.map((im, k) => (
              <button key={im.id} onClick={() => setI(k)} className={cn("relative flex h-[60px] w-[45px] shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-md border-2 bg-muted", k === i ? "border-indigo-500" : "border-transparent")}>
                {im.url ? <img src={im.url} alt="" className="size-full object-cover" />
                  : im.status === "pending" || im.status === "running" ? <Spinner className="size-3" />
                  : <span className="text-[10px] text-muted-foreground">{k + 1}</span>}
              </button>
            ))}
          </div>
        )}
        {cur ? (
          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
              <span>第 {cur.idx + 1} 张{cur.idx === 0 && "（封面）"}的画面描述</span>
              {cur.status === "failed" && <span className="text-red-500">生成失败</span>}
            </div>
            <div className="flex items-start gap-2">
              <p className="flex-1 rounded-md bg-input-background px-3 py-2 text-xs leading-relaxed">{cur.prompt}</p>
              <Button variant="outline" size="sm" className="px-2" title="重新生成这张" loading={act.images.isPending} onClick={() => act.images.mutate(cur.idx)}>
                {!act.images.isPending && <RefreshCw className="text-indigo-500" />}
              </Button>
            </div>
          </div>
        ) : <p className="text-xs text-muted-foreground">这篇没有配图描述</p>}
        <Button variant="outline" size="sm" className="w-full" loading={act.images.isPending} onClick={() => act.images.mutate(undefined)}><RefreshCw />全部重新生成</Button>
        <ErrorText error={act.images.error} />
      </CardBody>
    </Card>
  );
}

const DIM: Record<string, string> = { hook: "吸引力", value: "价值感", voice: "人设口吻", fit: "贴合定位", rules: "守规矩" };

type Ev = {
  dimensions?: Record<string, number>; violated_rules?: string[]; issues?: string[]; suggestions?: string[];
  history?: { attempt: number; score: number | null; problems: number }[];
};
const PASS = 7;

/** AI 质检：先说结论（达标没、自动改了几轮、分数怎么变的），再列「必须改 / 可以更好」，建议默认收起；
 *  没达标就能一键让 AI 按这些意见再改一轮（改得更好才替换）。 */
function Evaluation({ d, dirty }: { d: DraftDetail; dirty: boolean }) {
  const ev = d.evaluation as Ev;
  const dims = Object.entries(ev.dimensions ?? {});
  const { data: jobs = [] } = useActiveJobs(d.account_id);
  const revise = useRevise(d.id, d.account_id);
  const [note, setNote] = useState("");
  const [showTips, setShowTips] = useState(false);
  const job = jobs.find((j) => j.kind === "revise_draft" && isActive(j) && (j.payload as { draft_id?: string }).draft_id === d.id);
  const lastJob = jobs.find((j) => j.kind === "revise_draft" && (j.payload as { draft_id?: string }).draft_id === d.id);
  if (!dims.length && !d.check_issues.length) return null;

  const must = [...d.check_issues, ...(ev.violated_rules ?? []).map((r) => `没遵守账号规则：${r}`)];
  const better = ev.issues ?? [];
  const tips = ev.suggestions ?? [];
  const history = (ev.history ?? []).filter((h) => h.score != null);
  const rounds = Math.max(0, d.attempts - 1);
  const passed = !d.needs_attention;
  const last = (job?.events as JobEvent[] | undefined)?.at(-1);
  return (
    <Card className={cn(!passed && "border-amber-200")} >
      <div id="qc" />
      <CardHead icon={<Sparkles />} title="AI 质检"
        action={d.score != null && <span className={cn("text-lg font-semibold", passed ? "text-indigo-600" : "text-amber-600")}>{d.score.toFixed(1)}<span className="text-xs font-normal text-muted-foreground"> / 10</span></span>} />
      <CardBody className="space-y-4 text-sm">
        <div className={cn("rounded-xl px-4 py-3", passed ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900")}>
          <div className="font-medium">
            {passed ? `达标了（${PASS} 分合格），可以直接用` : `还差一点：${PASS} 分合格，现在 ${d.score?.toFixed(1) ?? "未评分"}`}
          </div>
          <div className="mt-0.5 text-xs opacity-80">
            {rounds > 0 ? `AI 按质检意见一共改了 ${rounds} 轮，留下的是分数最高的一版` : "写完一版就通过了质检"}
            {!passed && must.length > 0 && `，下面 ${must.length} 处必须改的还没改掉`}
          </div>
          {history.length > 1 && (
            <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
              {history.map((h, i) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 && <span className="opacity-40">→</span>}
                  <span className={cn("rounded-md px-1.5 py-0.5", h.score === d.score ? "bg-white font-semibold shadow-sm" : "bg-white/50")}>
                    {(h.attempt ?? i + 1) <= 1 ? "初稿" : `第${(h.attempt ?? i + 1) - 1}轮`} {h.score?.toFixed(1)}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>

        {dims.length > 0 && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-5">
            {dims.map(([k, v]) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-xs"><span className="text-muted-foreground">{DIM[k] ?? k}</span><span className="font-medium">{v}</span></div>
                <div className="h-1.5 rounded-full bg-muted"><div className={cn("h-full rounded-full", v < 6 ? "bg-amber-400" : "bg-brand-gradient")} style={{ width: `${Math.min(100, v * 10)}%` }} /></div>
              </div>
            ))}
          </div>
        )}

        {must.length > 0 && (
          <div>
            <div className="mb-1.5 text-xs font-medium text-red-600">必须改（{must.length}）</div>
            <ul className="space-y-1.5">{must.map((x) => <li key={x} className="flex gap-2 text-red-700"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{x}</li>)}</ul>
          </div>
        )}
        {better.length > 0 && (
          <div>
            <div className="mb-1.5 text-xs font-medium text-amber-700">可以更好（{better.length}）</div>
            <ul className="space-y-1.5">{better.map((x) => <li key={x} className="flex gap-2 text-amber-800"><span className="shrink-0">·</span>{x}</li>)}</ul>
          </div>
        )}
        {tips.length > 0 && (
          <div>
            <button className="cursor-pointer text-xs font-medium text-indigo-600 hover:underline" onClick={() => setShowTips((v) => !v)}>
              {showTips ? "收起修改建议" : `看 ${tips.length} 条具体怎么改`}
            </button>
            {showTips && <ul className="mt-1.5 space-y-1.5">{tips.map((x) => <li key={x} className="flex gap-2 text-muted-foreground"><span className="shrink-0">💡</span>{x}</li>)}</ul>}
          </div>
        )}

        <div className="space-y-2 rounded-xl border-2 border-dashed border-indigo-200 p-3">
          {job ? (
            <div className="flex items-center gap-2 text-indigo-700"><Spinner className="size-4" />AI 正在按这些意见改…<span className="truncate text-xs text-muted-foreground">{last?.message}</span></div>
          ) : (
            <>
              <div className="text-xs text-muted-foreground">
                {passed ? "还想调？说一句要求，AI 在这版上改，改得更好才替换。" : "让 AI 按上面的意见在这版上再改（最多 2 轮，改得更好才替换，不会越改越差）。也可以自己改完点保存。"}
              </div>
              <div className="flex gap-2">
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="补充要求（可选），例如：开头更直接、再短一点"
                  className="min-w-0 flex-1 rounded-lg border bg-card px-3 py-1.5 text-sm outline-none focus:border-indigo-300" />
                <Button size="sm" variant={passed ? "outline" : "gradient"} loading={revise.isPending} disabled={dirty || (passed && !note.trim())}
                  title={dirty ? "先保存你的修改" : undefined}
                  onClick={() => revise.mutate(note, { onSuccess: () => setNote("") })}>
                  {!revise.isPending && <Wand2 />}{passed ? "按要求改" : "按意见再改一轮"}
                </Button>
              </div>
              {dirty && <p className="text-xs text-amber-600">你有没保存的修改，先保存再让 AI 改</p>}
              {lastJob?.status === "succeeded" && <p className="text-xs text-emerald-600">{(lastJob.events as JobEvent[]).at(-1)?.message}</p>}
              {lastJob?.status === "failed" && <p className="text-xs text-red-600">上次没改成：{lastJob.error}</p>}
              <ErrorText error={revise.error} />
            </>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

function FeedbackCard({ d }: { d: DraftDetail }) {
  const act = useDraftActions(d.id);
  const { add } = useRules(d.account_id);
  const { data: account } = useAccount(d.account_id);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  const [learned, setLearned] = useState<S["LearnOut"] | null>(null);
  const [accepted, setAccepted] = useState<string[]>([]);
  const rate = (rating: "good" | "bad") => act.feedback.mutate({ rating, comment }, { onSuccess: () => { setSent(true); setComment(""); } });

  return (
    <Card>
      <CardHead icon={<Star />} title="反馈与学习" desc="说说哪里好、哪里不好；你改过的地方也能让小媒学会，下次少改" />
      <CardBody className="space-y-3 text-sm">
        <Textarea rows={2} placeholder="哪里好、哪里不好？（可选）" value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => rate("good")} loading={act.feedback.isPending}><ThumbsUp className="text-green-600" />写得好</Button>
          <Button size="sm" variant="outline" onClick={() => rate("bad")} loading={act.feedback.isPending}><ThumbsDown className="text-red-500" />不太行</Button>
          {sent && <span className="text-xs text-muted-foreground">收到 ✓</span>}
          <Button size="sm" variant="gradient" className="ml-auto" loading={act.learn.isPending} onClick={() => act.learn.mutate(undefined, { onSuccess: setLearned })}>
            {!act.learn.isPending && <Sparkles />}学我的改法
          </Button>
        </div>
        {d.edited && !learned && <p className="text-xs text-muted-foreground">你改过这篇，点「学习」让小媒总结你的偏好。</p>}
        <ErrorText error={act.learn.error} />
        {learned && (
          <div className="space-y-2 rounded-lg bg-purple-50/60 p-3">
            {learned.summary && <p className="text-purple-800">{learned.summary}</p>}
            {learned.rules.length === 0 && <p className="text-muted-foreground">没发现需要新增的要求。</p>}
            {learned.rules.map((r) => {
              const exists = accepted.includes(r) || account?.rules.some((x) => x.text === r);
              return (
                <div key={r} className="flex items-center gap-2 rounded-md bg-card px-3 py-2">
                  <span className="flex-1">{r}</span>
                  <Button size="xs" variant={exists ? "ghost" : "outline"} disabled={exists} onClick={() => add.mutate({ text: r, source: "learned" }, { onSuccess: () => setAccepted([...accepted, r]) })}>
                    {exists ? "已加入" : "加进文案要求"}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function PhonePreview({ d, title, body, tags, idx, onIdx }: {
  d: DraftDetail; title: string; body: string; tags: string[]; idx: number; onIdx: (i: number) => void;
}) {
  const cur = d.images[idx];
  const { data: account } = useAccount(d.account_id);
  const name = account?.name ?? "我的账号";
  return (
    <div className="mx-auto w-full max-w-[360px] overflow-hidden rounded-[32px] border-[6px] border-gray-900 bg-white shadow-xl">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <ChevronLeft className="size-4" />
        <div className="flex items-center gap-1.5">
          <div className="flex size-6 items-center justify-center rounded-full bg-gradient-to-br from-pink-400 to-[#ff2442] text-[10px] font-bold text-white">{name.slice(0, 1)}</div>
          <span className="text-xs font-medium">{name}</span>
        </div>
        <span className="rounded-full border border-[#ff2442] px-2 py-0.5 text-[10px] text-[#ff2442]">关注</span>
      </div>
      <div className="h-[560px] overflow-y-auto">
        <div className="relative flex aspect-[3/4] items-center justify-center bg-slate-100">
          {cur?.url ? <img src={cur.url} alt="" className="size-full object-cover" />
            : cur && (cur.status === "pending" || cur.status === "running") ? <div className="flex flex-col items-center gap-2 text-xs text-muted-foreground"><Spinner className="size-5" />配图生成中</div>
            : <div className="px-8 text-center text-xs text-muted-foreground"><ImageIcon className="mx-auto mb-2 size-8 opacity-30" />{cur ? cur.prompt : "暂无配图"}</div>}
          {d.images.length > 1 && (
            <div className="absolute bottom-2.5 left-1/2 flex -translate-x-1/2 gap-1">
              {d.images.map((_, k) => <button key={k} onClick={() => onIdx(k)} className={cn("size-1.5 cursor-pointer rounded-full", k === idx ? "bg-[#ff2442]" : "bg-gray-400/60")} />)}
            </div>
          )}
        </div>
        <div className="space-y-2.5 p-3.5">
          <h2 className="text-[15px] font-bold leading-snug">{title || "标题"}</h2>
          <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{body}</p>
          <div className="flex flex-wrap gap-1.5 text-[13px] text-[#13386c]">{tags.map((t) => <span key={t}>#{t}</span>)}</div>
          <p className="text-[11px] text-muted-foreground">刚刚</p>
        </div>
      </div>
      <div className="flex items-center gap-3 border-t px-3 py-2">
        <div className="flex-1 rounded-full bg-gray-100 px-3 py-1 text-[11px] text-muted-foreground">说点什么...</div>
        <Heart className="size-4" /><Star className="size-4" /><MessageCircle className="size-4" />
      </div>
    </div>
  );
}
