import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Account, S } from "../api/client";
import { useRules, useUpdateAccount } from "../api/hooks";
import { FREQ_LABEL, timeAgo } from "../lib/utils";
import { Badge, Button, Card, ErrorText, Field, Input, Textarea } from "./ui";

const FIELDS: { key: keyof S["AccountPatch"]; label: string; hint: string; long?: boolean }[] = [
  { key: "name", label: "账号名", hint: "" },
  { key: "theme", label: "主题定位", hint: "这个号主要讲什么，例如「职场新人的理财入门」", long: true },
  { key: "audience", label: "目标人群", hint: "写给谁看，越具体越好", long: true },
  { key: "content_style", label: "内容风格", hint: "语气、结构、长短，例如「闺蜜聊天口吻，多用清单」", long: true },
  { key: "image_style", label: "配图风格", hint: "例如「ins 风浅色调，手绘插画」", long: true },
  { key: "topic_type", label: "选题偏好", hint: "例如「干货教程为主，偶尔追热点」" },
];

const RULE_SOURCE = { user: "手写", chat: "对话", learned: "学到的" } as const;

export function ProfilePanel({ account }: { account: Account }) {
  const update = useUpdateAccount(account.id);
  const { add, remove } = useRules(account.id);
  const [form, setForm] = useState<Record<string, string>>({});
  const [keywords, setKeywords] = useState("");
  const [rule, setRule] = useState("");

  useEffect(() => {
    setForm(Object.fromEntries(FIELDS.map((f) => [f.key, String(account[f.key as keyof Account] ?? "")])));
    setKeywords(account.keywords.join("，"));
  }, [account]);

  const dirty =
    FIELDS.some((f) => form[f.key] !== String(account[f.key as keyof Account] ?? "")) ||
    keywords !== account.keywords.join("，");

  const save = () =>
    update.mutate({
      ...form,
      keywords: keywords.split(/[,，、\s]+/).map((k) => k.trim()).filter(Boolean),
    });

  return (
    <div className="space-y-4 p-4">
      <Card className="space-y-4 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">账号定位</div>
            <div className="text-xs text-muted">也可以直接在左边和管家聊，它会帮你填</div>
          </div>
          <Button variant="primary" size="sm" disabled={!dirty} loading={update.isPending} onClick={save}>保存</Button>
        </div>
        {FIELDS.map((f) => (
          <Field key={f.key} label={f.label} hint={f.hint || undefined}>
            {f.long ? (
              <Textarea rows={2} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            ) : (
              <Input value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            )}
          </Field>
        ))}
        <Field label="关键词" hint="用逗号分隔，找热点时会用到">
          <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        </Field>
        <ErrorText error={update.error} />
      </Card>

      <Card className="space-y-3 p-4">
        <div>
          <div className="font-medium">写作规矩</div>
          <div className="text-xs text-muted">每次写稿和评审都会严格遵守</div>
        </div>
        {account.rules.length === 0 && <div className="text-sm text-muted">还没有规矩。比如「不提具体品牌」「结尾带一个互动提问」。</div>}
        <ul className="space-y-1.5">
          {account.rules.map((r) => (
            <li key={r.id} className="group flex items-start gap-2 rounded-lg bg-surface px-3 py-2 text-sm">
              <span className="flex-1">{r.text}</span>
              <Badge tone={r.source === "learned" ? "brand" : "gray"}>{RULE_SOURCE[r.source]}</Badge>
              <button onClick={() => remove.mutate(r.id)} className="cursor-pointer text-muted opacity-0 group-hover:opacity-100 hover:text-red-600" aria-label="删除规矩">
                <Trash2 className="size-4" />
              </button>
            </li>
          ))}
        </ul>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (rule.trim()) add.mutate({ text: rule.trim(), source: "user" }, { onSuccess: () => setRule("") });
          }}
        >
          <Input placeholder="加一条规矩…" value={rule} onChange={(e) => setRule(e.target.value)} />
          <Button type="submit" loading={add.isPending}>添加</Button>
        </form>
      </Card>

      <Card className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">自动模式</div>
            <div className="text-xs text-muted">按频率自动找选题并写稿，写好放进「待审核」，不会自动发布</div>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-brand"
              checked={account.auto_enabled}
              onChange={(e) => update.mutate({ auto_enabled: e.target.checked })}
            />
            {account.auto_enabled ? "已开启" : "已关闭"}
          </label>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted">频率</span>
          <select
            className="h-8 rounded-lg border border-line bg-white px-2"
            value={account.auto_frequency}
            onChange={(e) => update.mutate({ auto_frequency: e.target.value as S["AutoFrequency"] })}
          >
            {Object.entries(FREQ_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {account.last_auto_run_at && <span className="text-muted">上次运行 {timeAgo(account.last_auto_run_at)}</span>}
        </div>
      </Card>
    </div>
  );
}
