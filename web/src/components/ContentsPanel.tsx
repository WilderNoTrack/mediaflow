import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronRight, FileText, ImageIcon, PenLine, Trash2, TrendingUp } from "lucide-react";
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
      <form className="flex gap-2 rounded-xl border bg-card p-2 shadow-sm" onSubmit={(e) => { e.preventDefault(); start(); }}>
        <Input
          className="border-0 bg-transparent focus-visible:ring-0"
          placeholder={account.theme ? "想写什么？比如「月薪5千怎么存钱」；留空就按账号定位挑选题" : "先在「账号设定」或跟小媒聊聊定位，写出来会更准"}
          value={hint}
          onChange={(e) => setHint(e.target.value)}
        />
        <Button type="submit" variant="gradient" loading={write.isPending} disabled={busy}>
          {!write.isPending && <PenLine />}{busy ? "正在写…" : "写一篇"}
        </Button>
      </form>
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
        <div className="divide-y overflow-hidden rounded-xl border bg-card">
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
    <div onClick={onClick} className={cn("group flex cursor-pointer items-center gap-4 px-4 py-3.5 transition-colors hover:bg-slate-50", selected && "bg-indigo-50/60")}>
      {selecting && <input type="checkbox" readOnly checked={selected} className="size-4 shrink-0 accent-indigo-500" />}
      <div className="flex h-[72px] w-[54px] shrink-0 items-center justify-center overflow-hidden rounded-lg bg-muted">
        {d.cover_url ? <img src={d.cover_url} alt="" className="size-full object-cover" /> : <ImageIcon className="size-5 text-muted-foreground/40" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <h4 className="truncate text-sm font-medium">{d.title || "无标题"}</h4>
        </div>
        <p className="mb-1.5 line-clamp-1 text-xs text-muted-foreground">{d.body}</p>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <Badge className={cn("px-1.5 py-0 text-[11px]", s.cls)}>{s.label}</Badge>
          {d.needs_attention
            ? <span className="flex items-center gap-0.5 text-amber-600"><AlertTriangle className="size-3" />没过质检线</span>
            : d.score != null && <span>质检 {d.score.toFixed(1)}</span>}
          {d.trigger === "auto" && <span>· 自动运营</span>}
          <span>· {timeAgo(d.created_at)}</span>
        </div>
      </div>
      {!selecting && <ChevronRight className="size-4 shrink-0 text-muted-foreground/50 group-hover:text-muted-foreground" />}
    </div>
  );
}
