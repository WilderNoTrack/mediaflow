import { ChevronDown, ExternalLink, KeyRound, Play, X } from "lucide-react";
import { useState } from "react";
import type { S } from "../api/client";
import { useCredentials, useSaveCredentials, useTestSources } from "../api/hooks";
import { cn, PLATFORMS } from "../lib/utils";
import { QrLogin } from "./QrLogin";
import { Badge, Button, ErrorText, Input, Modal, Spinner } from "./ui";

/** 没连接时的退路，让用户知道不配也能不能用 */
const FALLBACK: Record<string, string> = {
  xiaohongshu: "不连就不搜小红书", zhihu: "不连就不搜知乎", baidu: "不连用百度热搜榜", douyin: "不连用抖音热榜",
  bilibili: "不连用游客身份，容易被限流", weibo: "不连用微博热搜榜",
};

/** 数据来源：一行一个平台，状态一眼可见，点开再填。凭据只存在本机。 */
export function SourcesDialog({ onClose }: { onClose: () => void }) {
  const { data: creds = [], isLoading } = useCredentials();
  const test = useTestSources();
  const [open, setOpen] = useState<string | null>(null);
  const [kw, setKw] = useState("秋季穿搭");
  const connected = creds.filter((c) => c.configured).length;

  return (
    <Modal className="max-w-xl" onClose={onClose}>
      <div className="flex items-start justify-between border-b px-5 py-4">
        <div>
          <div className="flex items-center gap-2 font-semibold"><KeyRound className="size-4 text-indigo-500" />连接平台</div>
          <p className="mt-0.5 text-xs text-muted-foreground">连上的平台能按关键词搜、能分析博主；没连的退回热榜。登录信息只存在这台电脑上。</p>
        </div>
        <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="关闭"><X className="size-4" /></button>
      </div>

      <div className="max-h-[65vh] overflow-y-auto px-5 py-3">
        <div className="mb-2 text-xs text-muted-foreground">已连接 {connected}/{creds.length}，微信公众号不用连接</div>
        {isLoading && <Spinner />}
        <div className="divide-y rounded-xl border">
          {creds.map((c) => <Row key={c.key} c={c} open={open === c.key} onToggle={() => setOpen(open === c.key ? null : c.key)} />)}
        </div>

        <div className="mt-4 rounded-xl bg-slate-50 p-3">
          <div className="mb-2 text-xs font-medium">试一下能不能搜到</div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); test.mutate(kw); }}>
            <Input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="随便一个关键词" className="bg-card" />
            <Button type="submit" variant="outline" loading={test.isPending}>{!test.isPending && <Play />}测试</Button>
          </form>
          <ErrorText error={test.error} />
          {test.data && (
            <div className="mt-3 space-y-2 text-xs">
              {test.data.sources.map((s) => (
                <div key={s.source}>
                  <div className="flex items-center gap-2">
                    <span className={cn("size-1.5 rounded-full", s.ok ? "bg-emerald-500" : s.mode === "off" ? "bg-gray-300" : "bg-red-500")} />
                    <span className="font-medium">{s.label}</span>
                    <span className="text-muted-foreground">
                      {s.mode === "search" ? `搜到 ${s.count} 条` : s.mode === "hot" ? `热榜 ${s.count} 条` : ""}{s.note && ` ${s.note}`}
                    </span>
                  </div>
                  {(test.data!.samples[s.source] ?? []).slice(0, 2).map((it, i) => (
                    <a key={i} href={it.url} target="_blank" rel="noreferrer" className="ml-3.5 block truncate text-muted-foreground hover:text-indigo-500">· {it.title}</a>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="flex justify-end border-t px-5 py-3">
        <Button variant="outline" onClick={onClose}>完成</Button>
      </div>
    </Modal>
  );
}

type Cred = S["CredentialOut"];

function Row({ c, open, onToggle }: { c: Cred; open: boolean; onToggle: () => void }) {
  const save = useSaveCredentials();
  const [value, setValue] = useState("");
  const p = PLATFORMS[c.platform];
  const qr = c.key === "bilibili_cookie" ? "bilibili" : c.key === "xhs_cookie" ? "xiaohongshu" : null;
  return (
    <div>
      <button onClick={onToggle} className="flex w-full cursor-pointer items-center gap-3 px-3.5 py-3 text-left hover:bg-slate-50">
        <Badge className={cn("w-14 justify-center rounded-full", p?.cls)}>{p?.label ?? c.platform}</Badge>
        <div className="min-w-0 flex-1">
          {c.configured ? (
            <div className="text-sm text-emerald-700">已连接{c.auto_refresh && <span className="text-xs text-emerald-600/80"> · 自动续期</span>}{c.origin === "env" && <span className="text-xs text-muted-foreground"> · 来自 .env</span>}</div>
          ) : (
            <div className="text-sm text-muted-foreground">未连接 <span className="text-xs">· {FALLBACK[c.platform] ?? ""}</span></div>
          )}
        </div>
        <span className="text-xs text-indigo-600">{c.configured ? "更新" : qr ? "扫码连接" : "连接"}</span>
        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-2.5 bg-slate-50/60 px-3.5 pb-3.5 pt-1">
          <p className="text-xs leading-relaxed text-muted-foreground">{c.help}
            <a href={c.url} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center gap-0.5 text-indigo-600 hover:underline">去获取<ExternalLink className="size-3" /></a>
          </p>
          {qr && (!c.auto_refresh || qr === "xiaohongshu") && <QrLogin platform={qr} again={c.configured} />}
          <div className="flex gap-2">
            <Input
              type="password"
              autoComplete="off"
              className="bg-card"
              placeholder={qr ? "或者粘贴浏览器里复制的整段 Cookie" : c.kind === "cookie" ? "粘贴整段 Cookie" : "粘贴密钥"}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            <Button size="md" disabled={!value.trim()} loading={save.isPending} onClick={() => save.mutate({ [c.key]: value.trim() }, { onSuccess: () => setValue("") })}>保存</Button>
            {c.origin === "ui" && <Button variant="ghost" onClick={() => { if (confirm(`断开${p?.label ?? ""}？`)) save.mutate({ [c.key]: "" }); }}>断开</Button>}
          </div>
          <ErrorText error={save.error} />
        </div>
      )}
    </div>
  );
}
