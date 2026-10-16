import { AlertTriangle, ImageIcon, PenLine } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useDrafts, useWrite } from "../api/hooks";
import { cn, DRAFT_STATUS, timeAgo } from "../lib/utils";
import { Badge, Button, Card, Empty, ErrorText, Input, Spinner } from "./ui";

const FILTERS = [["all", "全部"], ["pending_review", "待审核"], ["approved", "可以发"], ["exported", "已导出"], ["rejected", "不要了"]] as const;

export function DraftsPanel({ accountId, busy }: { accountId: string; busy: boolean }) {
  const { data: drafts = [], isLoading } = useDrafts(accountId);
  const write = useWrite(accountId);
  const [filter, setFilter] = useState<string>("all");
  const [hint, setHint] = useState("");
  const shown = filter === "all" ? drafts : drafts.filter((d) => d.status === filter);

  return (
    <div className="space-y-4 p-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => { e.preventDefault(); write.mutate({ hint }, { onSuccess: () => setHint("") }); }}
      >
        <Input placeholder="有具体想法可以写在这里，留空则自动挑选题" value={hint} onChange={(e) => setHint(e.target.value)} />
        <Button type="submit" variant="primary" loading={write.isPending} disabled={busy}>
          <PenLine className="size-4" />{busy ? "正在写…" : "立即创作"}
        </Button>
      </form>
      <ErrorText error={write.error} />

      <div className="flex gap-1">
        {FILTERS.map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            className={cn("cursor-pointer rounded-full px-3 py-1 text-sm", filter === v ? "bg-ink text-white" : "text-muted hover:bg-black/5")}
          >
            {l}{v !== "all" && ` ${drafts.filter((d) => d.status === v).length}`}
          </button>
        ))}
      </div>

      {isLoading ? <Spinner /> : shown.length === 0 ? (
        <Empty title="还没有草稿" hint="点「立即创作」，或在选题里挑一个「写这个」。" />
      ) : (
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
          {shown.map((d) => {
            const st = DRAFT_STATUS[d.status];
            return (
              <Link key={d.id} to={`/drafts/${d.id}`}>
                <Card className="overflow-hidden transition-shadow hover:shadow-md">
                  <div className="flex aspect-[3/4] items-center justify-center bg-surface">
                    {d.cover_url ? <img src={d.cover_url} alt="" className="size-full object-cover" /> : <ImageIcon className="size-8 text-line" />}
                  </div>
                  <div className="space-y-1.5 p-3">
                    <div className="line-clamp-2 text-sm font-medium">{d.title}</div>
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                      <Badge tone={st.tone}>{st.label}</Badge>
                      {d.needs_attention && <Badge tone="red"><AlertTriangle className="mr-0.5 size-3" />需留意</Badge>}
                      {d.score != null && <span>{d.score.toFixed(1)} 分</span>}
                      {d.trigger === "auto" && <span>自动</span>}
                      <span className="ml-auto">{timeAgo(d.created_at)}</span>
                    </div>
                  </div>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
