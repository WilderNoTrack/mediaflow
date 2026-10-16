import { Bot, Lightbulb, MessageCircle, Play, Save, Send, Settings, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Account, S } from "../api/client";
import { useChat, useNotes, useRules, useSendChat, useUpdateAccount, useWrite } from "../api/hooks";
import { cn, FREQ_LABEL, timeAgo } from "../lib/utils";
import { Badge, Button, ErrorText, Input, Label, Logo, Spinner, Switch, Textarea } from "./ui";

const TOOL_META: Record<string, { icon: string; label: string }> = {
  update_profile: { icon: "✏️", label: "更新账号配置" },
  add_rule: { icon: "📌", label: "记下规矩" },
  remove_rule: { icon: "🗑", label: "停用规矩" },
  list_drafts: { icon: "🗂", label: "查看最近内容" },
  find_topics: { icon: "🔍", label: "搜索热点选题" },
  write_post: { icon: "🚀", label: "执行内容创作" },
  set_auto: { icon: "⏰", label: "设置自动运营" },
  research_search: { icon: "🌐", label: "搜各平台内容" },
  research_creators: { icon: "👤", label: "搜博主" },
  research_creator_posts: { icon: "📚", label: "看博主作品" },
  research_post: { icon: "📄", label: "看作品详情" },
  save_note: { icon: "📝", label: "存运营笔记" },
  remove_note: { icon: "🗑", label: "删运营笔记" },
};

const PLATFORM_LABEL: Record<string, string> = {
  xiaohongshu: "小红书", douyin: "抖音", bilibili: "B站", weibo: "微博", wechat: "公众号", zhihu: "知乎", baidu: "百度",
};

/** 工具记录的一行摘要：调研类显示查了什么（参数），出错显示错误，其余显示结果 JSON。 */
function toolSummary(m: { tool_name: string; content: string; payload: Record<string, unknown> }) {
  const args = (m.payload?.args ?? {}) as Record<string, string>;
  const result = (m.payload?.result ?? {}) as Record<string, unknown>;
  if (result.ok === false) return `失败：${String(result.error ?? "")}`;
  if (m.tool_name.startsWith("research_")) {
    const what = [PLATFORM_LABEL[args.platform] ?? args.platform, args.keyword ?? args.name, args.creator_ref ?? args.post_ref]
      .filter(Boolean).join(" · ");
    const n = Array.isArray(result.items) ? result.items.length : Array.isArray(result.creators) ? result.creators.length
      : Array.isArray(result.posts) ? result.posts.length : 0;
    const title = typeof result.title === "string" ? `「${result.title}」` : "";
    return `${what}${n ? `（${n} 条）` : ""}${title}`;
  }
  if (m.tool_name === "save_note") return String(args.title ?? "");
  return m.content;
}

export function ConfigPanel({ account, busy }: { account: Account; busy: boolean }) {
  return (
    <div className="space-y-8">
      <div className="grid gap-6 lg:grid-cols-2">
        <ChatBox account={account} />
        <ProfileForm account={account} />
      </div>
      <AutoPanel account={account} busy={busy} />
    </div>
  );
}

