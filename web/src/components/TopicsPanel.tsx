import { AlertCircle, ExternalLink, Lightbulb, PenLine, Plus, Search, Sparkles, TrendingUp, X } from "lucide-react";
import { useState } from "react";
import type { Account, S, Topic } from "../api/client";
import { useIsAdmin, useTopicActions, useTopics, useWrite } from "../api/hooks";
import { cn, PLATFORMS } from "../lib/utils";
import { SourcesDialog } from "./SourcesDialog";
import { Badge, Button, Empty, ErrorText, Input, Spinner } from "./ui";

const SOURCES = ["xiaohongshu", "douyin", "bilibili", "weibo", "zhihu", "baidu", "wechat"];

export function TopicsPanel({ account, busy, onGoConfig }: { account: Account; busy: boolean; onGoConfig: () => void }) {
  const { data: topics = [], isLoading } = useTopics(account.id);
  const { search, add, setStatus } = useTopicActions(account.id);
  const write = useWrite(account.id);
  const [direction, setDirection] = useState("");
  const [manual, setManual] = useState("");
  const [result, setResult] = useState<S["TopicSearchOut"] | null>(null);
  const [writingId, setWritingId] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const admin = useIsAdmin();
  const fresh = topics.filter((t) => t.status === "new");
  const used = topics.filter((t) => t.status === "used");

  const doSearch = (d: string) => { setDirection(d); search.mutate(d, { onSuccess: setResult }); };

  return (
    <div className="space-y-5">
      {!account.theme && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          <AlertCircle className="size-4 shrink-0" />
          <span className="flex-1">账号定位还没定，找到的选题会比较泛。</span>
          <button className="cursor-pointer font-medium hover:underline" onClick={onGoConfig}>去设定</button>
        </div>
      )}

      <div className="rounded-xl border-2 border-indigo-200 bg-card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium"><Sparkles className="size-4 text-indigo-500" />智能找选题</div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); doSearch(direction); }}>
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="h-10 pl-9" placeholder="想找什么方向？留空就按账号定位找" value={direction} onChange={(e) => setDirection(e.target.value)} />
          </div>
          <Button type="submit" variant="gradient" className="h-10" loading={search.isPending}>找选题</Button>
        </form>
        {account.keywords.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">常用：</span>
            {account.keywords.map((k) => (
              <button key={k} onClick={() => doSearch(k)} className="cursor-pointer rounded-full border px-2.5 py-0.5 text-muted-foreground transition-colors hover:border-indigo-300 hover:text-indigo-600">{k}</button>
            ))}
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
          {search.isPending ? (
            <span className="flex items-center gap-1.5 text-indigo-600"><Spinner className="size-3" />正在各平台搜索并按定位筛选，大约半分钟…</span>
          ) : result ? (
            <>
              {result.sources.map((st) => (
                <span key={st.source} title={st.note} className="flex items-center gap-1">
                  <span className={cn("size-1.5 rounded-full", st.ok ? "bg-emerald-500" : st.mode === "off" ? "bg-gray-300" : "bg-red-500")} />
                  {PLATFORMS[st.source]?.label ?? st.label}
                  <span className="text-muted-foreground/70">{st.ok ? `${st.mode === "hot" ? "热榜" : ""}${st.count}` : st.mode === "off" ? "未连接" : "失败"}</span>
                </span>
              ))}
            </>
          ) : (
            <span>从 {SOURCES.map((s) => PLATFORMS[s].label).join("、")} 搜热点，再按你的定位挑出能写的角度</span>
          )}
          {admin && <button className="ml-auto cursor-pointer text-indigo-600 hover:underline" onClick={() => setSourcesOpen(true)}>连接平台</button>}
        </div>
        {result && !search.isPending && (
          <p className="mt-2 text-xs text-muted-foreground">
            新增 {result.topics.length} 个选题{result.skipped_duplicates > 0 && `，跳过 ${result.skipped_duplicates} 个和以前重复的`}{result.note && `。${result.note}`}
          </p>
        )}
        <ErrorText error={search.error} />
      </div>
      {sourcesOpen && <SourcesDialog onClose={() => setSourcesOpen(false)} />}

      <ErrorText error={write.error} />
      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="font-semibold">选题库 <span className="font-normal text-muted-foreground">{fresh.length}</span></h3>
          <span className="text-xs text-muted-foreground">挑一个点「用这个写」</span>
        </div>
        {isLoading ? (
          <div className="flex justify-center py-10"><Spinner className="size-6" /></div>
        ) : fresh.length === 0 ? (
          <Empty icon={<TrendingUp />} title="选题库是空的" desc="点上面「找选题」，或者在下面直接加一个你自己的想法。" />
        ) : (
          <div className="space-y-2">
            {fresh.map((t) => (
              <TopicRow
                key={t.id}
                topic={t}
                generating={write.isPending && writingId === t.id}
                disabled={busy}
                onSelect={() => { setWritingId(t.id); write.mutate({ topic_id: t.id, hint: "" }); }}
                onSkip={() => setStatus.mutate({ topic_id: t.id, status: "dismissed" })}
              />
            ))}
          </div>
        )}
        <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (manual.trim()) add.mutate({ title: manual.trim(), angle: "" }, { onSuccess: () => setManual("") }); }}>
          <Input className="border-dashed border-border bg-transparent" placeholder="＋ 自己加一个选题" value={manual} onChange={(e) => setManual(e.target.value)} />
          {manual.trim() && <Button type="submit" variant="outline" loading={add.isPending}><Plus />加入</Button>}
        </form>
      </div>

      {used.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-muted-foreground">写过的选题（{used.length}）</summary>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">{used.map((t) => <li key={t.id}>· {t.title}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

function TopicRow({ topic, onSelect, onSkip, generating, disabled }: {
  topic: Topic; onSelect: () => void; onSkip: () => void; generating: boolean; disabled: boolean;
}) {
  const p = PLATFORMS[topic.source];
  return (
    <div className="group flex gap-3 rounded-xl border bg-card p-4 transition-all hover:border-indigo-300 hover:shadow-md">
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-medium leading-snug">{topic.title}</h4>
          {p && <Badge className={cn("px-1.5 py-0 text-[11px]", p.cls)}>{p.label}</Badge>}
        </div>
        {topic.angle && <p className="text-xs leading-relaxed text-muted-foreground">切入：{topic.angle}</p>}
        {topic.reason && <p className="mt-0.5 flex items-start gap-1 text-xs leading-relaxed text-indigo-600/80"><Lightbulb className="mt-0.5 size-3 shrink-0" />{topic.reason}</p>}
        {typeof topic.reference?.title === "string" && (
          <p className="mt-1.5 rounded-md bg-fuchsia-50 px-2 py-1 text-xs leading-relaxed text-fuchsia-700">
            仿 {String(topic.reference.creator ?? "")} 的爆款「{topic.reference.title}」{topic.reference.likes ? ` · ${String(topic.reference.likes)}赞` : ""}
          </p>
        )}
        {topic.source_url && (
          <a href={topic.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ExternalLink className="size-3" />看原帖
          </a>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end justify-between gap-2">
        <button onClick={onSkip} title="不要这个" className="cursor-pointer rounded p-1 text-muted-foreground/50 hover:bg-muted hover:text-foreground"><X className="size-3.5" /></button>
        <Button size="sm" variant="outline" className="border-indigo-200 text-indigo-700 hover:bg-indigo-50" onClick={onSelect} loading={generating} disabled={disabled}>
          {!generating && <PenLine />}用这个写
        </Button>
      </div>
    </div>
  );
}
