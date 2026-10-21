import { Bot, BookOpen, Image as ImageIcon, ListChecks, Play, Plus, Star, Target, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import type { Account, AccountImageMode, S } from "../api/client";
import { ACCOUNT_IMAGE_MODES } from "../api/client";
import { useExemplar, useNotes, useRules, useSystem, useUpdateAccount, useWrite } from "../api/hooks";
import { cn, FREQ_LABEL, timeAgo } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHead, ErrorText, Input, Label, Switch, Textarea } from "./ui";
import { VisualCard } from "./VisualCard";

const FIELDS: { key: keyof S["AccountPatch"]; label: string; placeholder: string; rows?: number; wide?: boolean }[] = [
  { key: "name", label: "账号名称", placeholder: "例如：打工人理财笔记" },
  { key: "theme", label: "账号主题", placeholder: "这个号主要讲什么" },
  { key: "audience", label: "目标受众", placeholder: "写给谁看，比如 22-28 岁刚工作的女生" },
  { key: "topic_type", label: "选题方向", placeholder: "比如 干货清单 / 个人经历 / 测评" },
  { key: "content_style", label: "文案风格", placeholder: "比如 闺蜜聊天感，真诚不说教", rows: 2, wide: true },
  { key: "image_style", label: "配图风格", placeholder: "每篇的图怎么安排、什么视觉感觉", rows: 2, wide: true },
];
const RULE_SOURCE = { user: "手写", chat: "对话里记的", learned: "从修改里学的", benchmark: "对标" } as const;

export function SettingsPanel({ account, busy }: { account: Account; busy: boolean }) {
  return (
    <div className="space-y-5">
      <p className="rounded-xl bg-indigo-50/70 px-4 py-2.5 text-xs text-indigo-700">
        这里的内容都可以直接跟右边的小媒说，它会帮你改好；也可以在这里手动改。
      </p>
      <ProfileCard account={account} />
      <ExemplarCard account={account} />
      <ImageModeCard account={account} />
      <VisualCard account={account} />
      <RulesCard account={account} />
      <NotesCard account={account} />
      <AutoCard account={account} busy={busy} />
    </div>
  );
}

type ExemplarInfo = { draft_id?: string; title?: string; images?: number; cover?: string; at?: string };

/** 样板帖：用户打磨定稿的一篇，之后每篇都照它的写法和配图 */
function ExemplarCard({ account }: { account: Account }) {
  const ex = useExemplar(account.id);
  const cur = (account.exemplar ?? {}) as ExemplarInfo;
  return (
    <Card>
      <CardHead icon={<Star />} title="样板帖" desc="你打磨满意的一篇；之后每篇都照它的写法、配图做法和版式来，对标爆款只当选题和内容参考" />
      <CardBody>
        {cur.draft_id ? (
          <div className="flex items-center gap-3">
            {cur.cover
              ? <img src={`/files/images/${cur.cover}`} alt="" className="h-16 w-12 shrink-0 rounded-md border object-cover" />
              : <div className="flex h-16 w-12 shrink-0 items-center justify-center rounded-md bg-amber-50"><Star className="size-4 text-amber-500" /></div>}
            <div className="min-w-0 flex-1 text-sm">
              <Link to={`/drafts/${cur.draft_id}`} className="line-clamp-2 font-medium hover:text-indigo-600">{cur.title}</Link>
              <div className="mt-0.5 text-xs text-muted-foreground">{cur.images ? `${cur.images} 张图` : "还没有出好的图"}{cur.at ? ` · ${timeAgo(cur.at)}定的` : ""}</div>
            </div>
            <Button size="xs" variant="ghost" loading={ex.isPending} onClick={() => confirm("取消样板帖？之后写稿按对标爆款和账号设定来。") && ex.mutate(null)}>取消</Button>
          </div>
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">
            还没有。先跟小媒说想做什么，它会找几篇同领域的爆款给你挑，照着写出第一篇；改到满意后在草稿页点「定为样板帖」，或者直接跟小媒说「就按这篇来」。
          </p>
        )}
        <ErrorText error={ex.error} />
      </CardBody>
    </Card>
  );
}

