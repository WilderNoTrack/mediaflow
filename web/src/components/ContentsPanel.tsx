import { AlertTriangle, Edit, FileText, Sparkles, Trash2, TrendingUp, Zap } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Draft } from "../api/client";
import { useDrafts, useWrite } from "../api/hooks";
import { cn, dateStr, DRAFT_STATUS } from "../lib/utils";
import { Badge, Button, Empty, ErrorText, Input, Spinner } from "./ui";

const FILTERS = [["all", "全部"], ["pending_review", "待审核"], ["approved", "可以发"], ["exported", "已导出"], ["rejected", "不要了"]] as const;

export function ContentsPanel({ accountId, busy, onGoTopics }: { accountId: string; busy: boolean; onGoTopics: () => void }) {
  const { data: drafts = [], isLoading } = useDrafts(accountId);
  const write = useWrite(accountId);
  const qc = useQueryClient();
  const nav = useNavigate();
  const [filter, setFilter] = useState<string>("all");
  const [hint, setHint] = useState("");
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const shown = filter === "all" ? drafts : drafts.filter((d) => d.status === filter);

  const batchDelete = async () => {
    if (!confirm(`删除选中的 ${selected.size} 篇？`)) return;
    setDeleting(true);
    await Promise.allSettled([...selected].map((id) => unwrap(api.DELETE("/api/drafts/{draft_id}", { params: { path: { draft_id: id } } }))));
    setDeleting(false);
    setSelecting(false);
    setSelected(new Set());
    qc.invalidateQueries({ queryKey: ["drafts", accountId] });
    qc.invalidateQueries({ queryKey: ["accounts"] });
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border-2 border-indigo-200 bg-card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium"><Sparkles className="size-4 text-indigo-500" />立即创作一篇</div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); write.mutate({ hint }, { onSuccess: () => setHint("") }); }}>
          <Input placeholder="有具体想法写在这里；留空则 AI 按账号定位自动挑选题" value={hint} onChange={(e) => setHint(e.target.value)} />
          <Button type="submit" variant="gradient" loading={write.isPending} disabled={busy}>
            {!write.isPending && <Zap />}{busy ? "创作中…" : "生成图文"}
          </Button>
        </form>
        <ErrorText error={write.error} />
      </div>

      <div className="flex items-center justify-between">
        <h2 className="font-semibold">内容草稿</h2>
        {!selecting ? (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="danger-outline" onClick={() => setSelecting(true)} disabled={!drafts.length}><Trash2 className="size-3.5" />批量删除</Button>
            <Button size="sm" variant="outline" onClick={onGoTopics}><Sparkles className="size-3.5" />去选题生成</Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button className="cursor-pointer text-xs text-muted-foreground hover:text-foreground" onClick={() => setSelected(new Set(shown.map((d) => d.id)))}>全选</button>
            <Button size="sm" variant="destructive" loading={deleting} disabled={!selected.size} onClick={batchDelete}>
              <Trash2 className="size-3.5" />{selected.size ? `删除 ${selected.size} 篇` : "删除"}
            </Button>
            <button className="cursor-pointer text-xs text-muted-foreground hover:text-foreground" onClick={() => { setSelecting(false); setSelected(new Set()); }}>取消</button>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            className={cn("cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition-all",
              filter === v ? "bg-indigo-100 text-indigo-700" : "text-muted-foreground hover:bg-muted")}
          >
            {l}{v !== "all" && ` ${drafts.filter((d) => d.status === v).length}`}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner className="size-6" /></div>
      ) : shown.length === 0 ? (
        <Empty icon={<FileText />} title="还没有内容" action={<Button size="sm" onClick={onGoTopics}><TrendingUp className="size-3.5" />去选题</Button>} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {shown.map((d) => (
            <div key={d.id} className={cn("relative rounded-xl transition-all", selecting && selected.has(d.id) && "ring-2 ring-indigo-400")}>
              {selecting && (
                <input
                  type="checkbox"
                  checked={selected.has(d.id)}
                  onChange={() => { const s = new Set(selected); s.has(d.id) ? s.delete(d.id) : s.add(d.id); setSelected(s); }}
                  className="absolute right-3 top-3 z-10 size-4 cursor-pointer accent-indigo-500"
                />
              )}
              <ContentCard d={d} onOpen={() => (selecting ? undefined : nav(`/drafts/${d.id}`))} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ContentCard({ d, onOpen }: { d: Draft; onOpen: () => void }) {
  const s = DRAFT_STATUS[d.status];
  return (
    <div onClick={onOpen} className="cursor-pointer rounded-xl border bg-card p-4 transition-all hover:border-indigo-300 hover:shadow-md">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h4 className="line-clamp-2 flex-1 text-sm font-medium leading-snug">{d.title || "无标题"}</h4>
        <Badge className={s.cls}>{s.label}</Badge>
      </div>
      {(d.needs_attention || d.score != null || d.trigger === "auto") && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          {d.needs_attention && <Badge className="bg-amber-100 text-[10px] text-amber-700"><AlertTriangle className="size-2.5" />未达质检线</Badge>}
          {d.score != null && !d.needs_attention && <Badge className="bg-indigo-50 text-[10px] text-indigo-600">质检 {d.score.toFixed(1)}/10</Badge>}
          {d.trigger === "auto" && <Badge className="bg-purple-50 text-[10px] text-purple-600">自动运营</Badge>}
        </div>
      )}
      {d.cover_url && (
        <div className="mb-3 h-[75px] w-14 overflow-hidden rounded-lg bg-muted">
          <img src={d.cover_url} alt="" className="size-full object-cover" />
        </div>
      )}
      <p className="mb-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">{d.body}</p>
      {d.tags.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {d.tags.slice(0, 4).map((t) => <span key={t} className="text-xs text-indigo-600">#{t}</span>)}
        </div>
      )}
      <div className="flex items-center justify-between border-t pt-2">
        <span className="text-xs text-muted-foreground">{dateStr(d.created_at)}</span>
        <Button size="xs" variant="outline"><Edit />编辑</Button>
      </div>
    </div>
  );
}