function ChatBox({ account }: { account: Account }) {
  const { data: msgs = [], isLoading } = useChat(account.id);
  const send = useSendChat(account.id);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [msgs.length, pending]);

  const submit = (t = text) => {
    const v = t.trim();
    if (!v || send.isPending) return;
    setPending(v);
    setText("");
    send.mutate(v, { onSettled: () => setPending(null) });
  };

  const welcome = `你好！我是小媒 🌀 「${account.name}」的账号管家。\n\n直接跟我聊就行——比如「我想做一个职场新人理财账号」，我会边聊边帮你把定位配置好；配置差不多了说一句「写一篇试试」，我就直接帮你创作。\n\n想找对标也可以问我，比如「帮我分析一下小红书博主程十安」，我会去看 TA 的爆款和评论区。\n\n这个账号想做什么方向？`;

  return (
    <div className="flex flex-col">
      <div className="mb-3 flex items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-lg font-semibold"><MessageCircle className="size-4 text-indigo-500" />账号管家小媒</h3>
        <span className="text-xs text-muted-foreground">聊定位 · 改配置 · 找选题 · 写稿，都在这</span>
      </div>
      <div className="flex h-[560px] flex-col overflow-hidden rounded-xl border-2 bg-card">
        <div ref={box} className="flex-1 space-y-3 overflow-y-auto bg-slate-50/50 p-4">
          {isLoading && <Spinner />}
          {!isLoading && msgs.length === 0 && <Bubble role="assistant" text={welcome} />}
          {msgs.map((m) =>
            m.role === "tool" ? (
              <div key={m.id} className="ml-10 flex items-center gap-1.5 rounded-lg border border-indigo-100 bg-indigo-50/60 px-2.5 py-1.5 text-xs text-indigo-700">
                <span>{TOOL_META[m.tool_name]?.icon ?? "🔧"}</span>
                <span className="font-medium">{TOOL_META[m.tool_name]?.label ?? m.tool_name}</span>
                <span className="truncate text-indigo-500/80">{toolSummary(m)}</span>
              </div>
            ) : <Bubble key={m.id} role={m.role} text={m.content} />,
          )}
          {pending && <>
            <Bubble role="user" text={pending} />
            <div className="ml-10 flex items-center gap-2 text-xs text-muted-foreground"><Spinner className="size-3" />小媒思考中…</div>
          </>}
          <ErrorText error={send.error} />
        </div>
        <div className="flex gap-2 border-t bg-card p-3">
          <Input
            value={text}
            placeholder="聊定位、改配置、或说「写一篇试试」…"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
          />
          <Button variant="gradient" size="md" className="px-3" onClick={() => submit()} loading={send.isPending} aria-label="发送">
            {!send.isPending && <Send />}
          </Button>
        </div>
      </div>
      <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
        <Lightbulb className="size-3 text-amber-500" />小媒会在对话中直接更新右侧配置，无需手动保存。
      </p>
    </div>
  );
}

function Bubble({ role, text }: { role: string; text: string }) {
  const mine = role === "user";
  return (
    <div className={cn("flex items-start gap-2", mine && "flex-row-reverse")}>
      {!mine && <Logo size="sm" />}
      <div className={cn(
        "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
        mine ? "bg-brand-gradient text-white" : "border bg-card shadow-sm",
      )}>{text}</div>
    </div>
  );
}

const FIELDS: { key: keyof S["AccountPatch"]; label: string; hint?: string; rows?: number }[] = [
  { key: "name", label: "账号名称" },
  { key: "theme", label: "账号主题" },
  { key: "audience", label: "目标受众" },
  { key: "content_style", label: "内容风格", rows: 2 },
  { key: "image_style", label: "配图风格", hint: "每篇帖子的图片怎么安排", rows: 3 },
  { key: "topic_type", label: "选题类型", hint: "通常由小媒对话自动提取，也可手动填写" },
];

const RULE_SOURCE = { user: "手写", chat: "对话", learned: "学到的" } as const;

