import { ChevronDown, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Account, ChatMessage } from "../api/client";
import { useChat, useSendChat } from "../api/hooks";
import { cn } from "../lib/utils";
import { Button, ErrorText, Logo, Spinner, Textarea } from "./ui";

const TOOL_META: Record<string, { icon: string; label: string }> = {
  update_profile: { icon: "✏️", label: "更新了账号设定" },
  add_rule: { icon: "📌", label: "记下文案要求" },
  remove_rule: { icon: "🗑", label: "删掉文案要求" },
  list_drafts: { icon: "🗂", label: "看了最近的草稿" },
  find_topics: { icon: "🔍", label: "找了选题" },
  write_post: { icon: "🚀", label: "开始写稿" },
  set_auto: { icon: "⏰", label: "设置自动运营" },
  research_search: { icon: "🌐", label: "搜各平台内容" },
  research_creators: { icon: "👤", label: "搜博主" },
  research_creator_posts: { icon: "📚", label: "看博主作品" },
  research_post: { icon: "📄", label: "看作品详情" },
  save_note: { icon: "📝", label: "存了运营笔记" },
  remove_note: { icon: "🗑", label: "删了运营笔记" },
};

const PLATFORM_LABEL: Record<string, string> = {
  xiaohongshu: "小红书", douyin: "抖音", bilibili: "B站", weibo: "微博", wechat: "公众号", zhihu: "知乎", baidu: "百度",
};

/** 工具记录的一行摘要：调研类显示查了什么，出错显示原因。 */
function toolSummary(m: ChatMessage) {
  const args = (m.payload?.args ?? {}) as Record<string, string>;
  const result = (m.payload?.result ?? {}) as Record<string, unknown>;
  if (result.ok === false) return `没成功：${String(result.error ?? "")}`;
  if (m.tool_name.startsWith("research_")) {
    const what = [PLATFORM_LABEL[args.platform] ?? args.platform, args.keyword ?? args.name].filter(Boolean).join(" · ");
    const n = Array.isArray(result.items) ? result.items.length : Array.isArray(result.creators) ? result.creators.length
      : Array.isArray(result.posts) ? result.posts.length : 0;
    const title = typeof result.title === "string" ? `「${result.title}」` : "";
    return `${what}${n ? `，${n} 条` : ""}${title}`;
  }
  if (m.tool_name === "save_note") return String(args.title ?? "");
  if (m.tool_name === "add_rule") return String(args.text ?? "");
  if (m.tool_name === "update_profile") {
    const keys: Record<string, string> = { theme: "主题", audience: "受众", content_style: "文案风格", image_style: "配图风格",
      topic_type: "选题方向", keywords: "关键词", name: "名称" };
    return Object.keys(args).map((k) => keys[k] ?? k).join("、");
  }
  if (m.tool_name === "find_topics" && Array.isArray(result.topics)) return `${result.topics.length} 个，已放进选题库`;
  if (m.tool_name === "write_post") return "写好会出现在「草稿」里";
  return "";
}

/** 根据账号状态给几个可以直接点的开场问题 */
function suggestions(a: Account): string[] {
  if (!a.theme) return ["我想做一个职场新人理财账号", "帮我想想账号定位", "分析一下小红书博主程十安"];
  return ["找几个这周能写的选题", "写一篇试试", "帮我分析一个对标博主", "最近的草稿写得怎么样？"];
}

