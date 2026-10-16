import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronLeft, Copy, Download, ImageIcon, RefreshCw, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { S } from "../api/client";
import { api, unwrap } from "../api/client";
import { useAccount, useDraft, useDraftActions, useRules } from "../api/hooks";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Spinner, Textarea } from "../components/ui";
import { DRAFT_STATUS, timeAgo } from "../lib/utils";

export function DraftPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { data: d, isLoading } = useDraft(id);
  const act = useDraftActions(id);
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!d) return;
    setTitle(d.title);
    setBody(d.body);
    setTags(d.tags.join(" "));
  }, [d?.id, d?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <div className="p-8"><Spinner /></div>;
  if (!d) return <div className="p-8"><Empty title="草稿不存在" /></div>;

  const tagList = tags.split(/[\s,，#]+/).map((t) => t.trim()).filter(Boolean);
  const dirty = title !== d.title || body !== d.body || tagList.join(" ") !== d.tags.join(" ");
  const st = DRAFT_STATUS[d.status];
  const ev = d.evaluation as { dimensions?: Record<string, number>; violated_rules?: string[]; issues?: string[]; suggestions?: string[] };

  const copy = async () => {
    const { text } = await unwrap(api.GET("/api/drafts/{draft_id}/text", { params: { path: { draft_id: id } } })) as { text: string };
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Link to={`/accounts/${d.account_id}?tab=drafts`} className="flex items-center text-sm text-muted hover:text-ink"><ChevronLeft className="size-4" />返回</Link>
        <Badge tone={st.tone}>{st.label}</Badge>
        {d.needs_attention && <Badge tone="red"><AlertTriangle className="mr-0.5 size-3" />没达到合格线，发之前看仔细</Badge>}
        <span className="text-sm text-muted">{d.score != null && `${d.score.toFixed(1)} 分 · `}改写 {d.attempts} 轮 · {timeAgo(d.created_at)}</span>
        <div className="ml-auto flex gap-2">
          <Button size="sm" onClick={copy}>{copied ? <Check className="size-4" /> : <Copy className="size-4" />}{copied ? "已复制" : "复制文案"}</Button>
          <a href={`/api/drafts/${id}/export`} onClick={() => setTimeout(() => { qc.invalidateQueries({ queryKey: ["draft", id] }); qc.invalidateQueries({ queryKey: ["drafts"] }); }, 1500)}>
            <Button size="sm" variant="primary"><Download className="size-4" />下载图文包</Button>
          </a>
          {d.status !== "approved" && <Button size="sm" onClick={() => act.update.mutate({ status: "approved" })}>标为可以发</Button>}
          {d.status !== "rejected" && <Button size="sm" variant="ghost" onClick={() => act.update.mutate({ status: "rejected" })}>不要了</Button>}
          <Button size="sm" variant="danger" aria-label="删除" onClick={() => { if (confirm("删除这篇草稿？")) act.remove.mutate(undefined, { onSuccess: () => nav(`/accounts/${d.account_id}`) }); }}>
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card className="space-y-4 p-4">
            <Field label={`标题（${[...title].length}/20）`}><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <Field label={`正文（${[...body].length} 字）`}><Textarea rows={16} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
            <Field label="话题标签" hint="空格分隔，不用带 #"><Input value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
            <ErrorText error={act.update.error} />
            <div className="flex items-center justify-end gap-2">
              {d.edited && <span className="text-xs text-muted">你改过这篇，可以在右边让 AI 学习你的改法</span>}
              <Button variant="ghost" disabled={!dirty} onClick={() => { setTitle(d.title); setBody(d.body); setTags(d.tags.join(" ")); }}>撤销</Button>
              <Button variant="primary" disabled={!dirty} loading={act.update.isPending} onClick={() => act.update.mutate({ title, body, tags: tagList })}>保存修改</Button>
            </div>
          </Card>

          <Card className="space-y-3 p-4">
            <div className="flex items-center justify-between">
              <div className="font-medium">配图（{d.images.length}）</div>
              <Button size="sm" loading={act.images.isPending} onClick={() => act.images.mutate(undefined)}><RefreshCw className="size-3.5" />全部重画</Button>
            </div>
            <ErrorText error={act.images.error} />
            <div className="grid grid-cols-3 gap-3">
              {d.images.map((im) => (
                <div key={im.id} className="space-y-1">
                  <div className="group relative flex aspect-[3/4] items-center justify-center overflow-hidden rounded-lg bg-surface">
                    {im.status === "done" && im.url ? (
                      <a href={im.url} target="_blank" rel="noreferrer"><img src={im.url} alt={im.prompt} className="size-full object-cover" /></a>
                    ) : im.status === "pending" || im.status === "running" ? (
                      <div className="flex flex-col items-center gap-1 text-xs text-muted"><Spinner />生成中</div>
                    ) : (
                      <div className="flex flex-col items-center gap-1 p-2 text-center text-xs text-muted">
                        <ImageIcon className="size-6 text-line" />
                        {im.status === "skipped" ? "未配置配图服务" : im.error || "生成失败"}
                      </div>
                    )}
                    <button
                      onClick={() => act.images.mutate(im.idx)}
                      className="absolute right-1.5 top-1.5 cursor-pointer rounded-md bg-white/90 p-1 opacity-0 shadow group-hover:opacity-100"
                      aria-label="重画这张"
                    >
                      <RefreshCw className="size-3.5" />
                    </button>
                  </div>
                  <div className="line-clamp-2 text-xs text-muted" title={im.prompt}>{im.idx === 0 ? "封面 · " : ""}{im.prompt}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Preview title={title} body={body} tags={tagList} cover={d.images.find((i) => i.url)?.url ?? null} />
          <Evaluation ev={ev} issues={d.check_issues} />
          <FeedbackCard draftId={id} accountId={d.account_id} />
        </div>
      </div>
    </div>
  );
}

function Preview({ title, body, tags, cover }: { title: string; body: string; tags: string[]; cover: string | null }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex aspect-[3/4] max-h-80 w-full items-center justify-center bg-surface">
        {cover ? <img src={cover} alt="" className="size-full object-cover" /> : <ImageIcon className="size-8 text-line" />}
      </div>
      <div className="space-y-2 p-4">
        <div className="font-semibold">{title}</div>
        <div className="max-h-60 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed">{body}</div>
        <div className="flex flex-wrap gap-1 text-sm text-[#13386c]">{tags.map((t) => <span key={t}>#{t}</span>)}</div>
      </div>
    </Card>
  );
}

const DIM: Record<string, string> = { hook: "吸引力", value: "价值感", voice: "人设口吻", fit: "贴合定位", rules: "守规矩" };

function Evaluation({ ev, issues }: { ev: { dimensions?: Record<string, number>; violated_rules?: string[]; issues?: string[]; suggestions?: string[] }; issues: string[] }) {
  const dims = Object.entries(ev.dimensions ?? {});
  if (!dims.length && !issues.length) return null;
  return (
    <Card className="space-y-2 p-4 text-sm">
      <div className="font-medium">AI 评审</div>
      {dims.length > 0 && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {dims.map(([k, v]) => <div key={k} className="flex justify-between"><span className="text-muted">{DIM[k] ?? k}</span><span>{v}</span></div>)}
        </div>
      )}
      {[...issues, ...(ev.violated_rules ?? []).map((r) => `违反规矩：${r}`)].map((x) => <div key={x} className="text-red-600">· {x}</div>)}
      {(ev.issues ?? []).map((x) => <div key={x} className="text-amber-700">· {x}</div>)}
      {(ev.suggestions ?? []).map((x) => <div key={x} className="text-muted">· {x}</div>)}
    </Card>
  );
}

function FeedbackCard({ draftId, accountId }: { draftId: string; accountId: string }) {
  const act = useDraftActions(draftId);
  const { add } = useRules(accountId);
  const { data: account } = useAccount(accountId);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  const [learned, setLearned] = useState<S["LearnOut"] | null>(null);
  const [accepted, setAccepted] = useState<string[]>([]);

  const rate = (rating: "good" | "bad") =>
    act.feedback.mutate({ rating, comment }, { onSuccess: () => { setSent(true); setComment(""); } });

  return (
    <Card className="space-y-3 p-4 text-sm">
      <div className="font-medium">反馈与学习</div>
      <Textarea rows={2} placeholder="哪里好、哪里不好？（可选）" value={comment} onChange={(e) => setComment(e.target.value)} />
      <div className="flex gap-2">
        <Button size="sm" onClick={() => rate("good")} loading={act.feedback.isPending}><ThumbsUp className="size-3.5" />写得好</Button>
        <Button size="sm" onClick={() => rate("bad")} loading={act.feedback.isPending}><ThumbsDown className="size-3.5" />不太行</Button>
        {sent && <span className="self-center text-xs text-muted">收到 ✓</span>}
      </div>
      <div className="border-t border-line pt-3">
        <Button size="sm" variant="primary" loading={act.learn.isPending} onClick={() => act.learn.mutate(undefined, { onSuccess: setLearned })}>
          从我的修改和反馈里学习
        </Button>
        <ErrorText error={act.learn.error} />
        {learned && (
          <div className="mt-3 space-y-2">
            {learned.summary && <div className="text-muted">{learned.summary}</div>}
            {learned.rules.length === 0 && <div className="text-muted">没发现需要新增的规矩。</div>}
            {learned.rules.map((r) => {
              const exists = accepted.includes(r) || account?.rules.some((x) => x.text === r);
              return (
                <div key={r} className="flex items-start gap-2 rounded-lg bg-surface p-2">
                  <span className="flex-1">{r}</span>
                  <Button size="sm" disabled={exists} onClick={() => add.mutate({ text: r, source: "learned" }, { onSuccess: () => setAccepted([...accepted, r]) })}>
                    {exists ? "已加入" : "加为规矩"}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
}