function ProfileForm({ account }: { account: Account }) {
  const update = useUpdateAccount(account.id);
  const { add, remove } = useRules(account.id);
  const removeNote = useNotes(account.id);
  const [form, setForm] = useState<Record<string, string>>({});
  const [keywords, setKeywords] = useState("");
  const [rule, setRule] = useState("");

  // 只在定位字段本身变化时（保存后、小媒改了配置）同步表单；加减规矩等刷新不覆盖正在编辑的内容
  const profileKey = JSON.stringify([...FIELDS.map((f) => account[f.key as keyof Account]), account.keywords]);
  useEffect(() => {
    setForm(Object.fromEntries(FIELDS.map((f) => [f.key, String(account[f.key as keyof Account] ?? "")])));
    setKeywords(account.keywords.join(", "));
  }, [profileKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = FIELDS.some((f) => form[f.key] !== String(account[f.key as keyof Account] ?? "")) || keywords !== account.keywords.join(", ");

  return (
    <div>
      <h3 className="mb-3 flex items-center gap-1.5 text-lg font-semibold"><Settings className="size-4 text-indigo-500" />手动填写配置</h3>
      <div className="space-y-3.5">
        {FIELDS.map((f) => (
          <div key={f.key}>
            <Label hint={f.hint}>{f.label}</Label>
            {f.rows ? (
              <Textarea rows={f.rows} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            ) : (
              <Input value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            )}
          </div>
        ))}
        <div>
          <Label hint="逗号分隔，搜热点时会用到">具体选题词</Label>
          <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        </div>
        <ErrorText error={update.error} />
        <Button
          className="w-full"
          disabled={!dirty}
          loading={update.isPending}
          onClick={() => update.mutate({ ...form, keywords: keywords.split(/[,，、]+/).map((k) => k.trim()).filter(Boolean) })}
        >
          {!update.isPending && <Save />}保存配置
        </Button>

        <div className="pt-3">
          <Label hint="每篇写稿和质检都会严格遵守">文案要求</Label>
          <div className="space-y-1.5">
            {account.rules.map((r) => (
              <div key={r.id} className="group flex items-center gap-2 rounded-md bg-input-background px-3 py-2 text-sm">
                <span className="flex-1">{r.text}</span>
                <Badge className={r.source === "learned" ? "bg-purple-100 text-purple-700" : "bg-gray-100 text-gray-600"}>{RULE_SOURCE[r.source]}</Badge>
                <button onClick={() => remove.mutate(r.id)} className="cursor-pointer text-muted-foreground opacity-0 hover:text-red-600 group-hover:opacity-100" aria-label="删除">
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (rule.trim()) add.mutate({ text: rule.trim(), source: "user" }, { onSuccess: () => setRule("") }); }}>
              <Input placeholder="加一条，例如「结尾带一个互动提问」" value={rule} onChange={(e) => setRule(e.target.value)} />
              <Button type="submit" variant="outline" loading={add.isPending}>添加</Button>
            </form>
          </div>
        </div>

        <div className="pt-3">
          <Label hint="小媒调研后存下的结论，写稿和出选题时参考最近 5 条">运营笔记</Label>
          {account.notes.length === 0 ? (
            <p className="text-xs text-muted-foreground">还没有。跟小媒说「帮我分析一下某某博主」，分析完会自动存一份要点。</p>
          ) : (
            <div className="space-y-1.5">
              {account.notes.map((n) => (
                <details key={n.id} className="group rounded-md bg-input-background px-3 py-2 text-sm">
                  <summary className="flex cursor-pointer list-none items-center gap-2">
                    <span className="flex-1 font-medium">{n.title}</span>
                    <span className="text-xs text-muted-foreground">{timeAgo(n.created_at)}</span>
                    <button
                      onClick={(e) => { e.preventDefault(); removeNote.mutate(n.id); }}
                      className="cursor-pointer text-muted-foreground opacity-0 hover:text-red-600 group-hover:opacity-100"
                      aria-label="删除笔记"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </summary>
                  <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{n.content}</p>
                </details>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AutoPanel({ account, busy }: { account: Account; busy: boolean }) {
  const update = useUpdateAccount(account.id);
  const write = useWrite(account.id);
  return (
    <div className="border-t pt-8">
      <h3 className="mb-4 flex items-center gap-1.5 text-lg font-semibold"><Bot className="size-4 text-purple-500" />Agent 自动运营</h3>
      <div className="space-y-4">
        <div className="space-y-4 rounded-xl border-2 bg-card p-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-medium">自动运营开关</div>
              <div className="text-xs text-muted-foreground">开启后 Agent 会按频率自动搜选题、生成图文，存入「待审核」，不会自动发布</div>
            </div>
            <Switch checked={account.auto_enabled} disabled={update.isPending} onChange={(v) => update.mutate({ auto_enabled: v })} />
          </div>
          {account.auto_enabled && (
            <div className="flex flex-wrap items-center gap-3 border-t pt-4 text-sm">
              <span className="text-muted-foreground">频率</span>
              <div className="flex gap-1.5">
                {Object.entries(FREQ_LABEL).map(([v, l]) => (
                  <button
                    key={v}
                    onClick={() => update.mutate({ auto_frequency: v as S["AutoFrequency"] })}
                    className={cn("cursor-pointer rounded-md border px-3 py-1 text-xs font-medium transition-all",
                      account.auto_frequency === v ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "hover:bg-accent")}
                  >{l}</button>
                ))}
              </div>
              {account.last_auto_run_at && <span className="text-xs text-muted-foreground">上次运行：{timeAgo(account.last_auto_run_at)}</span>}
            </div>
          )}
        </div>
        <Button variant="gradient" size="lg" className="w-full from-purple-500 to-indigo-600" loading={write.isPending} disabled={busy} onClick={() => write.mutate({ hint: "" })}>
          {!write.isPending && <Play />}{busy ? "正在创作中…" : "立即运行一次（搜选题 → 生成图文 → 存草稿）"}
        </Button>
        <ErrorText error={write.error} />
      </div>
    </div>
  );
}