/** 和小媒的对话：工作台右侧常驻，手机上是全屏抽屉 */
export function ChatPanel({ account, onClose }: { account: Account; onClose?: () => void }) {
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

  const welcome = `你好，我是小媒，「${account.name}」的运营搭子。\n\n定位、选题、写稿、找对标，直接跟我说就行，我会边聊边帮你改好左边的设定。`;

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-card">
      <div className="flex items-center gap-2.5 border-b px-4 py-3">
        <Logo size="sm" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">小媒</div>
          <div className="truncate text-xs text-muted-foreground">{send.isPending ? "正在处理…" : "账号管家 · 会记住你们聊过的"}</div>
        </div>
        {onClose && <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="收起"><X className="size-4" /></button>}
      </div>

      <div ref={box} className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-slate-50/60 px-4 py-4">
        {isLoading && <Spinner />}
        {!isLoading && msgs.length === 0 && <Bubble role="assistant" text={welcome} />}
        {groupTools(msgs).map((g) =>
          Array.isArray(g) ? <ToolGroup key={g[0].id} items={g} /> : <Bubble key={g.id} role={g.role} text={g.content} />,
        )}
        {pending && <>
          <Bubble role="user" text={pending} />
          <div className="ml-10 flex items-center gap-2 text-xs text-muted-foreground"><Spinner className="size-3" />小媒正在想，调研类问题要半分钟左右…</div>
        </>}
        <ErrorText error={send.error} />
      </div>

      <div className="border-t p-3">
        {!send.isPending && msgs.length < 4 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {suggestions(account).map((s) => (
              <button key={s} onClick={() => submit(s)} className="cursor-pointer rounded-full border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-indigo-300 hover:text-indigo-600">{s}</button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2 rounded-xl border bg-input-background p-1.5 focus-within:border-indigo-300">
          <Textarea
            rows={1}
            value={text}
            placeholder="跟小媒说点什么…" title="Enter 发送，Shift+Enter 换行"
            className="max-h-32 min-h-9 resize-none bg-transparent py-1.5 focus-visible:ring-0"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
          />
          <Button variant="gradient" size="sm" className="size-8 px-0" onClick={() => submit()} disabled={!text.trim()} loading={send.isPending} aria-label="发送">
            {!send.isPending && <Send />}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 连续的工具记录合成一组，默认折叠成一行「做了 N 件事」 */
function groupTools(msgs: ChatMessage[]): (ChatMessage | ChatMessage[])[] {
  const out: (ChatMessage | ChatMessage[])[] = [];
  for (const m of msgs) {
    const last = out[out.length - 1];
    if (m.role === "tool") {
      if (Array.isArray(last)) last.push(m);
      else out.push([m]);
    } else out.push(m);
  }
  return out;
}

function ToolGroup({ items }: { items: ChatMessage[] }) {
  const [open, setOpen] = useState(items.length <= 2);
  const failed = items.filter((m) => (m.payload?.result as { ok?: boolean })?.ok === false).length;
  return (
    <div className="ml-10 rounded-lg border border-indigo-100 bg-indigo-50/50 text-xs text-indigo-800">
      {items.length > 2 && (
        <button onClick={() => setOpen(!open)} className="flex w-full cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-left font-medium">
          <span>⚙️</span>做了 {items.length} 件事{failed > 0 && <span className="text-red-600">（{failed} 件没成功）</span>}
          <ChevronDown className={cn("ml-auto size-3.5 transition-transform", open && "rotate-180")} />
        </button>
      )}
      {open && (
        <div className={cn("space-y-1 px-2.5 py-1.5", items.length > 2 && "border-t border-indigo-100")}>
          {items.map((m) => {
            const meta = TOOL_META[m.tool_name];
            const sum = toolSummary(m);
            const bad = sum.startsWith("没成功");
            return (
              <div key={m.id} className="flex items-center gap-1.5">
                <span>{meta?.icon ?? "🔧"}</span>
                <span className="shrink-0 font-medium">{meta?.label ?? m.tool_name}</span>
                {sum && <span className={cn("truncate", bad ? "text-red-600" : "text-indigo-600/70")} title={sum}>{sum}</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Bubble({ role, text }: { role: string; text: string }) {
  const mine = role === "user";
  return (
    <div className={cn("flex items-start gap-2", mine && "flex-row-reverse")}>
      {!mine && <Logo size="sm" />}
      <div className={cn(
        "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
        mine ? "rounded-tr-sm bg-indigo-600 text-white" : "rounded-tl-sm border bg-card",
      )}>{text}</div>
    </div>
  );
}
