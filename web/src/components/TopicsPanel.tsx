import { ExternalLink, PenLine, Plus, Search, X } from "lucide-react";
import { useState } from "react";
import type { S } from "../api/client";
import { useTopicActions, useTopics, useWrite } from "../api/hooks";
import { SOURCE_LABEL, timeAgo } from "../lib/utils";
import { Badge, Button, Card, Empty, ErrorText, Input, Spinner } from "./ui";

export function TopicsPanel({ accountId }: { accountId: string }) {
  const { data: topics = [], isLoading } = useTopics(accountId);
  const { search, add, setStatus } = useTopicActions(accountId);
  const write = useWrite(accountId);
  const [direction, setDirection] = useState("");
  const [manual, setManual] = useState("");
  const [result, setResult] = useState<S["TopicSearchOut"] | null>(null);
  const [writingId, setWritingId] = useState<string | null>(null);

  const list = topics.filter((t) => t.status === "new");
  const used = topics.filter((t) => t.status === "used");

  return (
    <div className="space-y-4 p-4">
      <Card className="space-y-3 p-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            search.mutate(direction, { onSuccess: setResult });
          }}
        >
          <Input placeholder="想往哪个方向找？留空就按账号定位找" value={direction} onChange={(e) => setDirection(e.target.value)} />
          <Button type="submit" variant="primary" loading={search.isPending}>
            {!search.isPending && <Search className="size-4" />}找选题
          </Button>
        </form>
        {search.isPending && <div className="text-sm text-muted">正在抓取微博、百度、B站、抖音热榜并筛选，大约需要半分钟…</div>}
        <ErrorText error={search.error} />
        {result && !search.isPending && (
          <div className="space-y-1 text-xs text-muted">
            <div className="flex flex-wrap gap-1.5">
              {result.sources.map((s) => (
                <Badge key={s.source} tone={s.ok ? "green" : "red"} className="cursor-help">
                  <span title={s.note}>{s.label} {s.ok ? `${s.count} 条` : "失败"}</span>
                </Badge>
              ))}
            </div>
            <div>
              新增 {result.topics.length} 个选题
              {result.skipped_duplicates > 0 && `，跳过 ${result.skipped_duplicates} 个和以前重复的`}
              {result.note && `。${result.note}`}
            </div>
          </div>
        )}
      </Card>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (manual.trim()) add.mutate({ title: manual.trim(), angle: "" }, { onSuccess: () => setManual("") });
        }}
      >
        <Input placeholder="自己有想法？直接加一个选题" value={manual} onChange={(e) => setManual(e.target.value)} />
        <Button type="submit" loading={add.isPending}><Plus className="size-4" />添加</Button>
      </form>

      {isLoading ? <Spinner /> : list.length === 0 ? (
        <Empty title="选题库是空的" hint="点「找选题」从热榜里挑，或者手动加一个。" />
      ) : (
        <div className="space-y-2">
          {list.map((t) => (
            <Card key={t.id} className="group p-3">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{t.title}</span>
                    <Badge>{SOURCE_LABEL[t.source] ?? t.source}</Badge>
                    {t.source_url && (
                      <a href={t.source_url} target="_blank" rel="noreferrer" className="text-muted hover:text-ink" aria-label="原链接">
                        <ExternalLink className="size-3.5" />
                      </a>
                    )}
                  </div>
                  {t.angle && <div className="text-sm">切入角度：{t.angle}</div>}
                  {t.reason && <div className="text-xs text-muted">{t.reason}</div>}
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    size="sm"
                    variant="primary"
                    loading={write.isPending && writingId === t.id}
                    onClick={() => { setWritingId(t.id); write.mutate({ topic_id: t.id, hint: "" }); }}
                  >
                    <PenLine className="size-3.5" />写这个
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ topic_id: t.id, status: "dismissed" })} aria-label="不要">
                    <X className="size-4" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      <ErrorText error={write.error} />
      {used.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">已写过的选题（{used.length}）</summary>
          <ul className="mt-2 space-y-1 text-muted">
            {used.map((t) => <li key={t.id}>· {t.title} <span className="text-xs">{timeAgo(t.created_at)}</span></li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
