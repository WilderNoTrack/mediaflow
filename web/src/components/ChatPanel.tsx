import { Send, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useChat, useSendChat } from "../api/hooks";
import { cn } from "../lib/utils";
import { Button, ErrorText, Spinner, Textarea } from "./ui";

const STARTERS = ["帮我梳理一下这个号的定位", "最近有什么适合我的热点？", "以后标题别用感叹号", "帮我写一篇"];

export function ChatPanel({ accountId }: { accountId: string }) {
  const { data: msgs = [], isLoading } = useChat(accountId);
  const send = useSendChat(accountId);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [msgs.length, pending]);

  const submit = (t = text) => {
    const v = t.trim();
    if (!v || send.isPending) return;
    setPending(v);
    setText("");
    send.mutate(v, { onSettled: () => setPending(null) });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-4 py-3">
        <div className="font-medium">运营管家</div>
        <div className="text-xs text-muted">聊定位、找选题、写稿、记规矩，都可以直接说</div>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {isLoading && <Spinner />}
        {!isLoading && msgs.length === 0 && !pending && (
          <div className="space-y-2">
            <div className="text-sm text-muted">试试这样说：</div>
            {STARTERS.map((s) => (
              <button key={s} onClick={() => submit(s)} className="block cursor-pointer rounded-lg border border-line bg-white px-3 py-2 text-left text-sm hover:border-brand">
                {s}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m) =>
          m.role === "tool" ? (
            <div key={m.id} className="flex items-center gap-1.5 text-xs text-muted">
              <Wrench className="size-3" />
              <span className="truncate">{m.content}</span>
            </div>
          ) : (
            <Bubble key={m.id} mine={m.role === "user"} text={m.content} />
          ),
        )}
        {pending && (
          <>
            <Bubble mine text={pending} />
            <div className="flex items-center gap-2 text-sm text-muted"><Spinner />管家思考中…</div>
          </>
        )}
        <ErrorText error={send.error} />
        <div ref={end} />
      </div>
      <div className="flex gap-2 border-t border-line p-3">
        <Textarea
          rows={2}
          value={text}
          placeholder="和管家说点什么…（Enter 发送，Shift+Enter 换行）"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          className="resize-none"
        />
        <Button variant="primary" onClick={() => submit()} loading={send.isPending} className="h-auto" aria-label="发送">
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  );
}

function Bubble({ mine, text }: { mine?: boolean; text: string }) {
  return (
    <div className={cn("flex", mine && "justify-end")}>
      <div className={cn("max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm", mine ? "bg-brand text-white" : "bg-surface")}>
        {text}
      </div>
    </div>
  );
}
