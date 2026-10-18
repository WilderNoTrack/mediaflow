import { Check, ExternalLink, Flame, Wand2 } from "lucide-react";
import { useState } from "react";
import type { Account, Candidate } from "../api/client";
import { useClone } from "../api/hooks";
import { cn } from "../lib/utils";
import { Avatar, Badge, Button, ErrorText } from "./ui";

export const MAX_BENCH = 3;

const fmt = (n?: number) => (n == null ? "" : n >= 10000 ? `${(n / 10000).toFixed(1)}万` : String(n));
const uid = (u: string) => u.match(/\/user\/profile\/([0-9a-zA-Z]{16,32})/)?.[1] ?? "";

/** 已经在对标的账号（按主页 ID 或名字认） */
export function isBenchmarked(account: Account, c: Pick<Candidate, "name" | "url">) {
  const id = uid(c.url);
  return account.benchmarks.some((b) => b.creator_name === c.name || (id && (uid(b.creator_url) === id || uid(b.target) === id)));
}

/** 对标候选卡片：勾选 1-3 个，点「学习选中的」开始拆解。工作台「对标」页和小媒对话里共用。 */
export function CandidatePicker({ account, candidates, compact, onStarted }: {
  account: Account; candidates: Candidate[]; compact?: boolean; onStarted?: () => void;
}) {
  const clone = useClone(account.id);
  const [picked, setPicked] = useState<string[]>([]);
  const [started, setStarted] = useState<string[]>([]);
  const slots = MAX_BENCH - account.benchmarks.filter((b) => b.status !== "failed").length;
  const toggle = (url: string) =>
    setPicked((p) => (p.includes(url) ? p.filter((x) => x !== url) : p.length >= slots ? p : [...p, url]));

  if (!candidates.length) return <p className="text-sm text-muted-foreground">这次没找到合适的同领域账号，换个说法或说说要求再找一次。</p>;
  return (
    <div className="min-w-0 space-y-3">
      <div className={cn("grid grid-cols-1 gap-3", !compact && "sm:grid-cols-2")}>
        {candidates.map((c) => {
          const done = started.includes(c.url) || isBenchmarked(account, c);
          const on = picked.includes(c.url);
          const full = !on && picked.length >= slots;
          return (
            <div key={c.url} onClick={() => !done && toggle(c.url)}
              className={cn("relative flex min-w-0 cursor-pointer flex-col rounded-xl border-2 bg-card p-4 transition-all",
                done ? "cursor-default opacity-70" : on ? "border-indigo-400 shadow-md ring-2 ring-indigo-100" : "hover:border-indigo-300 hover:shadow-md",
                full && !done && "opacity-60")}>
              <div className="mb-2 flex items-center gap-3">
                {c.avatar ? <img src={c.avatar} alt="" referrerPolicy="no-referrer" className="size-10 shrink-0 rounded-full object-cover" />
                  : <Avatar name={c.name} size="sm" />}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate font-medium">{c.name}</span>
                    {c.level && <Badge className="shrink-0 bg-indigo-50 text-[10px] text-indigo-600">{c.level}</Badge>}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {[c.fans && `${c.fans} 粉`, c.median_likes != null && `中位赞 ${fmt(c.median_likes)}`,
                      c.hit_rate != null && `爆款率 ${Math.round(c.hit_rate * 100)}%`, c.per_week && `周更 ${c.per_week}`].filter(Boolean).join(" · ")}
                  </div>
                </div>
                {done ? <Badge className="shrink-0 bg-emerald-50 text-emerald-600"><Check className="size-3" />在学了</Badge> : (
                  <span className={cn("flex size-5 shrink-0 items-center justify-center rounded-md border-2",
                    on ? "border-indigo-500 bg-indigo-500 text-white" : "border-gray-300")}>{on && <Check className="size-3" />}</span>
                )}
              </div>
              {c.reason && <p className="mb-2 text-xs leading-relaxed text-indigo-600">💡 {c.reason}</p>}
              {c.learn && <div className="mb-2"><span className="rounded bg-fuchsia-50 px-1.5 py-0.5 text-xs text-fuchsia-700">最该学：{c.learn}</span></div>}
              <div className="mt-auto space-y-1">
                {(c.top?.length ? c.top : c.hits ?? []).slice(0, compact ? 2 : 3).map((h) => (
                  <a key={h.url || h.title} href={h.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                    className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                    <Flame className="size-3 shrink-0 text-orange-400" /><span className="truncate">{h.title}</span>
                    {h.likes && <span className="shrink-0 text-muted-foreground/70">{h.likes}赞</span>}
                  </a>
                ))}
              </div>
              <a href={c.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                className="mt-2 flex items-center gap-1 border-t pt-2 text-xs text-muted-foreground hover:text-foreground">
                <ExternalLink className="size-3" />看主页{c.last_post && <span className="ml-auto">最近更新 {c.last_post}</span>}
              </a>
            </div>
          );
        })}
      </div>
      <ErrorText error={clone.error} />
      <div className={cn("flex items-center gap-3", compact && "flex-col items-stretch gap-2")}>
        <span className="text-xs text-muted-foreground">
          {slots <= 0 ? `已经对标 ${MAX_BENCH} 个了，先在「对标」页删掉一个` : `已选 ${picked.length}，这次最多选 ${slots} 个`}
        </span>
        <Button variant="gradient" className={cn(!compact && "ml-auto")} disabled={!picked.length} loading={clone.isPending}
          onClick={() => clone.mutate({ targets: picked, names: picked.map((u) => candidates.find((c) => c.url === u)?.name ?? "") }, { onSuccess: () => { setStarted((s) => [...s, ...picked]); setPicked([]); onStarted?.(); } })}>
          {!clone.isPending && <Wand2 />}学习选中的{picked.length ? ` ${picked.length} 个` : ""}
        </Button>
      </div>
    </div>
  );
}
