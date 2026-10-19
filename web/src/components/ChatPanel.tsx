import { ChevronDown, MessageCircle, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Account, Candidate, ChatMessage } from "../api/client";
import { useChat, usePendingChat, useSendChat } from "../api/hooks";
import { CandidatePicker } from "./CandidatePicker";
import { ChatJobCard, TopicCards } from "./ChatCards";
import { Markdown } from "./Markdown";
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
  find_benchmarks: { icon: "🔭", label: "找同领域对标账号" },
  clone_creator: { icon: "🪄", label: "开始学习对标账号" },
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
  if (m.tool_name === "find_topics" && Array.isArray(result.topics)) return `${result.topics.length} 个，点「写这篇」就开始写`;
  if (m.tool_name === "write_post") return "进度见下方";
  if (m.tool_name === "find_benchmarks" && Array.isArray(result.candidates)) return `${result.candidates.length} 个，在下面勾选`;
  if (m.tool_name === "clone_creator") return `${Array.isArray(result.added) ? result.added.length : 1} 个，进度见下方`;
  return "";
}

/** 根据账号状态给几个可以直接点的开场问题 */
function suggestions(a: Account): string[] {
  if (!a.theme) return ["我是宝妈，想分享带娃省钱经验", "帮我想想账号定位", "帮我找几个做得好的同类账号"];
  if (!a.benchmarks.length) return ["今天写一篇", "帮我找几个同领域的对标账号", "找几个这周能写的选题", "最近写得怎么样？"];
  return ["今天写一篇", "找几个这周能写的选题", "最近写得怎么样？", "再找几个对标账号"];
}

/** 和小媒的对话：工作台右侧常驻，手机上是全屏抽屉 */
export function ChatPanel({ account, onClose, wide }: { account: Account; onClose?: () => void; wide?: boolean }) {
  const { data: msgs = [], isLoading } = useChat(account.id);
  const send = useSendChat(account.id);
  const [text, setText] = useState("");
  const pending = usePendingChat(account.id).at(-1) ?? null;
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [msgs.length, pending]);

  const submit = (t = text) => {
    const v = t.trim();
    if (!v || pending) return;
    setText("");
    send.mutate(v);
  };

  const welcome = `你好！我是小媒，帮你打理「${account.name}」。\n\n不知道从哪开始？点下面的按钮就行：\n- **找对标账号**：我去小红书找几个做得好的同类账号，学 TA 们的套路\n- **今天写一篇**：选题、文案、配图我来，你看看、改改就能发\n\n有想法也可以直接打字，比如「我是二胎宝妈，想分享带娃省钱经验」。`;

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-card">
      <div className="flex items-center gap-2.5 border-b px-4 py-3">
        <MessageCircle className="size-4 text-indigo-500" />
        <div className="min-w-0 flex-1">
          <div className="font-semibold">小媒</div>
          <div className="truncate text-xs text-muted-foreground">{pending ? "正在处理…" : "想做什么直接说：找对标、找选题、写稿、改设定"}</div>
        </div>
        {onClose && <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="收起"><X className="size-4" /></button>}
      </div>

      <div ref={box} className={cn("min-h-0 flex-1 space-y-3 overflow-y-auto bg-slate-50/50 p-4", wide && "sm:px-8 sm:py-6")}>
        {isLoading && <Spinner />}
        {!isLoading && msgs.length === 0 && <Bubble role="assistant" text={welcome} />}
        {groupTools(msgs).map((g) =>
          Array.isArray(g) ? (
            <div key={g[0].id} className="space-y-2">
              <ToolGroup items={g} />
              {g.map((m) => {
                const r = (m.payload?.result ?? {}) as { ok?: boolean; candidates?: Candidate[]; job_id?: string; topics?: { id: string; title: string; angle?: string }[] };
                if (!r.ok) return null;
                if (m.tool_name === "find_benchmarks" && r.candidates) return <CandidatePicker key={m.id} account={account} candidates={r.candidates} compact />;
                if ((m.tool_name === "write_post" || m.tool_name === "clone_creator") && r.job_id) return <ChatJobCard key={m.id} account={account} jobId={r.job_id} />;
                if (m.tool_name === "find_topics" && r.topics?.length) return <TopicCards key={m.id} account={account} topics={r.topics} />;
                return null;
              })}
            </div>
          ) : <Bubble key={g.id} role={g.role} text={g.content} />,
        )}
        {pending && <>
          <Bubble role="user" text={pending} />
          <div className="ml-10 flex items-center gap-2 text-xs text-muted-foreground"><Spinner className="size-3" />{/对标|找.*号/.test(pending) ? "正在小红书上找同领域的号、看数据，大约半分钟到一分钟…" : "小媒正在想，调研类问题要半分钟左右…"}</div>
        </>}
        <ErrorText error={send.error} />
      </div>

      <div className="border-t p-3">
        {!pending && (
          <div className="-mx-3 mb-2 flex gap-1.5 overflow-x-auto px-3 pb-0.5">
            {suggestions(account).map((s) => (
              <button key={s} onClick={() => submit(s)} className="shrink-0 cursor-pointer rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1 text-xs text-indigo-600 transition-colors hover:bg-indigo-100">{s}</button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <Textarea
            rows={1}
            value={text}
            placeholder="聊定位、改配置、或说「写一篇试试」…" title="Enter 发送，Shift+Enter 换行"
            className="max-h-32 min-h-9 resize-none py-2"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
          />
          <Button variant="gradient" size="md" className="px-3" onClick={() => submit()} disabled={!text.trim()} loading={!!pending} aria-label="发送">
            {!pending && <Send />}
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
        "max-w-[85%] break-words rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
        mine ? "whitespace-pre-wrap bg-brand-gradient text-white" : "border bg-card shadow-sm",
      )}>{mine ? text : <Markdown text={text} />}</div>
    </div>
  );
}
