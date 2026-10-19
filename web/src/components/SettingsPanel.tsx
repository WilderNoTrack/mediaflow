import { Bot, BookOpen, ListChecks, Play, Plus, Target, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Account, S } from "../api/client";
import { useNotes, useRules, useUpdateAccount, useWrite } from "../api/hooks";
import { cn, FREQ_LABEL, timeAgo } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHead, ErrorText, Input, Label, Switch, Textarea } from "./ui";

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
      <RulesCard account={account} />
      <NotesCard account={account} />
      <AutoCard account={account} busy={busy} />
    </div>
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
