import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronLeft, Copy, Download, Heart, Image as ImageIcon,
  ChevronRight, ExternalLink, Link2, MessageCircle, Pencil, Plus, RefreshCw, Save, Sparkles, Star, Tag, ThumbsDown, ThumbsUp,
  Trash2, Wand2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { DraftDetail, JobEvent, S } from "../api/client";
import { api, unwrap } from "../api/client";
import { type ImageOp, isActive, useAccount, useActiveJobs, useDraft, useDraftActions, useIsAdmin, useRevise, useRules, useSystem } from "../api/hooks";
import { ChatPanel } from "../components/ChatPanel";
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
  const [ask, setAsk] = useState(false);

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
            {d.score != null && `AI 打分 ${d.score.toFixed(1)} · `}{d.attempts > 1 ? `自动改了 ${d.attempts - 1} 轮 · ` : ""}{timeAgo(d.created_at)}
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
            <Button variant="outline" size="sm" onClick={() => setAsk(true)} title="直接说想怎么改：文案、第几张图、加一张删一张都行">
              <MessageCircle className="text-indigo-500" />让小媒改
            </Button>
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
              <span className="flex-1">AI 自动改了几轮还没完全达标，留下的是最好的一版。发之前看看 AI 的修改意见，或者让 AI 再改一轮。</span>
              <a href="#qc" className="shrink-0 font-medium hover:underline">看意见 ↓</a>
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
          <ReferenceCard d={d} />
          <ImagesCard d={d} i={imgIdx} setI={setImgIdx} onAsk={() => setAsk(true)} />
        </div>
      </div>
      {ask && <AskDrawer d={d} dirty={dirty} onClose={() => setAsk(false)} />}
    </div>
  );
}

/** 草稿页右侧抽屉：和小媒说怎么改这篇（小媒知道你正在看哪篇，能直接改文案、改配图） */
function AskDrawer({ d, dirty, onClose }: { d: DraftDetail; dirty: boolean; onClose: () => void }) {
  const { data: acc } = useAccount(d.account_id);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[90] flex bg-black/20" onClick={onClose}>
      <div className="ml-auto flex h-full w-full max-w-md flex-col shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {dirty && <div className="bg-amber-50 px-4 py-2 text-xs text-amber-800">你改的文案还没保存，小媒看到的是上次保存的版本，先保存再让它改文案更稳。</div>}
        <div className="min-h-0 flex-1">
          {acc ? <ChatPanel account={acc} draft={{ id: d.id, title: d.title }} onClose={onClose} />
            : <div className="flex h-full items-center justify-center bg-card"><Spinner /></div>}
        </div>
      </div>
    </div>
  );
}

type RefPost = { title?: string; url?: string; creator?: string; likes?: string; why?: string; kind?: string };
type Ref = RefPost & { source?: string; local?: string[]; extra?: RefPost[] };

