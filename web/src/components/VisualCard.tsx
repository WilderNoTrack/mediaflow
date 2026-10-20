import { Check, Images, Link2, Palette, Pencil, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import type { Account, JobEvent } from "../api/client";
import { isActive, useActiveJobs, useSystem, useVisual } from "../api/hooks";
import { cn, timeAgo } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHead, ErrorText, Input, Label, Spinner, Textarea } from "./ui";

export type VisualPage = { type: string; desc?: string; when?: string; examples?: string[] };
export type Visual = {
  spec?: string; pages?: VisualPage[]; tips?: string[]; at?: string;
  source?: { kind?: string; names?: string[]; images?: number; links?: string[] };
};

const img = (rel: string) => `/files/images/${rel}`;

/** 账号配图模板：看对标账号的图学出来的「整体视觉 + 几种页型（带样例图）」。有它时每篇配图都照它出，整个账号像同一个博主做的。 */
export function VisualCard({ account }: { account: Account }) {
  const v = (account.visual ?? {}) as Visual;
  const pages = v.pages ?? [];
  const has = !!v.spec && pages.length > 0;
  const act = useVisual(account.id);
  const { data: sys } = useSystem();
  const { data: jobs = [] } = useActiveJobs(account.id);
  const job = jobs.find((j) => j.kind === "learn_visual" || (j.kind === "clone_creator" && isActive(j)));
  const learning = !!job && isActive(job) && (job.kind === "learn_visual" || (job.events as JobEvent[]).some((e) => e.stage === "visual"));
  const lastMsg = job ? (job.events as JobEvent[]).at(-1)?.message : "";
  const failed = job?.kind === "learn_visual" && job.status === "failed" ? job.error : "";
  const [links, setLinks] = useState<string | null>(null);
  const [spec, setSpec] = useState<string | null>(null);
  const hasBench = account.benchmarks.some((b) => b.status === "ready");
  const vision = sys?.vision_available !== false;

  const learn = (l = "") => act.learn.mutate(l, { onSuccess: () => setLinks(null) });
  const removePage = (t: string) => {
    if (!confirm(`删掉「${t}」这种页？以后的配图不再用它。`)) return;
    act.patch.mutate({ pages: pages.filter((p) => p.type !== t).map((p) => ({ type: p.type, desc: p.desc ?? "", when: p.when ?? "", examples: p.examples ?? [], from: "" })) });
  };
  const from = v.source?.kind === "text" ? "按你的描述起的（没有样例图，出图照文字描述做）" : v.source?.kind === "links" ? `照你给的 ${v.source.links?.length ?? 0} 篇笔记学的` : v.source?.names?.length ? `从「${v.source.names.join("」「")}」的 ${v.source.images ?? ""} 张图学的` : "";

  return (
    <Card>
      <CardHead icon={<Palette />} title="配图模板" desc="整个账号的图都照它出：统一的配色字体，再按几种固定的页型排版，每篇看起来都像同一个博主做的" />
      <CardBody className="space-y-4">
        {learning && (
          <div className="flex items-center gap-2 rounded-lg bg-indigo-50 px-3 py-2.5 text-xs text-indigo-700">
            <Spinner className="size-3" /><span className="font-medium">正在看图学配图模板</span><span className="truncate text-indigo-500">{lastMsg}</span>
          </div>
        )}
        {failed && !learning && <div className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">没学成：{failed}</div>}

        {!has ? (
          <div className="rounded-xl border border-dashed px-4 py-6 text-center">
            <Images className="mx-auto mb-2 size-8 text-muted-foreground/40" />
            <p className="text-sm">还没有配图模板，现在每篇配图照它自己的参考帖做</p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
              {vision ? "加完对标账号会自动看它的爆款图学一个；也可以现在学，或者贴几篇你喜欢的图文笔记照着学。"
                : "学模板要能看图，管理员配好 DeepSeek Key 后就能用。"}
            </p>
            {vision && !learning && (
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <Button size="sm" disabled={!hasBench} title={hasBench ? "" : "还没有学好的对标账号"} loading={act.learn.isPending && links === null} onClick={() => learn()}>
                  <Images />看对标的图学一个
                </Button>
                <Button size="sm" variant="outline" onClick={() => setLinks("")}><Link2 />照我喜欢的笔记学</Button>
              </div>
            )}
          </div>
        ) : (
          <>
            <div>
              <Label hint={[from, v.at && timeAgo(v.at)].filter(Boolean).join(" · ")}>整体视觉</Label>
              {spec !== null ? (
                <div className="space-y-2">
                  <Textarea rows={4} value={spec} onChange={(e) => setSpec(e.target.value)} />
                  <div className="flex justify-end gap-2">
                    <Button size="xs" variant="ghost" onClick={() => setSpec(null)}>取消</Button>
                    <Button size="xs" disabled={!spec.trim()} loading={act.patch.isPending} onClick={() => act.patch.mutate({ spec }, { onSuccess: () => setSpec(null) })}>保存</Button>
                  </div>
                </div>
              ) : (
                <div className="group flex items-start gap-2 rounded-lg bg-muted/50 px-3 py-2.5 text-sm leading-relaxed">
                  <p className="flex-1">{v.spec}</p>
                  <button onClick={() => setSpec(v.spec ?? "")} className="cursor-pointer rounded p-1 text-muted-foreground opacity-60 hover:bg-muted hover:opacity-100" title="改整体视觉"><Pencil className="size-3.5" /></button>
                </div>
              )}
              {!!v.tips?.length && (
                <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                  {v.tips.map((t) => <li key={t} className="flex gap-1.5"><Check className="mt-0.5 size-3 shrink-0 text-emerald-500" />{t}</li>)}
                </ul>
              )}
            </div>
            <div>
              <Label hint="出图时每张选一种，照着它的样例图排版">{pages.length} 种页型</Label>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {pages.map((p) => <PageTile key={p.type} p={p} onRemove={p.type.includes("封面") || pages.length <= 2 ? undefined : () => removePage(p.type)} />)}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t pt-3">
              {vision && hasBench && <Button size="sm" variant="outline" disabled={learning} loading={act.learn.isPending && links === null}
                onClick={() => confirm("重新看对标账号的图学一遍？现在的模板会被替换。") && learn()}><RefreshCw />重新学</Button>}
              {vision && <Button size="sm" variant="outline" disabled={learning} onClick={() => setLinks("")}><Link2 />照我喜欢的笔记学</Button>}
              <button className="ml-auto cursor-pointer text-xs text-muted-foreground hover:text-red-600"
                onClick={() => confirm("不用配图模板了？以后每篇配图照它自己的参考帖做。") && act.clear.mutate()}>不用模板</button>
            </div>
            <p className="text-xs text-muted-foreground">想改哪里直接跟小媒说，比如「封面别放人」「主色换成莫兰迪蓝」「加一种前后对比页」。改完只影响以后出的图。</p>
          </>
        )}

        {links !== null && (
          <div className="space-y-2 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3">
            <div className="text-xs font-medium">贴 1-5 篇你喜欢的小红书图文笔记（链接或整段分享文字都行），照它们的图学模板</div>
            <Input autoFocus value={links} onChange={(e) => setLinks(e.target.value)} placeholder="https://www.xiaohongshu.com/explore/…" />
            <div className="flex justify-end gap-2">
              <Button size="xs" variant="ghost" onClick={() => setLinks(null)}>取消</Button>
              <Button size="xs" disabled={!links.trim()} loading={act.learn.isPending} onClick={() => learn(links)}>开始学</Button>
            </div>
          </div>
        )}
        <ErrorText error={act.learn.error ?? act.patch.error ?? act.clear.error} />
      </CardBody>
    </Card>
  );
}

function PageTile({ p, onRemove }: { p: VisualPage; onRemove?: () => void }) {
  const ex = p.examples ?? [];
  return (
    <div className="group relative flex gap-3 rounded-lg border bg-card p-2.5">
      <div className="flex shrink-0">
        {ex.length ? ex.slice(0, 2).map((e, k) => (
          <a key={e} href={img(e)} target="_blank" rel="noreferrer" className={cn("block", k > 0 && "-ml-6")}>
            <img src={img(e)} alt="" className="h-[84px] w-[63px] rounded-md border-2 border-white object-cover shadow-sm" />
          </a>
        )) : <div className="flex h-[84px] w-[63px] items-center justify-center rounded-md bg-muted text-[10px] text-muted-foreground">无样例</div>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium">{p.type}</span>
          {p.type.includes("封面") && <Badge className="bg-indigo-50 text-indigo-600">第 1 张</Badge>}
        </div>
        {p.when && <div className="mt-0.5 text-xs text-indigo-600/80">{p.when}</div>}
        {p.desc && <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-muted-foreground" title={p.desc}>{p.desc}</p>}
      </div>
      {onRemove && (
        <button onClick={onRemove} className="absolute right-1.5 top-1.5 cursor-pointer rounded p-0.5 text-muted-foreground opacity-0 hover:bg-muted hover:text-red-600 group-hover:opacity-100" title="删掉这种页">
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}
