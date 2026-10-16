import { AlertCircle, ExternalLink, KeyRound, Plus, Search, TrendingUp, Zap } from "lucide-react";
import { useState } from "react";
import type { Account, S, Topic } from "../api/client";
import { useTopicActions, useTopics, useWrite } from "../api/hooks";
import { cn, PLATFORMS } from "../lib/utils";
import { SourcesDialog } from "./SourcesDialog";
import { Badge, Button, Card, CardBody, CardHead, Empty, ErrorText, Input, Spinner } from "./ui";

const SOURCES = ["xiaohongshu", "zhihu", "baidu", "douyin", "bilibili", "weibo", "wechat"];

export function TopicsPanel({ account, busy, onGoConfig }: { account: Account; busy: boolean; onGoConfig: () => void }) {
  const { data: topics = [], isLoading } = useTopics(account.id);
  const { search, add, setStatus } = useTopicActions(account.id);
  const write = useWrite(account.id);
  const [direction, setDirection] = useState("");
  const [manual, setManual] = useState("");
  const [result, setResult] = useState<S["TopicSearchOut"] | null>(null);
  const [writingId, setWritingId] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const fresh = topics.filter((t) => t.status === "new");
  const used = topics.filter((t) => t.status === "used");
  const status = (src: string) => result?.sources.find((s) => s.source === src);

  const doSearch = (d: string) => { setDirection(d); search.mutate(d, { onSuccess: setResult }); };

  return (
    <div className="space-y-6">
      {!account.theme && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <AlertCircle className="size-5 shrink-0 text-amber-500" />
          <div className="flex-1 text-sm text-amber-800">账号主题还没设定，选题会不够精准</div>
          <Button size="sm" variant="outline" onClick={onGoConfig}>去配置</Button>
        </div>
      )}

      <Card>
        <CardHead icon={<Search />} title="搜索选题热点" desc="AI 会在各平台按关键词搜索（没配置的平台用热榜），按账号定位筛出适合的选题和切入角度"
          action={<Button size="sm" variant="ghost" onClick={() => setSourcesOpen(true)}><KeyRound />数据来源</Button>} />
        {sourcesOpen && <SourcesDialog onClose={() => setSourcesOpen(false)} />}
        <CardBody className="space-y-4">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); doSearch(direction); }}>
            <Input placeholder="输入方向或关键词，留空则按账号定位搜索…" value={direction} onChange={(e) => setDirection(e.target.value)} />
            <Button type="submit" variant="gradient" loading={search.isPending}>{!search.isPending && <Search />}搜索</Button>
          </form>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">来源平台：</span>
            {SOURCES.map((src) => {
              const st = status(src);
              return (
                <Badge key={src} className={cn("rounded-full px-2.5 py-1", PLATFORMS[src].cls,
                  st?.mode === "off" && "bg-gray-100 text-gray-400",
                  st && !st.ok && st.mode !== "off" && "bg-red-50 text-red-500 line-through")}>
                  <span title={st?.note}>
                    {PLATFORMS[src].label}{st?.ok && ` · ${st.mode === "hot" ? "热榜" : "搜索"} ${st.count}`}{st?.mode === "off" && " · 未配置"}
                  </span>
                </Badge>
              );
            })}
            {search.isPending && <span className="flex items-center gap-1 text-indigo-500"><Spinner className="size-3" />抓取并筛选中，约半分钟…</span>}
          </div>
          {result && !search.isPending && (
            <p className="text-xs text-muted-foreground">
              新增 {result.topics.length} 个选题{result.skipped_duplicates > 0 && `，已跳过 ${result.skipped_duplicates} 个和历史重复的`}{result.note && `。${result.note}`}
            </p>
          )}
          <ErrorText error={search.error} />

          <div>
            <span className="text-xs text-muted-foreground">选题类型</span>
            {account.topic_type ? (
              <div className="mt-1 flex items-center justify-between rounded-lg bg-indigo-50 px-2.5 py-1.5 text-xs font-medium text-indigo-700">
                <span>{account.topic_type}</span><span className="font-normal text-indigo-400 opacity-60">来自配置</span>
              </div>
            ) : (
              <button onClick={onGoConfig} className="mt-1 w-full cursor-pointer rounded-lg border border-dashed px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-indigo-300 hover:text-indigo-500">
                未设置 → 去「配置」Tab 和小媒对话确认
              </button>
            )}
            {account.keywords.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {account.keywords.map((k) => (
                  <button key={k} onClick={() => doSearch(k)} className="cursor-pointer rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-100">{k}</button>
                ))}
              </div>
            )}
          </div>

          <form className="flex gap-2 border-t pt-4" onSubmit={(e) => { e.preventDefault(); if (manual.trim()) add.mutate({ title: manual.trim(), angle: "" }, { onSuccess: () => setManual("") }); }}>
            <Input placeholder="自己有想法？直接加一个选题" value={manual} onChange={(e) => setManual(e.target.value)} />
            <Button type="submit" variant="outline" loading={add.isPending}><Plus />添加</Button>
          </form>
        </CardBody>
      </Card>

      <ErrorText error={write.error} />
      {isLoading ? (
        <div className="flex justify-center py-10"><Spinner className="size-6" /></div>
      ) : fresh.length === 0 ? (
        <Empty icon={<TrendingUp />} title="输入关键词，发现适合你账号的选题热点" />
      ) : (
        <div>
          <h3 className="mb-3 text-sm font-semibold">选题库（{fresh.length}）</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {fresh.map((t) => (
              <TopicCard
                key={t.id}
                topic={t}
                generating={write.isPending && writingId === t.id}
                disabled={busy}
                onSelect={() => { setWritingId(t.id); write.mutate({ topic_id: t.id, hint: "" }); }}
                onSkip={() => setStatus.mutate({ topic_id: t.id, status: "dismissed" })}
              />
            ))}
          </div>
        </div>
      )}
      {used.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">已用过的选题（{used.length}）</summary>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">{used.map((t) => <li key={t.id}>· {t.title}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

function TopicCard({ topic, onSelect, onSkip, generating, disabled }: {
  topic: Topic; onSelect: () => void; onSkip: () => void; generating: boolean; disabled: boolean;
}) {
  const p = PLATFORMS[topic.source];
  return (
    <div className="rounded-xl border-2 bg-card p-4 transition-all hover:border-indigo-300">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h4 className="flex-1 text-sm font-medium leading-snug">{topic.title}</h4>
        {p && <Badge className={p.cls}>{p.label}</Badge>}
      </div>
      {topic.angle && <p className="mb-1 text-xs leading-relaxed text-muted-foreground">{topic.angle}</p>}
      {topic.reason && <p className="mb-2 text-xs leading-relaxed text-indigo-500/80">💡 {topic.reason}</p>}
      <div className="mt-2 flex items-center justify-between">
        {topic.source_url ? (
          <a href={topic.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ExternalLink className="size-3" />原文
          </a>
        ) : <span />}
        <div className="flex gap-2">
          <Button size="xs" variant="ghost" className="text-muted-foreground" onClick={onSkip}>跳过</Button>
          <Button size="xs" variant="gradient" onClick={onSelect} loading={generating} disabled={disabled}>{!generating && <Zap />}生成图文</Button>
        </div>
      </div>
    </div>
  );
}