/** 这篇参考了哪些帖子：文案可以学好几篇，配图只照主参考帖一篇（一套图统一）。主参考帖可以贴链接换掉，再「按它全部重新出图」。 */
function ReferenceCard({ d }: { d: DraftDetail }) {
  const act = useDraftActions(d.id);
  const ref = (d.reference ?? {}) as Ref;
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState("");
  const [justSet, setJustSet] = useState(false);
  const n = ref.local?.length ?? 0;
  const submit = () => url.trim() && act.reference.mutate(url.trim(), {
    onSuccess: () => { setEditing(false); setUrl(""); setJustSet(true); },
  });
  const busy = d.images.some((x) => x.status === "pending" || x.status === "running");
  return (
    <Card>
      <CardHead icon={<Link2 />} title="参考帖"
        action={!editing && <button className="cursor-pointer text-xs text-indigo-600 hover:underline" onClick={() => setEditing(true)}>{ref.title ? "换配图照的那篇" : "指定一篇"}</button>} />
      <CardBody className="space-y-3">
        {ref.title && <div className="text-[11px] font-medium text-muted-foreground">配图统一照这篇{(ref.extra?.length ?? 0) > 0 && "，文案也学它"}</div>}
        {ref.title ? (
          <div className="flex gap-3">
            {n > 0
              ? <img src={`/files/images/${ref.local![0]}`} alt="" className="h-[84px] w-[63px] shrink-0 rounded-md border object-cover" />
              : <div className="flex h-[84px] w-[63px] shrink-0 items-center justify-center rounded-md bg-muted"><ImageIcon className="size-4 text-muted-foreground" /></div>}
            <div className="min-w-0 flex-1 text-xs">
              {ref.url
                ? <a href={ref.url} target="_blank" rel="noreferrer" className="line-clamp-2 text-sm font-medium hover:text-indigo-600">{ref.title}<ExternalLink className="ml-1 inline size-3 text-muted-foreground" /></a>
                : <div className="line-clamp-2 text-sm font-medium">{ref.title}</div>}
              <div className="mt-1 text-muted-foreground">{[ref.creator, ref.likes && `${ref.likes} 赞`, n > 0 && `${n} 张图`].filter(Boolean).join(" · ")}</div>
              {ref.why && <div className="mt-1 text-muted-foreground">为什么选它：{ref.why}</div>}
            </div>
          </div>
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">这篇没有照着具体的帖子做（没找到合适的对标爆款）。贴一篇小红书图文笔记，配图就会一张对一张照着它的版式出。</p>
        )}
        {ref.title && n > 0 && !editing && !justSet && (
          <p className="text-xs leading-relaxed text-muted-foreground">配图一张对一张照着它的版式、文字位置和配色重做，内容换成这篇的；整套用同一份视觉规范，翻起来是一套。</p>
        )}
        {ref.title && n === 0 && (
          <p className="text-xs leading-relaxed text-muted-foreground">这篇的原图没拿到，配图按账号的配图风格统一出。</p>
        )}
        {(ref.extra?.length ?? 0) > 0 && (
          <div className="border-t pt-2.5">
            <div className="mb-1.5 text-[11px] font-medium text-muted-foreground">文案还参考了（只学标题和结构，不参与出图）</div>
            <ul className="space-y-1.5">
              {ref.extra!.map((x, k) => (
                <li key={k} className="text-xs">
                  {x.url
                    ? <a href={x.url} target="_blank" rel="noreferrer" className="line-clamp-1 font-medium hover:text-indigo-600">{x.title}<ExternalLink className="ml-1 inline size-3 text-muted-foreground" /></a>
                    : <span className="line-clamp-1 font-medium">{x.title}</span>}
                  <span className="text-muted-foreground">{[x.creator, x.likes && `${x.likes} 赞`, x.kind === "视频" && "视频"].filter(Boolean).join(" · ")}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {editing && (
          <div className="space-y-2">
            <div className="flex gap-2">
              <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} autoFocus
                placeholder="粘贴一篇小红书图文笔记的链接或分享文字"
                className="min-w-0 flex-1 rounded-md border bg-input-background px-2.5 py-1.5 text-xs outline-none focus:border-indigo-400" />
              <Button size="xs" loading={act.reference.isPending} disabled={!url.trim()} onClick={submit}>确定</Button>
              <Button size="xs" variant="ghost" onClick={() => { setEditing(false); act.reference.reset(); }}>取消</Button>
            </div>
            <ErrorText error={act.reference.error} />
          </div>
        )}
        {justSet && d.images.length > 0 && (
          <div className="flex items-center gap-2 rounded-lg bg-indigo-50 px-3 py-2 text-xs text-indigo-700">
            <span className="flex-1">换好了。文案不动，配图要按它整套重新出吗？</span>
            <Button size="xs" disabled={busy} loading={act.images.isPending}
              onClick={() => act.images.mutate("all", { onSuccess: () => setJustSet(false) })}>按它全部重新出图</Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function ImagesCard({ d, i, setI, onAsk }: { d: DraftDetail; i: number; setI: (i: number) => void; onAsk: () => void }) {
  const act = useDraftActions(d.id);
  const cur = d.images[i];
  // 改描述 / 在这张后面加一张：本地先写好，提交后改过的、新加的马上重新出图
  const [edit, setEdit] = useState<null | { mode: "update" | "add"; text: string }>(null);
  useEffect(() => setEdit(null), [cur?.id]);
  const run = (ops: ImageOp[], then?: () => void) =>
    act.editImages.mutate({ ops }, { onSuccess: () => { setEdit(null); then?.(); } });
  const done = d.images.filter((x) => x.status === "done").length;
  const skipped = d.images.length > 0 && d.images.every((x) => x.status === "skipped");
  const busy = d.images.filter((x) => x.status === "pending" || x.status === "running").length;
  const failedImgs = d.images.filter((x) => x.status === "failed");
  const failed = failedImgs.length;
  const firstErr = failedImgs[0]?.error?.slice(0, 40);
  const { data: sys } = useSystem();
  const [setup, setSetup] = useState(false);
  const admin = useIsAdmin();
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
              <span className="flex-1">{admin ? "还没配置 AI 配图，所以没出图。填一个生图 Key 就能自动出图，也可以先导出文案。" : "管理员还没配好 AI 配图，所以没出图，可以先导出文案。"}</span>
              {admin && <Button size="xs" variant="outline" onClick={() => setSetup(true)}>去配置</Button>}
            </div>)}
        {busy > 0 && (
          <div className="rounded-lg bg-indigo-50 px-3 py-2.5 text-xs text-indigo-700">
            <div className="mb-1.5 flex items-center gap-1.5">
              <Spinner className="size-3" /><span className="flex-1">正在出图：好了 {done}/{d.images.length} 张</span>
              <span className="text-indigo-500">几张一起出，一般 1-2 分钟</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-indigo-100">
              <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-700"
                style={{ width: `${Math.max(6, (done / d.images.length) * 100)}%` }} />
            </div>
          </div>
        )}
        {failed > 0 && busy === 0 && (
          <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
            <span className="flex-1">有 {failed} 张没出来{firstErr && `：${firstErr}`}</span>
            <Button size="xs" variant="outline" loading={act.images.isPending} onClick={() => act.images.mutate(undefined)}>补出这 {failed} 张</Button>
          </div>
        )}
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
              {cur.ref_url && (
                <a href={cur.ref_url} target="_blank" rel="noreferrer" className="shrink-0 text-center" title="这张照着参考帖的这张图做">
                  <img src={cur.ref_url} alt="" className="h-[64px] w-[48px] rounded-md border object-cover" />
                  <span className="mt-0.5 block text-[10px] text-muted-foreground">照着原帖第 {((d.reference as Ref).local ?? []).indexOf(cur.ref_url.replace("/files/images/", "")) + 1 || "?"} 张</span>
                </a>
              )}
              {edit?.mode === "update" ? (
                <Textarea autoFocus rows={5} value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })}
                  className="flex-1 text-xs leading-relaxed" placeholder="这张画什么、怎么构图、图上写哪几个字" />
              ) : (
                <p className="flex-1 rounded-md bg-input-background px-3 py-2 text-xs leading-relaxed">{cur.prompt}</p>
              )}
              {!edit && (
                <div className="flex flex-col gap-1.5">
                  <Button variant="outline" size="sm" className="px-2" title={cur.status === "running" || cur.status === "pending" ? "这张正在出" : "重新出这张"}
                    disabled={cur.status === "running" || cur.status === "pending"} loading={act.images.isPending && act.images.variables === cur.idx}
                    onClick={() => act.images.mutate(cur.idx)}>
                    {!(act.images.isPending && act.images.variables === cur.idx) && <RefreshCw className="text-indigo-500" />}
                  </Button>
                  <Button variant="outline" size="sm" className="px-2" title={busy > 0 ? "等这轮出完再改" : "改这张的描述，改完重出"} disabled={busy > 0}
                    onClick={() => setEdit({ mode: "update", text: cur.prompt })}>
                    <Pencil className="text-indigo-500" />
                  </Button>
                </div>
              )}
            </div>
            {edit?.mode === "update" && (
              <div className="mt-2 flex justify-end gap-2">
                <Button variant="ghost" size="xs" onClick={() => setEdit(null)}>取消</Button>
                <Button size="xs" disabled={!edit.text.trim() || edit.text.trim() === cur.prompt} loading={act.editImages.isPending}
                  onClick={() => run([{ op: "update", no: cur.idx + 1, description: edit.text.trim() }])}>改好了，重出这张</Button>
              </div>
            )}
          </div>
        ) : <p className="text-xs text-muted-foreground">这篇没有配图描述</p>}
        {edit?.mode === "add" ? (
          <div className="space-y-2 rounded-lg border border-dashed border-indigo-200 p-2.5">
            <div className="text-xs font-medium">{cur ? `在第 ${cur.idx + 1} 张后面加一张` : "加一张"}</div>
            <Textarea autoFocus rows={4} value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} className="text-xs leading-relaxed"
              placeholder="这张画什么？比如：清单图，大标题「3 个避坑点」，下面三行要点，和前面几张同一个风格" />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="xs" onClick={() => setEdit(null)}>取消</Button>
              <Button size="xs" disabled={!edit.text.trim()} loading={act.editImages.isPending}
                onClick={() => run([{ op: "add", after: cur ? cur.idx + 1 : null, description: edit.text.trim() }], () => setI(cur ? cur.idx + 1 : 0))}>加上并出图</Button>
            </div>
          </div>
        ) : !edit && (
          <div className="flex flex-wrap items-center gap-1 text-xs">
            <ImgAction disabled={busy > 0 || d.images.length >= 9} title={d.images.length >= 9 ? "最多 9 张" : "在这张后面加一张"} onClick={() => setEdit({ mode: "add", text: "" })}>
              <Plus className="size-3" />加一张
            </ImgAction>
            {cur && d.images.length > 1 && <>
              <ImgAction disabled={busy > 0 || i === 0} title="往前挪一位" onClick={() => run([{ op: "move", no: i + 1, to: i }], () => setI(i - 1))}>
                <ChevronLeft className="size-3" />前移
              </ImgAction>
              <ImgAction disabled={busy > 0 || i === d.images.length - 1} title="往后挪一位" onClick={() => run([{ op: "move", no: i + 1, to: i + 2 }], () => setI(i + 1))}>
                后移<ChevronRight className="size-3" />
              </ImgAction>
              <ImgAction disabled={busy > 0} title="删掉这张" danger
                onClick={() => confirm(`删掉第 ${i + 1} 张？`) && run([{ op: "remove", no: i + 1 }], () => setI(Math.max(0, i - 1)))}>
                <Trash2 className="size-3" />删掉
              </ImgAction>
            </>}
            <button onClick={onAsk} className="ml-auto cursor-pointer text-indigo-600 hover:underline">想大改？跟小媒说 →</button>
          </div>
        )}
        <ErrorText error={act.editImages.error} />
        {d.image_spec && <SpecNote spec={d.image_spec} />}
        {!skipped && d.images.length > 0 && (
          <Button variant="outline" size="sm" className="w-full" disabled={busy > 0} loading={act.images.isPending && act.images.variables === "all"}
            onClick={() => confirm(`${d.images.length} 张全部重新出？会用掉 ${d.images.length} 次生图额度`) && act.images.mutate("all")}>
            <RefreshCw />{busy > 0 ? "出图中…" : "全部重新出"}
          </Button>
        )}
        <ErrorText error={act.images.error} />
      </CardBody>
    </Card>
  );
}

