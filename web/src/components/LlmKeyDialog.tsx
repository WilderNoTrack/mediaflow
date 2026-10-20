import { Check, ExternalLink, KeyRound, X } from "lucide-react";
import { useState } from "react";
import { useLlmSettings, useSaveLlmKey } from "../api/hooks";
import { Badge, Button, ErrorText, Input, Modal, Segmented } from "./ui";

type Channel = "auto" | "next" | "deepseek";

function Status({ on, env }: { on?: boolean; env?: boolean }) {
  return on
    ? <Badge className="bg-emerald-50 text-emerald-700"><Check className="size-3" />已填好{env && "（来自 .env）"}</Badge>
    : <Badge className="bg-slate-100 text-slate-500">没填</Badge>;
}

/** 填写稿、聊天用的模型 Key：openai-next（优先，和配图共用一个 Key）或 DeepSeek 官方（备用），填一个就能用。
 *  不用改文件、不用重启；保存前会实际试一句，填错当场提示。 */
export function LlmKeyDialog({ onClose }: { onClose: () => void }) {
  const { data: st } = useLlmSettings();
  const save = useSaveLlmKey();
  const [nextKey, setNextKey] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [dsKey, setDsKey] = useState("");
  const [done, setDone] = useState("");
  const ok = !!st?.configured && !!done;
  const order = (st?.order ?? []).map((c) => (c === "next" ? "openai-next" : "DeepSeek 官方")).join(" → ");
  const run = (body: Parameters<typeof save.mutate>[0], what: string, reset: () => void) =>
    save.mutate(body, { onSuccess: () => { reset(); setDone(what); } });
  return (
    <Modal className="max-w-lg" onClose={onClose}>
      <div className="flex items-start justify-between border-b px-5 py-4">
        <div>
          <div className="flex items-center gap-2 font-semibold"><KeyRound className="size-4 text-indigo-500" />写稿和聊天用的模型</div>
          <p className="mt-0.5 text-xs text-muted-foreground">都是 DeepSeek，两条路填一个就能用；都填了先走 openai-next，出错自动换官方。Key 只存在这台电脑上。</p>
        </div>
        <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="关闭"><X className="size-4" /></button>
      </div>
      <div className="space-y-5 px-5 py-4 text-sm">
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="font-medium">openai-next <span className="text-xs font-normal text-muted-foreground">（优先用，和 AI 配图共用一个 Key）</span></div>
            <Status on={st?.next_configured} env={st?.next_origin === "env"} />
          </div>
          <p className="text-xs text-slate-600">在 <a href="https://credits.openai-next.com" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline">openai-next<ExternalLink className="size-3" /></a> 复制 sk- 开头的 Key。配图那边填过的话这里已经是好的。</p>
          <form className="space-y-2" onSubmit={(e) => {
            e.preventDefault();
            const m = model?.trim();
            run({ ...(nextKey.trim() ? { next_api_key: nextKey.trim() } : {}), ...(model !== null && m !== st?.next_model ? { next_model: m ?? "" } : {}) },
              "openai-next", () => { setNextKey(""); setModel(null); });
          }}>
            <Input type="password" value={nextKey} onChange={(e) => setNextKey(e.target.value)} autoComplete="off"
              placeholder={st?.next_configured ? "已保存，要换就粘贴新的" : "粘贴 openai-next 的 Key"} />
            <div className="flex gap-2">
              <Input value={model ?? st?.next_model ?? ""} onChange={(e) => setModel(e.target.value)} placeholder="模型名"
                title="openai-next 上 DeepSeek 模型的名字，一般不用改" className="font-mono text-xs" />
              <Button type="submit" variant="gradient" className="shrink-0"
                disabled={!nextKey.trim() && (model === null || model.trim() === st?.next_model)}
                loading={save.isPending && save.variables && ("next_api_key" in save.variables || "next_model" in save.variables)}>验证并保存</Button>
            </div>
          </form>
        </section>
        <section className="space-y-2 border-t pt-4">
          <div className="flex items-center justify-between">
            <div className="font-medium">DeepSeek 官方 <span className="text-xs font-normal text-muted-foreground">（备用；只用它也行）</span></div>
            <Status on={st?.deepseek_configured} env={st?.origin === "env"} />
          </div>
          <p className="text-xs text-slate-600">打开 <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline">DeepSeek 开放平台<ExternalLink className="size-3" /></a>，手机号注册 → 先少充一点 → 「API keys」创建，复制 sk- 开头那串。</p>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (dsKey.trim()) run({ api_key: dsKey.trim() }, "DeepSeek", () => setDsKey("")); }}>
            <Input type="password" value={dsKey} onChange={(e) => setDsKey(e.target.value)} autoComplete="off"
              placeholder={st?.deepseek_configured ? "已保存，要换就粘贴新的" : "粘贴 sk- 开头的 Key"} />
            <Button type="submit" variant="gradient" className="shrink-0" disabled={!dsKey.trim()}
              loading={save.isPending && save.variables && "api_key" in save.variables}>验证并保存</Button>
          </form>
        </section>
        {st?.next_configured && st?.deepseek_configured && (
          <section className="flex items-center justify-between gap-3 border-t pt-4">
            <div className="text-xs text-slate-600">先用哪条</div>
            <Segmented<Channel> value={(st?.channel as Channel) ?? "auto"} onChange={(v) => run({ channel: v }, "通道", () => {})}
              items={[{ value: "auto", label: "openai-next 优先" }, { value: "next", label: "只用 openai-next" }, { value: "deepseek", label: "只用官方" }]} />
          </section>
        )}
        <ErrorText error={save.error} />
        {st?.configured && <p className="text-xs text-slate-500">现在：{order || "—"}{st.next_paused && "（openai-next 刚出过错，这一阵先走官方）"}</p>}
        {ok && <p className="flex items-center gap-1.5 text-xs text-emerald-700"><Check className="size-3.5" />{done === "通道" ? "改好了" : `${done} 能用了！`}现在可以去和小媒聊天、写稿了。</p>}
      </div>
      <div className="flex justify-end border-t px-5 py-3"><Button size="sm" variant={ok ? "gradient" : "outline"} onClick={onClose}>{ok ? "开始用" : "关闭"}</Button></div>
    </Modal>
  );
}
