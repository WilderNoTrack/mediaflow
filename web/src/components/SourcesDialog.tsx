import { CheckCircle2, Circle, ExternalLink, KeyRound, Play, X } from "lucide-react";
import { useState } from "react";
import { useCredentials, useSaveCredentials, useTestSources } from "../api/hooks";
import { cn, PLATFORMS } from "../lib/utils";
import { QrLogin } from "./QrLogin";
import { Badge, Button, ErrorText, Input, Modal, Spinner } from "./ui";

/** 数据来源设置：各平台搜索凭据（只存在本机），并可一键实测 */
export function SourcesDialog({ onClose }: { onClose: () => void }) {
  const { data: creds = [], isLoading } = useCredentials();
  const save = useSaveCredentials();
  const test = useTestSources();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [kw, setKw] = useState("秋季穿搭");
  const dirty = Object.values(draft).some((v) => v.trim());

  const doSave = () => save.mutate(draft, { onSuccess: () => setDraft({}) });

  return (
    <Modal className="max-w-2xl">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <div className="flex items-center gap-2 font-semibold"><KeyRound className="size-4 text-indigo-500" />数据来源</div>
          <p className="mt-0.5 text-xs text-muted-foreground">配好后选题会用各平台的「关键词搜索」，没配的退回热榜。密钥只保存在本机。</p>
        </div>
        <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted"><X className="size-4" /></button>
      </div>

      <div className="max-h-[60vh] space-y-3 overflow-y-auto px-6 py-4">
        {isLoading && <Spinner />}
        {creds.map((c) => (
          <div key={c.key} className="rounded-xl border p-3">
            <div className="mb-1 flex items-center gap-2 text-sm font-medium">
              {c.configured ? <CheckCircle2 className="size-4 text-emerald-500" /> : <Circle className="size-4 text-gray-300" />}
              <Badge className={cn("rounded-full", PLATFORMS[c.platform]?.cls)}>{PLATFORMS[c.platform]?.label ?? c.platform}</Badge>
              {c.label}
              {c.origin === "env" && <span className="text-xs font-normal text-muted-foreground">（来自 .env）</span>}
              {c.auto_refresh && <span className="text-xs font-normal text-emerald-600">自动续期中</span>}
              <a href={c.url} target="_blank" rel="noreferrer" className="ml-auto flex items-center gap-1 text-xs font-normal text-indigo-500 hover:underline">
                去获取<ExternalLink className="size-3" />
              </a>
            </div>
            <p className="mb-2 text-xs text-muted-foreground">{c.help}</p>
            <div className="flex gap-2">
              <Input
                type="password"
                autoComplete="off"
                placeholder={c.configured ? "已配置，留空不改；粘贴新值可覆盖" : c.kind === "cookie" ? "粘贴整段 Cookie" : "粘贴密钥"}
                value={draft[c.key] ?? ""}
                onChange={(e) => setDraft({ ...draft, [c.key]: e.target.value })}
              />
              {c.origin === "ui" && (
                <Button variant="outline" size="sm" onClick={() => save.mutate({ [c.key]: "" })}>清除</Button>
              )}
            </div>
            {c.key === "bilibili_cookie" && !c.auto_refresh && <div className="mt-2"><QrLogin platform="bilibili" /></div>}
            {c.key === "xhs_cookie" && <div className="mt-2"><QrLogin platform="xiaohongshu" again={c.configured} /></div>}
          </div>
        ))}
        <ErrorText error={save.error} />

        <div className="rounded-xl bg-slate-50 p-3">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); test.mutate(kw); }}>
            <Input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="测试关键词" />
            <Button type="submit" variant="outline" loading={test.isPending}>{!test.isPending && <Play />}实测一下</Button>
          </form>
          <ErrorText error={test.error} />
          {test.data && (
            <div className="mt-3 space-y-2 text-xs">
              {test.data.sources.map((s) => (
                <div key={s.source}>
                  <div className="flex items-center gap-2">
                    <span className={cn("font-medium", s.ok ? "text-emerald-600" : s.mode === "off" ? "text-gray-400" : "text-red-500")}>
                      {s.ok ? "✓" : s.mode === "off" ? "–" : "✗"} {s.label}
                    </span>
                    <span className="text-muted-foreground">
                      {s.mode === "search" ? `搜索 ${s.count} 条` : s.mode === "hot" ? `热榜 ${s.count} 条` : ""}{s.note && ` ${s.note}`}
                    </span>
                  </div>
                  {(test.data!.samples[s.source] ?? []).map((it, i) => (
                    <a key={i} href={it.url} target="_blank" rel="noreferrer" className="ml-5 block truncate text-muted-foreground hover:text-indigo-500">· {it.title}</a>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-end gap-2 border-t px-6 py-3">
        <Button variant="ghost" onClick={onClose}>关闭</Button>
        <Button variant="gradient" disabled={!dirty} loading={save.isPending} onClick={doSave}>保存</Button>
      </div>
    </Modal>
  );
}