function ImgAction({ children, danger, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean }) {
  return (
    <button {...p} className={cn("flex cursor-pointer items-center gap-0.5 rounded-md px-1.5 py-1 text-muted-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40",
      danger ? "hover:text-red-600" : "hover:text-foreground")}>{children}</button>
  );
}

/** 这套图统一的视觉规范：每张都带着它出，重出某一张也沿用 */
function SpecNote({ spec }: { spec: string }) {
  const [open, setOpen] = useState(false);
  return (
    <button onClick={() => setOpen(!open)} className="block w-full cursor-pointer rounded-md bg-muted/60 px-3 py-2 text-left text-xs text-muted-foreground hover:bg-muted">
      <span className="font-medium text-foreground">整套统一的风格</span>
      <span className="ml-1">（每张都照它，重出某张也不变）</span>
      <span className={cn("mt-1 block leading-relaxed", !open && "line-clamp-2")}>{spec}</span>
    </button>
  );
}

const DIM: Record<string, string> = { hook: "吸引力", value: "价值感", voice: "人设口吻", fit: "贴合定位", rules: "守规矩" };

type Item = { level: "must" | "nice"; where?: string; quote?: string; problem: string; fix?: string };
type Ev = {
  dimensions?: Record<string, number>; violated_rules?: string[]; issues?: string[]; suggestions?: string[];
  items?: Item[]; resolved?: number; edits?: { applied: number; skipped: number; unfixed?: string[] };
  history?: { attempt: number; score: number | null; problems: number }[];
  changes?: Change[]; attempted?: boolean;
};
type Change = { where: string; before: string; after: string; why?: string };
const PASS = 7;

