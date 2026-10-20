import { Brain, Check, ChevronDown, ChevronRight, MessageCircle, PenLine, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Account, Candidate, ChatMessage } from "../api/client";
import { type ChatStep, useChat, useLiveChat, usePendingChat, useSendChat } from "../api/hooks";
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
  get_draft: { icon: "👀", label: "看了草稿" },
  edit_images: { icon: "🖼", label: "改配图" },
  revise_post: { icon: "✍️", label: "改文案" },
  learn_visual: { icon: "🎨", label: "学配图模板" },
  update_visual: { icon: "🎨", label: "改配图模板" },
};

const PLATFORM_LABEL: Record<string, string> = {
  xiaohongshu: "小红书", douyin: "抖音", bilibili: "B站", weibo: "微博", wechat: "公众号", zhihu: "知乎", baidu: "百度",
};

/** 工具记录的一行摘要：调研类显示查了什么，出错显示原因。 */
function toolSummary(m: ChatMessage) {
  const args = (m.payload?.args ?? {}) as Record<string, string>;
  const result = (m.payload?.result ?? {}) as Record<string, unknown>;
  if (result.ok === false) return `没成功：${String(result.error ?? "")}`;
  if (result.already_running) return "已经在做了，没有重复开，进度见下方";
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
  if (m.tool_name === "write_post" || m.tool_name === "revise_post" || m.tool_name === "learn_visual") return "进度见下方";
  if (m.tool_name === "update_visual") return String(result.changed ?? "") || (Array.isArray(result.pages) ? `${result.pages.length} 种页` : "");
  if (m.tool_name === "get_draft" && typeof result.title === "string") return `《${result.title}》`;
  if (m.tool_name === "edit_images") {
    const ch = Array.isArray(result.changed) ? (result.changed as number[]) : [];
    const rm = Number(result.removed ?? 0);
    return [ch.length ? `第 ${ch.join("、")} 张重新出` : "", rm ? `删了 ${rm} 张` : "", `现在共 ${result.total ?? "?"} 张`].filter(Boolean).join("，");
  }
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

/** 在草稿页里和小媒说怎么改这篇 */
const DRAFT_SUGGESTIONS = ["封面字再大一点", "第 2 张换成对比图", "再加一张清单总结图", "开头改得更抓人", "标题再短一点"];

/** 和小媒的对话：工作台右侧常驻，手机上是全屏抽屉；草稿页里打开时带着正在看的这篇（draft），可以直接让它改文案、改配图 */
export function ChatPanel({ account, onClose, wide, draft }: {
  account: Account; onClose?: () => void; wide?: boolean; draft?: { id: string; title: string };
}) {
  const { data: msgs = [], isLoading } = useChat(account.id);
  const send = useSendChat(account.id, draft?.id);
  // 没发出去的话按账号（和正在看的草稿）存在本地：切到别的页面再回来还在
  const draftKey = `mf-chat-draft:${account.id}:${draft?.id ?? ""}`;
  const [text, setTextRaw] = useState(() => localStorage.getItem(draftKey) ?? "");
  useEffect(() => { setTextRaw(localStorage.getItem(draftKey) ?? ""); }, [draftKey]);
  const setText = (v: string) => {
    setTextRaw(v);
    if (v) localStorage.setItem(draftKey, v);
    else localStorage.removeItem(draftKey);
  };
  const input = useRef<HTMLTextAreaElement>(null);
  const pending = usePendingChat(account.id).at(-1) ?? null;
  const { data: live } = useLiveChat(account.id);
  const box = useRef<HTMLDivElement>(null);
  const byId = new Map(msgs.map((m) => [m.id, m]));
  // 流式对话的工具记录归在回复的「过程」里显示，不再单独列一组
  const covered = new Set(msgs.flatMap((m) => ((m.payload?.steps ?? []) as ChatStep[]).map((s) => s.message_id).filter(Boolean)));

  // 新内容出来时跟着滚到底（用户自己往上翻了就不打扰）
  const stick = useRef(true);
  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTo({ top: el.scrollHeight });
  }, [msgs.length, pending, live?.reply.length, live?.steps.length]);

  const submit = (t = text) => {
    const v = t.trim();
    if (!v || pending) return;
    if (t === text) setText("");
    send.mutate(v);
  };
  // 小媒最后一句是带选项的提问、用户还没回：在它下面放按钮
  const lastMsg = [...msgs].reverse().find((m) => m.role !== "tool");
  const ask = !pending && !live && lastMsg?.role === "assistant" ? (lastMsg.payload?.ask as Ask | undefined) : undefined;

  const welcome = `你好！我是小媒，帮你打理「${account.name}」。\n\n不知道从哪开始？点下面的按钮就行：\n- **找对标账号**：我去小红书找几个做得好的同类账号，学 TA 们的套路\n- **今天写一篇**：选题、文案、配图我来，你看看、改改就能发\n\n有想法也可以直接打字，比如「我是二胎宝妈，想分享带娃省钱经验」。`;

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-card">
      <div className="flex items-center gap-2.5 border-b px-4 py-3">
        <MessageCircle className="size-4 text-indigo-500" />
        <div className="min-w-0 flex-1">
          <div className="font-semibold">小媒</div>
          <div className="truncate text-xs text-muted-foreground">
            {pending ? "正在处理…" : draft ? `正在看《${draft.title || "这篇草稿"}》，想怎么改直接说` : "想做什么直接说：找对标、找选题、写稿、改设定"}
          </div>
        </div>
        {onClose && <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="收起"><X className="size-4" /></button>}
      </div>

      <div ref={box} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }} className={cn("min-h-0 flex-1 space-y-3 overflow-y-auto bg-slate-50/50 p-4", wide && "sm:px-8 sm:py-6")}>
        {isLoading && <Spinner />}
        {!isLoading && msgs.length === 0 && <Bubble role="assistant" text={welcome} />}
        {groupTools(msgs.filter((m) => !covered.has(m.id))).map((g) =>
          Array.isArray(g) ? (
            <div key={g[0].id} className="space-y-2">
              <ToolGroup items={g} />
              {g.map((m) => <ToolCard key={m.id} account={account} m={m} />)}
            </div>
          ) : g.role === "assistant" && Array.isArray(g.payload?.steps) ? (
            <div key={g.id} className="space-y-2">
              <Process steps={g.payload.steps as ChatStep[]} byId={byId} total={g.payload.ms as number | undefined} />
              {(g.payload.steps as ChatStep[]).map((st) => st.message_id && byId.get(st.message_id)
                ? <ToolCard key={st.id} account={account} m={byId.get(st.message_id)!} /> : null)}
              <Bubble role="assistant" text={g.content} />
              {ask && g.id === lastMsg?.id && <AskButtons key={g.id} ask={ask} onPick={(t) => submit(t)} onSelf={() => input.current?.focus()} />}
            </div>
          ) : <Bubble key={g.id} role={g.role} text={g.content} />,
        )}
        {live && <>
          {!live.echoed && <Bubble role="user" text={live.text} />}
          {live.steps.length > 0
            ? <Process steps={live.steps} byId={new Map([...byId, ...live.tools.map((m) => [m.id, m] as const)])} live started={live.started} />
            : <div className="ml-10 flex items-center gap-2 text-xs text-muted-foreground"><Spinner className="size-3" />发给小媒了…</div>}
          {live.tools.map((m) => <ToolCard key={m.id} account={account} m={m} />)}
          {live.reply && <Bubble role="assistant" text={live.reply} typing />}
        </>}
        <ErrorText error={send.error} />
      </div>

      <div className="border-t p-3">
        {!pending && !ask && (
          <div className="-mx-3 mb-2 flex gap-1.5 overflow-x-auto px-3 pb-0.5">
            {(draft ? DRAFT_SUGGESTIONS : suggestions(account)).map((s) => (
              <button key={s} onClick={() => submit(s)} className="shrink-0 cursor-pointer rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1 text-xs text-indigo-600 transition-colors hover:bg-indigo-100">{s}</button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <Textarea
            ref={input}
            rows={1}
            value={text}
            placeholder={ask ? "点上面的选项，或者自己说…" : draft ? "比如「第 3 张换成前后对比」「开头再口语一点」…" : "聊定位、改配置、或说「写一篇试试」…"} title="Enter 发送，Shift+Enter 换行"
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

type Ask = { question?: string; options: string[]; multi?: boolean; kind?: "choice" | "confirm" };

/** 小媒问的选择题 / 确认：点一下就当用户说了这句话；多选的先勾再点确定；也可以自己打字 */
function AskButtons({ ask, onPick, onSelf }: { ask: Ask; onPick: (t: string) => void; onSelf: () => void }) {
  const [sel, setSel] = useState<string[]>([]);
  const own = ask.options.some((o) => /我来|自己/.test(o));
  const pill = "flex cursor-pointer items-center gap-1 rounded-full border px-3 py-1.5 text-sm transition-colors";
  const self = !own && (
    <button onClick={onSelf} className={cn(pill, "border-dashed border-slate-300 bg-white text-muted-foreground hover:text-foreground")}>
      <PenLine className="size-3.5" />我自己说
    </button>
  );
  if (ask.multi) {
    const toggle = (o: string) => setSel(sel.includes(o) ? sel.filter((x) => x !== o) : [...sel, o]);
    return (
      <div className="ml-10 space-y-1.5">
        <div className="text-xs text-muted-foreground">可以多选</div>
        <div className="flex flex-wrap gap-1.5">
          {ask.options.map((o) => {
            const on = sel.includes(o);
            return (
              <button key={o} onClick={() => toggle(o)} aria-pressed={on}
                className={cn(pill, on ? "border-indigo-500 bg-indigo-500 text-white" : "border-indigo-200 bg-white text-indigo-700 hover:bg-indigo-50")}>
                {on && <Check className="size-3.5" />}{o}
              </button>
            );
          })}
          <Button size="sm" variant="gradient" className="rounded-full" disabled={!sel.length} onClick={() => onPick(sel.join("、"))}>
            确定{sel.length > 0 && `（${sel.length}）`}
          </Button>
          {self}
        </div>
      </div>
    );
  }
  return (
    <div className="ml-10 flex flex-wrap gap-1.5">
      {ask.options.map((o, i) => (
        <button key={o} onClick={() => onPick(o)}
          className={cn(pill, ask.kind === "confirm" && i === 0
            ? "border-transparent bg-brand-gradient font-medium text-white shadow-sm hover:opacity-90"
            : "border-indigo-200 bg-white text-indigo-700 hover:bg-indigo-50")}>
          {ask.kind === "confirm" && i === 0 && <Check className="size-3.5" />}{o}
        </button>
      ))}
      {self}
    </div>
  );
}

/** 没成功、但后面同一个操作又做成了的（小媒自己改了参数重试）：不算失败 */
function retriedOk<T extends { name: string; ok?: boolean }>(list: T[]): Set<number> {
  const out = new Set<number>();
  list.forEach((t, i) => {
    if (t.ok === false && list.slice(i + 1).some((x) => x.name === t.name && x.ok !== false)) out.add(i);
  });
  return out;
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
  const flat = items.map((m) => ({ name: m.tool_name, ok: (m.payload?.result as { ok?: boolean })?.ok }));
  const retried = retriedOk(flat);
  const bad = items.filter((_, i) => flat[i].ok === false && !retried.has(i));
  const failed = bad.length;
  return (
    <div className="ml-10 rounded-lg border border-indigo-100 bg-indigo-50/50 text-xs text-indigo-800">
      {items.length > 2 && (
        <button onClick={() => setOpen(!open)} className="flex w-full cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-left font-medium">
          <span>⚙️</span>做了 {items.length} 件事{failed > 0 && <span className="truncate text-red-600">
            （{failed === 1 ? `${TOOL_META[bad[0].tool_name]?.label ?? bad[0].tool_name}没成功：${String((bad[0].payload?.result as { error?: string })?.error ?? "").slice(0, 40)}` : `${failed} 件没成功`}）</span>}
          <ChevronDown className={cn("ml-auto size-3.5 transition-transform", open && "rotate-180")} />
        </button>
      )}
      {open && (
        <div className={cn("space-y-1 px-2.5 py-1.5", items.length > 2 && "border-t border-indigo-100")}>
          {items.map((m, i) => {
            const meta = TOOL_META[m.tool_name];
            const sum = retried.has(i) ? "这次没成功，后面换了个方式重试成功了" : toolSummary(m);
            const bad = !retried.has(i) && sum.startsWith("没成功");
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

/** 工具结果对应的卡片：对标候选、任务进度、选题 */
function ToolCard({ account, m }: { account: Account; m: ChatMessage }) {
  const r = (m.payload?.result ?? {}) as { ok?: boolean; candidates?: Candidate[]; job_id?: string; draft_id?: string; topics?: { id: string; title: string; angle?: string }[] };
  if (!r.ok) return null;
  if (m.tool_name === "find_benchmarks" && r.candidates) return <CandidatePicker account={account} candidates={r.candidates} compact />;
  if (["write_post", "clone_creator", "revise_post", "edit_images", "learn_visual"].includes(m.tool_name) && r.job_id)
    return <ChatJobCard account={account} jobId={r.job_id} draftId={r.draft_id} />;
  if (m.tool_name === "find_topics" && r.topics?.length) return <TopicCards account={account} topics={r.topics} />;
  return null;
}

function secs(ms: number) {
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} 秒`;
  return `${Math.floor(ms / 60000)} 分 ${Math.round((ms % 60000) / 1000)} 秒`;
}

/** 进行中时每 100ms 刷新一次，用来显示「思考中… 2.3 秒」 */
function useNow(on: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [on]);
  return now;
}

/** 这一轮小媒的过程：思考了几秒、调了哪些工具（各用时多少），每一步都能点开看细节。
 *  进行中展开、实时计时；做完后收成一行「用时 N 秒」，想看再点开。 */
function Process({ steps, byId, live, started, total }: {
  steps: ChatStep[]; byId: Map<string, ChatMessage>; live?: boolean; started?: number; total?: number;
}) {
  const [open, setOpen] = useState(false);
  const now = useNow(!!live);
  const tools = steps.filter((s) => s.kind === "tool");
  const thinkMs = steps.filter((s) => s.kind === "thinking").reduce((a, s) => a + (s.ms ?? (live && s.started ? now - s.started : 0)), 0);
  const retried = retriedOk(tools.map((t) => ({ name: t.name ?? "", ok: t.ok })));
  const bad = tools.filter((t, i) => t.ok === false && !retried.has(i));
  const failed = bad.length;
  const retriedIds = new Set(tools.filter((_, i) => retried.has(i)).map((t) => t.id));
  const simple = !tools.length && !steps.some((s) => s.kind === "note" || s.text);
  if (simple && !live) return <div className="ml-10 flex items-center gap-1 text-xs text-muted-foreground"><Brain className="size-3" />思考了 {secs(thinkMs)}</div>;
  const elapsed = live && started ? now - started : total ?? 0;
  const show = live || open;
  return (
    <div className="ml-10 rounded-lg border border-indigo-100 bg-indigo-50/40 text-xs text-indigo-900">
      <button onClick={() => !live && setOpen(!open)} className={cn("flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left", !live && "cursor-pointer")}>
        {live ? <Spinner className="size-3" /> : <span>✨</span>}
        <span className="font-medium">{live ? "小媒正在处理" : "处理完了"}</span>
        <span className="text-indigo-600/70">
          · {live ? "已" : ""}用时 {secs(elapsed)}{thinkMs > 0 && ` · 思考 ${secs(thinkMs)}`}{tools.length > 0 && ` · 做了 ${tools.length} 件事`}
          {failed > 0 && <span className="text-red-600">（{failed === 1
            ? `${TOOL_META[bad[0].name ?? ""]?.label ?? bad[0].name}没成功${bad[0].error ? `：${bad[0].error.slice(0, 40)}` : ""}`
            : `${failed} 件没成功，点开看原因`}）</span>}
        </span>
        {!live && <ChevronDown className={cn("ml-auto size-3.5 shrink-0 transition-transform", open && "rotate-180")} />}
      </button>
      {show && (
        <div className="space-y-0.5 border-t border-indigo-100 px-1.5 py-1">
          {steps.map((st) => <StepRow key={st.id} st={st} m={st.message_id ? byId.get(st.message_id) : undefined} now={now} live={!!live} retried={retriedIds.has(st.id)} />)}
        </div>
      )}
    </div>
  );
}

function StepRow({ st, m, now, live, retried }: { st: ChatStep; m?: ChatMessage; now: number; live: boolean; retried?: boolean }) {
  const [open, setOpen] = useState(false);
  const running = st.kind !== "note" && st.ms == null && live;
  const ms = st.ms ?? (running && st.started ? now - st.started : undefined);
  if (st.kind === "note") return <div className="px-1 py-0.5 text-indigo-700/80">💬 {st.text}</div>;
  let head: React.ReactNode;
  let detail: React.ReactNode = null;
  if (st.kind === "thinking") {
    head = <><Brain className="size-3.5 shrink-0 text-indigo-500" /><span className="font-medium">{running ? "思考中…" : "思考了"}</span></>;
    if (st.text) detail = <p className="whitespace-pre-wrap leading-relaxed text-indigo-800/80">{st.text}</p>;
  } else {
    const meta = TOOL_META[st.name ?? ""];
    const sum = m ? toolSummary(m) : "";
    head = <>
      <span>{meta?.icon ?? "🔧"}</span>
      <span className="shrink-0 font-medium">{meta?.label ?? st.name}{running && "…"}</span>
      {st.ok === false ? (retried ? <span className="truncate text-amber-600">没成功，后面重试成功了</span>
        : <span className="truncate text-red-600" title={st.error}>没成功{st.error ? `：${st.error}` : ""}</span>)
        : sum && <span className="truncate text-indigo-600/70" title={sum}>{sum}</span>}
    </>;
    const args = Object.entries(st.args ?? {}).filter(([, v]) => v !== "" && v != null);
    detail = (
      <div className="space-y-1">
        {args.length > 0 && <div className="space-y-0.5">{args.map(([k, v]) => (
          <div key={k} className="flex gap-1.5"><span className="shrink-0 text-indigo-500">{ARG_LABEL[k] ?? k}</span><span className="break-all">{typeof v === "string" ? v : JSON.stringify(v)}</span></div>
        ))}</div>}
        {st.error ? <div className="text-red-600">原因：{st.error}</div> : sum ? <div>结果：{sum}</div> : !running && <div className="text-indigo-500">完成</div>}
      </div>
    );
  }
  const can = !!detail && !running;
  return (
    <div>
      <button onClick={() => can && setOpen(!open)} className={cn("flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left", can && "cursor-pointer hover:bg-indigo-100/60")}>
        {head}
        <span className="ml-auto flex shrink-0 items-center gap-1 pl-2 tabular-nums text-indigo-500">
          {running && <Spinner className="size-3" />}{ms != null && secs(ms)}
          {can && <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} />}
        </span>
      </button>
      {open && detail && <div className="mb-1 ml-5 rounded-md bg-white/70 px-2 py-1.5">{detail}</div>}
    </div>
  );
}

const ARG_LABEL: Record<string, string> = {
  keyword: "关键词", platform: "平台", name: "名字", query: "搜", text: "内容", title: "标题", topic_id: "选题",
  hint: "要求", direction: "方向", reference_url: "参考帖", targets: "对标", theme: "主题", enabled: "开启", frequency: "频率",
  creator_ref: "博主", post_ref: "作品", limit: "数量", sort: "排序", prefer: "偏好",
  draft_id: "草稿", ops: "改动", instruction: "要求", image_plan: "配图想法", links: "链接",
};

/** 逐字显示：新到的字以「追上去」的速度一点点露出来，像打字一样 */
function useTypewriter(text: string, on: boolean) {
  const [n, setN] = useState(on ? 0 : text.length);
  useEffect(() => {
    if (!on) { setN(text.length); return; }
    if (n >= text.length) return;
    const t = setTimeout(() => setN((x) => Math.min(text.length, x + Math.max(1, Math.ceil((text.length - x) / 12)))), 16);
    return () => clearTimeout(t);
  }, [text, n, on]);
  return text.slice(0, n);
}

function Bubble({ role, text, typing }: { role: string; text: string; typing?: boolean }) {
  const mine = role === "user";
  const shown = useTypewriter(text, !!typing);
  text = typing ? shown : text;
  return (
    <div className={cn("flex items-start gap-2", mine && "flex-row-reverse")}>
      {!mine && <Logo size="sm" />}
      <div className={cn(
        "max-w-[85%] break-words rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
        mine ? "whitespace-pre-wrap bg-brand-gradient text-white" : "border bg-card shadow-sm",
      )}>{mine ? text : <Markdown text={text} />}{typing && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-indigo-400 align-middle" />}</div>
    </div>
  );
}
