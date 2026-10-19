import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronRight, FileText, PenLine, Sparkles, Trash2, TrendingUp } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap, type Account, type Draft } from "../api/client";
import { useDrafts, useWrite } from "../api/hooks";
import { cn, DRAFT_STATUS, timeAgo } from "../lib/utils";
import { Badge, Button, Empty, ErrorText, Input, Pills, Spinner } from "./ui";

type Filter = "all" | Draft["status"];

export function ContentsPanel({ account, busy, onGoTopics }: { account: Account; busy: boolean; onGoTopics: () => void }) {
  const accountId = account.id;
  const { data: drafts = [], isLoading } = useDrafts(accountId);
  const write = useWrite(accountId);
  const qc = useQueryClient();
  const nav = useNavigate();
  const [filter, setFilter] = useState<Filter>("all");
  const [hint, setHint] = useState("");
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const shown = filter === "all" ? drafts : drafts.filter((d) => d.status === filter);
  const count = (s: string) => drafts.filter((d) => d.status === s).length;

  const batchDelete = async () => {
    if (!confirm(`删除选中的 ${selected.size} 篇？删了找不回来。`)) return;
    setDeleting(true);
    await Promise.allSettled([...selected].map((id) => unwrap(api.DELETE("/api/drafts/{draft_id}", { params: { path: { draft_id: id } } }))));
    setDeleting(false);
    setSelecting(false);
    setSelected(new Set());
    qc.invalidateQueries({ queryKey: ["drafts", accountId] });
    qc.invalidateQueries({ queryKey: ["accounts"] });
  };
  const toggle = (id: string) => { const s = new Set(selected); s.has(id) ? s.delete(id) : s.add(id); setSelected(s); };
  const start = () => write.mutate({ hint }, { onSuccess: () => setHint("") });

  return (
    <div className="space-y-5">
      <div className="rounded-xl border-2 border-indigo-200 bg-card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium"><Sparkles className="size-4 text-indigo-500" />立即创作一篇</div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); start(); }}>
          <Input
            placeholder={account.theme ? "想写什么？比如「月薪5千怎么存钱」；留空就按账号定位挑选题" : "先在「账号设定」或跟小媒聊聊定位，写出来会更准"}
            value={hint}
            onChange={(e) => setHint(e.target.value)}
          />
          <Button type="submit" variant="gradient" loading={write.isPending} disabled={busy}>
            {!write.isPending && <PenLine />}{busy ? "正在写…" : "写一篇"}
          </Button>
        </form>
      </div>
      <ErrorText error={write.error} />

      <div className="flex items-center justify-between gap-3">
        <Pills<Filter>
          value={filter}
          onChange={setFilter}
          items={[
            { value: "all", label: `全部 ${drafts.length}` },
            ...(["pending_review", "approved", "exported", "rejected"] as const).map((s) => ({ value: s, label: `${DRAFT_STATUS[s].label} ${count(s)}` })),
          ]}
        />
        {drafts.length > 0 && (!selecting ? (
          <button className="shrink-0 whitespace-nowrap cursor-pointer text-xs text-muted-foreground hover:text-foreground" onClick={() => setSelecting(true)}>批量管理</button>
        ) : (
          <div className="flex shrink-0 items-center gap-3 text-xs">
            <button className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => setSelected(new Set(shown.map((d) => d.id)))}>全选</button>
            <button className="cursor-pointer text-muted-foreground hover:text-foreground" onClick={() => { setSelecting(false); setSelected(new Set()); }}>取消</button>
            <Button size="xs" variant="destructive" loading={deleting} disabled={!selected.size} onClick={batchDelete}><Trash2 />删除 {selected.size || ""}</Button>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner className="size-6" /></div>
      ) : shown.length === 0 ? (
        drafts.length === 0 ? (
          <Empty
            icon={<FileText />}
            title="还没有草稿"
            desc="在上面写一句想法点「写一篇」，或者先去找几个选题。写好的稿子会先放这里等你审核，不会自动发布。"
            action={<Button size="sm" variant="outline" onClick={onGoTopics}><TrendingUp />去找选题</Button>}
          />
        ) : <Empty title={`没有「${DRAFT_STATUS[filter]?.label ?? ""}」的草稿`} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {shown.map((d) => (
            <DraftRow key={d.id} d={d} selecting={selecting} selected={selected.has(d.id)}
              onClick={() => (selecting ? toggle(d.id) : nav(`/drafts/${d.id}`))} />
          ))}
        </div>
      )}
    </div>
  );
}

function DraftRow({ d, selecting, selected, onClick }: { d: Draft; selecting: boolean; selected: boolean; onClick: () => void }) {
  const s = DRAFT_STATUS[d.status];
  return (
    <div onClick={onClick} className={cn("relative flex cursor-pointer flex-col rounded-xl border bg-card p-4 transition-all hover:border-indigo-300 hover:shadow-md", selected && "ring-2 ring-indigo-400")}>
      {selecting && <input type="checkbox" readOnly checked={selected} className="absolute right-3 top-3 z-10 size-4 accent-indigo-500" />}
      <div className="mb-2 flex items-start justify-between gap-2">
        <h4 className="line-clamp-2 flex-1 text-sm font-medium leading-snug">{d.title || "无标题"}</h4>
        {!selecting && <Badge className={s.cls}>{s.label}</Badge>}
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {d.needs_attention && <Badge className="bg-amber-100 text-[10px] text-amber-700"><AlertTriangle className="size-2.5" />未达质检线</Badge>}
        {d.score != null && !d.needs_attention && <Badge className="bg-indigo-50 text-[10px] text-indigo-600">质检 {d.score.toFixed(1)}/10</Badge>}
        {d.trigger === "auto" && <Badge className="bg-purple-50 text-[10px] text-purple-600">自动运营</Badge>}
      </div>
      <div className="mb-2 flex gap-3">
        {d.cover_url ? (
          <div className="h-[75px] w-14 shrink-0 overflow-hidden rounded-lg bg-muted"><img src={d.cover_url} alt="" className="size-full object-cover" /></div>
        ) : d.images_busy > 0 && (
          <div className="flex h-[75px] w-14 shrink-0 flex-col items-center justify-center gap-1 rounded-lg bg-indigo-50 text-[10px] text-indigo-600">
            <Spinner className="size-3" />出图中<span>{d.images_done}/{d.images_total}</span>
          </div>
        )}
        <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">{d.body}</p>
      </div>
      {d.tags.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">{d.tags.slice(0, 4).map((t) => <span key={t} className="text-xs text-indigo-600">#{t}</span>)}</div>
      )}
      <div className="mt-auto flex items-center justify-between border-t pt-2 text-xs text-muted-foreground">
        <span>{timeAgo(d.created_at)}</span>
        <span className="flex items-center gap-0.5 text-indigo-600">打开<ChevronRight className="size-3.5" /></span>
      </div>
    </div>
  );
}
