import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronLeft, Copy, Download, Edit, Eye, FileText, Heart, Image as ImageIcon,
  MessageCircle, PenLine, RefreshCw, Save, Share2, Sparkles, Star, Tag, ThumbsDown, ThumbsUp, Trash2, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { DraftDetail, S } from "../api/client";
import { api, unwrap } from "../api/client";
import { useAccount, useDraft, useDraftActions, useRules } from "../api/hooks";
import { Header } from "../components/Header";
import { Badge, Button, Card, CardBody, CardHead, Empty, ErrorText, Input, Spinner, Textarea } from "../components/ui";
import { cn, DRAFT_STATUS, timeAgo } from "../lib/utils";

export function DraftPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: d, isLoading } = useDraft(id);
  const act = useDraftActions(id);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [preview, setPreview] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!d) return;
    setTitle(d.title);
    setBody(d.body);
    setTags(d.tags.join(", "));
  }, [d?.id, d?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <div className="flex justify-center py-20"><Spinner className="size-6" /></div>;
  if (!d) return <Empty title="草稿不存在" action={<Link to="/"><Button size="sm">回到首页</Button></Link>} />;

  const tagList = tags.split(/[,，\s#]+/).map((t) => t.trim()).filter(Boolean);
  const dirty = title !== d.title || body !== d.body || tagList.join(",") !== d.tags.join(",");
  const st = DRAFT_STATUS[d.status];
  const save = () => act.update.mutate({ title, body, tags: tagList });

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

  return (
    <div className={cn("min-h-full", preview ? "bg-gray-100" : "bg-gradient-to-br from-slate-50 via-white to-indigo-50/40")}>
      <Header
        narrow
        left={<>
          {preview
            ? <Button variant="ghost" size="sm" onClick={() => setPreview(false)}><ArrowLeft />返回</Button>
            : <Link to={back}><Button variant="ghost" size="sm"><ArrowLeft />返回</Button></Link>}
          <div>
            <div className="flex items-center gap-2 font-bold">{preview ? "内容预览" : "编辑内容"}<Badge className={st.cls}>{st.label}</Badge></div>
            <div className="text-xs text-muted-foreground">
              {preview ? "小红书图文效果" : <>{d.score != null && `质检 ${d.score.toFixed(1)}/10 · `}改写 {d.attempts} 轮 · {timeAgo(d.created_at)}</>}
            </div>
          </div>
        </>}
        right={<>
          {preview
            ? <Button variant="outline" size="sm" onClick={() => setPreview(false)}><Edit />编辑</Button>
            : <Button variant="outline" size="sm" className="border-indigo-200 text-indigo-600" onClick={() => setPreview(true)}><Eye />预览</Button>}
          <Button variant="outline" size="sm" disabled={!dirty} loading={act.update.isPending} onClick={save}><Save />保存</Button>
          <Button variant="outline" size="sm" onClick={copy}>{copied ? <Check /> : <Copy />}{copied ? "已复制" : "复制文案"}</Button>
          <Button variant="gradient" size="sm" onClick={exportZip}><Download />导出图文包</Button>
        </>}
      />

      {preview ? (
        <PhonePreview d={d} title={title} body={body} tags={tagList} onExport={exportZip} />
      ) : (
        <div className="container mx-auto px-6 py-8">
          {d.needs_attention && (
            <div className="mb-6 flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              <AlertTriangle className="size-5 shrink-0 text-amber-500" />
              这篇没达到质检合格线（试了 {d.attempts} 轮取了最好的一版），发之前请仔细看一下下方的质检意见。
            </div>
          )}
          <div className="grid gap-8 lg:grid-cols-[1fr_380px]">
            <div className="space-y-6">
              <Card>
                <CardHead icon={<PenLine />} title="标题" desc="吸引人的标题能让内容获得更多关注" action={<span className={cn("text-xs", [...title].length > 20 ? "text-red-500" : "text-muted-foreground")}>{[...title].length}/20</span>} />
                <CardBody><Input value={title} onChange={(e) => setTitle(e.target.value)} /></CardBody>
              </Card>
              <Card>
                <CardHead icon={<FileText />} title="正文" desc="撰写优质内容，分享你的见解和故事" action={<span className="text-xs text-muted-foreground">{[...body].length} 字</span>} />
                <CardBody><Textarea rows={14} value={body} onChange={(e) => setBody(e.target.value)} /></CardBody>
              </Card>
              <Card>
                <CardHead icon={<Tag />} title="标签" desc="用逗号分隔，如：理财,存钱,打工人" />
                <CardBody><Input value={tags} onChange={(e) => setTags(e.target.value)} /></CardBody>
              </Card>
              <ErrorText error={act.update.error} />
              <Evaluation d={d} />
              <FeedbackCard d={d} />
              <div className="flex flex-wrap gap-2">
                {d.status !== "approved" && <Button variant="outline" size="sm" onClick={() => act.update.mutate({ status: "approved" })}><CheckCircle2 className="text-green-600" />标为可以发</Button>}
                {d.status !== "rejected" && <Button variant="outline" size="sm" onClick={() => act.update.mutate({ status: "rejected" })}><X />不要了</Button>}
                <Button variant="danger-outline" size="sm" onClick={() => { if (confirm("删除这篇草稿？")) act.remove.mutate(undefined, { onSuccess: () => nav(back) }); }}>
                  <Trash2 />删除
                </Button>
              </div>
            </div>
            <ImagesCard d={d} />
          </div>
        </div>
      )}
    </div>
  );
}

function ImagesCard({ d }: { d: DraftDetail }) {
  const act = useDraftActions(d.id);
  const [i, setI] = useState(0);
  const cur = d.images[i];
  const done = d.images.filter((x) => x.status === "done").length;
  return (
    <div className="lg:sticky lg:top-24 lg:self-start">
      <Card>
        <CardHead icon={<ImageIcon />} title="图片" action={<span className="text-xs text-muted-foreground">{done}/{d.images.length}</span>} />
        <CardBody className="space-y-4">
          {cur ? <>
            <div className="group relative flex aspect-[3/4] items-center justify-center overflow-hidden rounded-xl bg-muted/60">
              {cur.status === "done" && cur.url ? (
                <img src={cur.url} alt={cur.prompt} className="size-full object-cover" />
              ) : cur.status === "pending" || cur.status === "running" ? (
                <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground"><Spinner className="size-6" />第 {cur.idx + 1} 张 · 生成中</div>
              ) : (
                <div className="flex flex-col items-center gap-2 p-4 text-center text-sm text-muted-foreground">
                  <ImageIcon className="size-10 opacity-40" />
                  第 {cur.idx + 1} 张 · {cur.status === "skipped" ? "未配置配图服务" : cur.error || "生成失败"}
                </div>
              )}
            </div>
            {d.images.length > 1 && (
              <div className="flex gap-1.5 overflow-x-auto">
                {d.images.map((im, k) => (
                  <button key={im.id} onClick={() => setI(k)} className={cn("h-[60px] w-[45px] shrink-0 cursor-pointer overflow-hidden rounded-md border-2 bg-muted", k === i ? "border-indigo-500" : "border-transparent")}>
                    {im.url ? <img src={im.url} alt="" className="size-full object-cover" /> : <span className="text-[10px] text-muted-foreground">{k + 1}</span>}
                  </button>
                ))}
              </div>
            )}
            <div>
              <div className="mb-1.5 text-xs text-muted-foreground">第 {cur.idx + 1} 张{cur.idx === 0 && "（封面）"} · 提示词</div>
              <div className="flex items-start gap-2">
                <div className="flex-1 rounded-md bg-input-background px-3 py-2 text-sm">{cur.prompt}</div>
                <Button variant="outline" size="sm" className="px-2" aria-label="重新生成这张" loading={act.images.isPending} onClick={() => act.images.mutate(cur.idx)}>
                  {!act.images.isPending && <RefreshCw className="text-indigo-500" />}
                </Button>
              </div>
            </div>
          </> : <p className="text-sm text-muted-foreground">这篇没有配图提示词</p>}
          <Button variant="outline" className="w-full" loading={act.images.isPending} onClick={() => act.images.mutate(undefined)}><RefreshCw />全部重新生成</Button>
          <ErrorText error={act.images.error} />
        </CardBody>
      </Card>
    </div>
  );
}

const DIM: Record<string, string> = { hook: "吸引力", value: "价值感", voice: "人设口吻", fit: "贴合定位", rules: "守规矩" };

function Evaluation({ d }: { d: DraftDetail }) {
  const ev = d.evaluation as { dimensions?: Record<string, number>; violated_rules?: string[]; issues?: string[]; suggestions?: string[] };
  const dims = Object.entries(ev.dimensions ?? {});
  if (!dims.length && !d.check_issues.length) return null;
  return (
    <Card className="border-indigo-200">
      <CardHead icon={<Sparkles />} title="AI 质检" desc={d.score != null ? `综合 ${d.score.toFixed(1)} / 10` : "未评分"} />
      <CardBody className="space-y-3 text-sm">
        {dims.length > 0 && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
            {dims.map(([k, v]) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-xs"><span className="text-muted-foreground">{DIM[k] ?? k}</span><span className="font-medium">{v}</span></div>
                <div className="h-1.5 rounded-full bg-muted"><div className="h-full rounded-full bg-brand-gradient" style={{ width: `${Math.min(100, v * 10)}%` }} /></div>
              </div>
            ))}
          </div>
        )}
        {[...d.check_issues, ...(ev.violated_rules ?? []).map((r) => `违反规矩：${r}`)].map((x) => <p key={x} className="text-red-600">⚠ {x}</p>)}
        {(ev.issues ?? []).map((x) => <p key={x} className="text-amber-700">· {x}</p>)}
        {(ev.suggestions ?? []).map((x) => <p key={x} className="text-muted-foreground">💡 {x}</p>)}
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
    <Card className="border-purple-200">
      <CardHead icon={<Star />} title="反馈与学习" desc="告诉 AI 哪里好哪里不好；改过的稿子也能让它学你的改法，越用越懂你" />
      <CardBody className="space-y-3 text-sm">
        <Textarea rows={2} placeholder="哪里好、哪里不好？（可选）" value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => rate("good")} loading={act.feedback.isPending}><ThumbsUp className="text-green-600" />写得好</Button>
          <Button size="sm" variant="outline" onClick={() => rate("bad")} loading={act.feedback.isPending}><ThumbsDown className="text-red-500" />不太行</Button>
          {sent && <span className="text-xs text-muted-foreground">收到 ✓</span>}
          <Button size="sm" variant="gradient" className="ml-auto" loading={act.learn.isPending} onClick={() => act.learn.mutate(undefined, { onSuccess: setLearned })}>
            {!act.learn.isPending && <Sparkles />}从修改和反馈中学习
          </Button>
        </div>
        {d.edited && !learned && <p className="text-xs text-muted-foreground">你改过这篇，点「学习」让小媒总结你的偏好。</p>}
        <ErrorText error={act.learn.error} />
        {learned && (
          <div className="space-y-2 rounded-lg bg-purple-50/60 p-3">
            {learned.summary && <p className="text-purple-800">{learned.summary}</p>}
            {learned.rules.length === 0 && <p className="text-muted-foreground">没发现需要新增的规矩。</p>}
            {learned.rules.map((r) => {
              const exists = accepted.includes(r) || account?.rules.some((x) => x.text === r);
              return (
                <div key={r} className="flex items-center gap-2 rounded-md bg-card px-3 py-2">
                  <span className="flex-1">{r}</span>
                  <Button size="xs" variant={exists ? "ghost" : "outline"} disabled={exists} onClick={() => add.mutate({ text: r, source: "learned" }, { onSuccess: () => setAccepted([...accepted, r]) })}>
                    {exists ? "已加入" : "加为规矩"}
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

function PhonePreview({ d, title, body, tags, onExport }: { d: DraftDetail; title: string; body: string; tags: string[]; onExport: () => void }) {
  const imgs = d.images.filter((x) => x.url);
  const [i, setI] = useState(0);
  const { data: account } = useAccount(d.account_id);
  const name = account?.name ?? "我的账号";
  return (
    <div className="flex flex-col items-center gap-6 px-4 py-6">
      <div className="w-[390px] overflow-hidden rounded-[44px] border-[3px] border-gray-900 bg-white shadow-2xl">
        <div className="relative flex items-center justify-between px-6 pb-1 pt-3 text-xs font-semibold">
          <span>9:41</span>
          <div className="absolute left-1/2 top-2.5 h-6 w-24 -translate-x-1/2 rounded-full bg-black" />
          <span>●●●</span>
        </div>
        <div className="flex items-center justify-between border-b px-4 py-2">
          <ChevronLeft className="size-5" />
          <span className="border-b-2 border-[#ff2442] pb-0.5 text-sm font-medium">图文</span>
          <Share2 className="size-4" />
        </div>
        <div className="h-[620px] overflow-y-auto">
          <div className="relative flex aspect-[3/4] items-center justify-center bg-slate-50">
            {imgs.length ? (
              <>
                <img src={imgs[i]?.url ?? ""} alt="" className="size-full object-cover" />
                {imgs.length > 1 && (
                  <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1">
                    {imgs.map((_, k) => <button key={k} onClick={() => setI(k)} className={cn("size-1.5 cursor-pointer rounded-full", k === i ? "bg-[#ff2442]" : "bg-white/70")} />)}
                  </div>
                )}
              </>
            ) : (
              <div className="text-center text-muted-foreground">
                <div className="mx-auto mb-3 flex size-16 items-center justify-center rounded-full bg-gray-200 text-3xl">📷</div>
                <p className="text-sm">暂无配图</p>
              </div>
            )}
          </div>
          <div className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <div className="flex size-9 items-center justify-center rounded-full bg-gradient-to-br from-pink-400 to-[#ff2442] text-sm font-bold text-white">{name.slice(0, 1)}</div>
              <div className="flex-1"><div className="text-sm font-semibold">{name}</div><div className="text-xs text-muted-foreground">刚刚</div></div>
              <span className="rounded-full border border-[#ff2442] px-3 py-0.5 text-xs text-[#ff2442]">关注</span>
            </div>
            <h2 className="font-bold leading-snug">{title}</h2>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{body}</p>
            <div className="flex flex-wrap gap-1.5 text-sm text-[#13386c]">{tags.map((t) => <span key={t}>#{t}</span>)}</div>
          </div>
        </div>
        <div className="flex items-center gap-4 border-t px-4 py-2.5">
          <div className="flex-1 rounded-full bg-gray-100 px-3 py-1.5 text-xs text-muted-foreground">说点什么...</div>
          <Heart className="size-5" /><Star className="size-5" /><MessageCircle className="size-5" />
        </div>
      </div>
      <div className="flex w-[390px] items-center rounded-xl border bg-card p-4 shadow-sm">
        {[[[...body].length, "字数"], [imgs.length, "图片"], [tags.length, "标签"]].map(([n, l]) => (
          <div key={l} className="flex-1 border-r text-center last:border-0"><div className="font-semibold">{n}</div><div className="text-xs text-muted-foreground">{l}</div></div>
        ))}
        <Button variant="gradient" size="sm" className="ml-4 from-[#ff2442] to-pink-500" onClick={onExport}><Download />导出</Button>
      </div>
    </div>
  );
}