/** 配图默认怎么做：AI 画 / AI 画面 + 代码排字 / 排版卡片 / 网上找图 / 自动，点一下就存 */
function ImageModeCard({ account }: { account: Account }) {
  const update = useUpdateAccount(account.id);
  const { data: sys } = useSystem();
  const cur = (account.image_mode || "ai") as AccountImageMode;
  const pending = update.isPending ? (update.variables?.image_mode as AccountImageMode | undefined) : undefined;
  const shown = pending ?? cur;
  const m = ACCOUNT_IMAGE_MODES.find((x) => x.value === shown);
  return (
    <Card>
      <CardHead icon={<ImageIcon />} title="配图怎么做" desc="每篇配图默认的做法；草稿页里每张也能单独换" />
      <CardBody className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {ACCOUNT_IMAGE_MODES.map((x) => (
            <button key={x.value} disabled={update.isPending} onClick={() => x.value !== cur && update.mutate({ image_mode: x.value })}
              className={cn("cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-all disabled:cursor-wait",
                x.value === shown ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
              {x.label}
            </button>
          ))}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">{m?.desc}</p>
        {m?.ai && sys && !sys.image_configured && (
          <p className="text-xs text-amber-600">还没配置 AI 配图（生图 Key），配好之前要 AI 画的会跳过或改成排版卡片；「排版卡片」「网上找图」不用 Key。</p>
        )}
        <ErrorText error={update.error} />
      </CardBody>
    </Card>
  );
}

function ProfileCard({ account }: { account: Account }) {
  const update = useUpdateAccount(account.id);
  const [form, setForm] = useState<Record<string, string>>({});
  const [keywords, setKeywords] = useState("");
  const reset = () => {
    setForm(Object.fromEntries(FIELDS.map((f) => [f.key, String(account[f.key as keyof Account] ?? "")])));
    setKeywords(account.keywords.join("，"));
  };
  // 只在定位字段本身变化时（保存后、小媒改了设定）同步表单，不覆盖正在编辑的内容
  const profileKey = JSON.stringify([...FIELDS.map((f) => account[f.key as keyof Account]), account.keywords]);
  useEffect(reset, [profileKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const kwList = keywords.split(/[,，、\s]+/).map((k) => k.trim()).filter(Boolean);
  const dirty = FIELDS.some((f) => (form[f.key] ?? "") !== String(account[f.key as keyof Account] ?? "")) || kwList.join(",") !== account.keywords.join(",");
  const filled = FIELDS.filter((f) => String(account[f.key as keyof Account] ?? "").trim()).length;

  return (
    <Card>
      <CardHead icon={<Target />} title="账号定位" desc="写稿、打分、找选题都按这里来"
        action={<span className="text-xs text-muted-foreground">已填 {filled}/{FIELDS.length}</span>} />
      <CardBody>
        <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
          {FIELDS.map((f) => (
            <div key={f.key} className={cn(f.wide && "sm:col-span-2")}>
              <Label>{f.label}</Label>
              {f.rows ? (
                <Textarea rows={f.rows} placeholder={f.placeholder} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
              ) : (
                <Input placeholder={f.placeholder} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
              )}
            </div>
          ))}
          <div className="sm:col-span-2">
            <Label hint="找选题时会用这些词去各平台搜">关键词</Label>
            <Input placeholder="用逗号隔开，比如 存钱，基金，记账" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
          </div>
        </div>
        <ErrorText error={update.error} />
        {dirty && (
          <div className="mt-4 flex items-center justify-end gap-2 border-t pt-3">
            <span className="mr-auto text-xs text-amber-600">有改动还没保存</span>
            <Button size="sm" variant="ghost" onClick={reset}>撤销</Button>
            <Button size="sm" loading={update.isPending} onClick={() => update.mutate({ ...form, keywords: kwList })}>保存</Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function RulesCard({ account }: { account: Account }) {
  const { add, remove } = useRules(account.id);
  const [rule, setRule] = useState("");
  return (
    <Card>
      <CardHead icon={<ListChecks />} title="文案要求" desc="每篇写稿和打分都会逐条检查" />
      <CardBody className="space-y-1.5">
        {account.rules.length === 0 && <p className="pb-1 text-xs text-muted-foreground">还没有。比如「结尾带一个互动提问」「不推荐具体理财产品」。</p>}
        {account.rules.map((r, i) => (
          <div key={r.id} className="group flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-muted/60">
            <span className="w-4 text-xs text-muted-foreground">{i + 1}</span>
            <span className="flex-1">{r.text}</span>
            <Badge className={r.source === "learned" ? "bg-purple-50 text-purple-600" : r.source === "benchmark" ? "bg-fuchsia-50 text-fuchsia-600" : "bg-gray-100 text-gray-500"}>{RULE_SOURCE[r.source]}</Badge>
            <button onClick={() => remove.mutate(r.id)} className="cursor-pointer text-muted-foreground opacity-0 hover:text-red-600 group-hover:opacity-100" aria-label="删除">
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
        <form className="flex gap-2 pt-2" onSubmit={(e) => { e.preventDefault(); if (rule.trim()) add.mutate({ text: rule.trim(), source: "user" }, { onSuccess: () => setRule("") }); }}>
          <Input placeholder="加一条要求" value={rule} onChange={(e) => setRule(e.target.value)} />
          <Button type="submit" variant="outline" disabled={!rule.trim()} loading={add.isPending}><Plus />添加</Button>
        </form>
      </CardBody>
    </Card>
  );
}

function NotesCard({ account }: { account: Account }) {
  const removeNote = useNotes(account.id);
  return (
    <Card>
      <CardHead icon={<BookOpen />} title="运营笔记" desc="小媒调研后存下的结论，写稿和找选题时参考最近 5 条" />
      <CardBody className="space-y-1.5">
        {account.notes.length === 0 ? (
          <p className="text-xs text-muted-foreground">还没有。跟小媒说「帮我分析一下某某博主」，分析完会自动存一份要点。</p>
        ) : account.notes.map((n, i) => (
          <details key={n.id} className="group rounded-lg border px-3 py-2 text-sm" open={i === 0}>
            <summary className="flex cursor-pointer list-none items-center gap-2">
              <span className="flex-1 font-medium">{n.title}</span>
              <span className="text-xs text-muted-foreground">{timeAgo(n.created_at)}</span>
              <button
                onClick={(e) => { e.preventDefault(); if (confirm(`删除笔记「${n.title}」？`)) removeNote.mutate(n.id); }}
                className="cursor-pointer text-muted-foreground opacity-0 hover:text-red-600 group-hover:opacity-100"
                aria-label="删除笔记"
              ><Trash2 className="size-3.5" /></button>
            </summary>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{n.content}</p>
          </details>
        ))}
      </CardBody>
    </Card>
  );
}

function AutoCard({ account, busy }: { account: Account; busy: boolean }) {
  const update = useUpdateAccount(account.id);
  const write = useWrite(account.id);
  return (
    <Card>
      <CardHead icon={<Bot />} title="自动运营" desc="按频率自动找选题、写稿，放进「待审核」；不会自动发布"
        action={<Switch checked={account.auto_enabled} disabled={update.isPending} onChange={(v) => update.mutate({ auto_enabled: v })} />} />
      <CardBody className="flex flex-wrap items-center gap-3 text-sm">
        {account.auto_enabled ? <>
          <span className="text-xs text-muted-foreground">频率</span>
          <div className="flex gap-1">
            {Object.entries(FREQ_LABEL).map(([v, l]) => (
              <button
                key={v}
                onClick={() => update.mutate({ auto_frequency: v as S["AutoFrequency"] })}
                className={cn("cursor-pointer rounded-md border px-3 py-1 text-xs font-medium transition-colors",
                  account.auto_frequency === v ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "hover:bg-accent")}
              >{l}</button>
            ))}
          </div>
          {account.last_auto_run_at && <span className="text-xs text-muted-foreground">上次：{timeAgo(account.last_auto_run_at)}</span>}
        </> : <span className="text-xs text-muted-foreground">已关闭</span>}
        <Button size="sm" variant="outline" className="ml-auto" loading={write.isPending} disabled={busy} onClick={() => write.mutate({ hint: "" })}>
          {!write.isPending && <Play />}{busy ? "正在写…" : "现在跑一次"}
        </Button>
        <ErrorText error={write.error} />
      </CardBody>
    </Card>
  );
}