/** AI 质检：先说结论（达标没、分数怎么变的），再列「AI 自己改了哪些地方」（改前 → 改后、为什么改）；
 *  AI 提的意见默认由 AI 自己落实，留在这里的只是「改过但没改好」的，需要人拿主意。 */
function Evaluation({ d, dirty }: { d: DraftDetail; dirty: boolean }) {
  const ev = d.evaluation as Ev;
  const dims = Object.entries(ev.dimensions ?? {});
  const { data: jobs = [] } = useActiveJobs(d.account_id);
  const revise = useRevise(d.id, d.account_id);
  const [note, setNote] = useState("");
  const [showTips, setShowTips] = useState(false);
  const [showChanges, setShowChanges] = useState(false);
  const job = jobs.find((j) => j.kind === "revise_draft" && isActive(j) && (j.payload as { draft_id?: string }).draft_id === d.id);
  const lastJob = jobs.find((j) => j.kind === "revise_draft" && (j.payload as { draft_id?: string }).draft_id === d.id);
  if (!dims.length && !d.check_issues.length) return null;

  const items = ev.items;
  const hard = [...d.check_issues, ...(ev.violated_rules ?? []).map((r) => `没遵守账号规则：${r}`)];
  const mustItems = items?.filter((i) => i.level === "must") ?? [];
  const niceItems = items?.filter((i) => i.level !== "must") ?? [];
  const must = [...hard, ...mustItems.map((i) => i.problem)];
  const better = items ? niceItems.map((i) => i.problem) : ev.issues ?? [];
  const tips = items ? [] : ev.suggestions ?? [];
  const history = (ev.history ?? []).filter((h) => h.score != null);
  const rounds = Math.max(0, d.attempts - 1);
  const passed = !d.needs_attention;
  const changes = ev.changes ?? [];
  const left = must.length + better.length;
  const tried = ev.attempted ?? false;
  const last = (job?.events as JobEvent[] | undefined)?.at(-1);
  return (
    <Card className={cn(!passed && "border-amber-200")} >
      <div id="qc" />
      <CardHead icon={<Sparkles />} title="AI 打分和修改意见"
        action={d.score != null && <span className={cn("text-lg font-semibold", passed ? "text-indigo-600" : "text-amber-600")}>{d.score.toFixed(1)}<span className="text-xs font-normal text-muted-foreground"> / 10</span></span>} />
      <CardBody className="space-y-4 text-sm">
        <div className={cn("rounded-xl px-4 py-3", passed ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900")}>
          <div className="font-medium">
            {passed ? `达标了（${PASS} 分合格），可以直接用` : `还差一点：${PASS} 分合格，现在 ${d.score?.toFixed(1) ?? "未评分"}`}
          </div>
          <div className="mt-0.5 text-xs opacity-80">
            {changes.length > 0 ? `AI 自己挑出问题、自己改好了 ${changes.length} 处（改了 ${rounds} 轮）`
              : rounds > 0 ? `AI 按意见改了 ${rounds} 轮，留下的是分数最高的一版` : "写完一版就达标了，没有要改的"}
            {left > 0 && (tried ? `；还有 ${left} 处 AI 改不好，需要你看一下` : `；还有 ${left} 处可以改`)}
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

        {changes.length > 0 && (
          <div>
            <button className="flex cursor-pointer items-center gap-1 text-xs font-medium text-emerald-700 hover:underline" onClick={() => setShowChanges((v) => !v)}>
              <CheckCircle2 className="size-3.5" />AI 已经自动改好的 {changes.length} 处 {showChanges ? "收起" : "· 点开看改了什么"}
            </button>
            {showChanges && (
              <ul className="mt-1.5 space-y-1.5">
                {changes.map((c, k) => (
                  <li key={k} className="rounded-lg bg-emerald-50/60 px-3 py-2 text-xs">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="shrink-0 rounded bg-emerald-100 px-1.5 text-[11px] font-medium text-emerald-800">{c.where}</span>
                      {c.why && <span className="text-emerald-900">{c.why}</span>}
                    </div>
                    {c.before && <div className="mt-1 text-muted-foreground line-through decoration-red-300">{c.before}</div>}
                    <div className="mt-0.5 text-emerald-800">{c.after || "（删掉了）"}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {left > 0 && (
          <p className="text-xs text-muted-foreground">
            {tried ? "下面这些 AI 已经试着改过，但没改好——通常需要你拿主意（比如真实价格、亲身经历、要不要换说法）。可以自己改，或者在最下面补一句要求让 AI 再试。"
              : "下面这些意见还没改，点最下面的按钮让 AI 照着改。"}
          </p>
        )}
        {must.length > 0 && (
          <div>
            <div className="mb-1.5 text-xs font-medium text-red-600">{tried ? "还没改好（重要）" : "必须改"}（{must.length}）</div>
            <ul className="space-y-1.5">
              {hard.map((x) => <li key={x} className="flex gap-2 text-red-700"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{x}</li>)}
              {mustItems.map((x, k) => <ItemRow key={k} it={x} tone="red" />)}
            </ul>
          </div>
        )}
        {better.length > 0 && (
          <div>
            <div className="mb-1.5 text-xs font-medium text-amber-700">{tried ? "还没改好（不改也能发）" : "可以更好"}（{better.length}）</div>
            <ul className="space-y-1.5">
              {items ? niceItems.map((x, k) => <ItemRow key={k} it={x} tone="amber" />)
                : better.map((x) => <li key={x} className="flex gap-2 text-amber-800"><span className="shrink-0">·</span>{x}</li>)}
            </ul>
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
                {left === 0 ? "还想调？说一句要求，AI 只改相关的句子，改得更好才替换。"
                  : tried ? "补一句你的想法（比如真实价格、想怎么说），AI 照着再改；只动相关的句子，你亲手改过的不会动。"
                  : "让 AI 照上面的意见逐条改：只动被点名的句子，你亲手改过的句子不会动；改得更好才替换。"}
              </div>
              <div className="flex gap-2">
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="补充要求（可选），例如：开头更直接、再短一点"
                  className="min-w-0 flex-1 rounded-lg border bg-card px-3 py-1.5 text-sm outline-none focus:border-indigo-300" />
                <Button size="sm" variant={left === 0 ? "outline" : "gradient"} loading={revise.isPending} disabled={dirty || (left === 0 && !note.trim())}
                  title={dirty ? "先保存你的修改" : undefined}
                  onClick={() => revise.mutate(note, { onSuccess: () => setNote("") })}>
                  {!revise.isPending && <Wand2 />}{left === 0 ? "按要求改" : tried ? "让 AI 再试" : "让 AI 照着改"}
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

/** 一条质检意见：位置 + 原文 + 问题 + 改法 */
function ItemRow({ it, tone }: { it: Item; tone: "red" | "amber" }) {
  return (
    <li className={cn("rounded-lg px-3 py-2", tone === "red" ? "bg-red-50/60 text-red-800" : "bg-amber-50/60 text-amber-900")}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        {it.where && <span className={cn("shrink-0 rounded px-1.5 text-[11px] font-medium", tone === "red" ? "bg-red-100" : "bg-amber-100")}>{it.where}</span>}
        <span>{it.problem}</span>
      </div>
      {it.quote && <div className="mt-1 truncate text-xs text-muted-foreground">原文：「{it.quote}」</div>}
      {it.fix && <div className="mt-0.5 text-xs text-indigo-700">改法：{it.fix}</div>}
    </li>
  );
}
