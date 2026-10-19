import { Check, ExternalLink, ImageIcon, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { useImageSettings, useSaveImageSettings, useTestImage } from "../api/hooks";
import { cn } from "../lib/utils";
import { Badge, Button, ErrorText, Input, Modal, Spinner } from "./ui";

/** AI 配图：填 grsai 的 Key、选模型，可以先试出一张看看效果。Key 只存在本机。 */
export function ImageSettingsDialog({ onClose }: { onClose: () => void }) {
  const { data: st, isLoading } = useImageSettings();
  const save = useSaveImageSettings();
  const test = useTestImage();
  const [key, setKey] = useState("");
  const model = save.variables?.model && save.isPending ? save.variables.model : st?.model;

  return (
    <Modal className="max-w-xl" onClose={onClose}>
      <div className="flex items-start justify-between border-b px-5 py-4">
        <div>
          <div className="flex items-center gap-2 font-semibold"><ImageIcon className="size-4 text-indigo-500" />AI 配图</div>
          <p className="mt-0.5 text-xs text-muted-foreground">写完稿自动按配图描述出图（3:4 竖图，封面带大字标题）。Key 只存在这台电脑上。</p>
        </div>
        <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="关闭"><X className="size-4" /></button>
      </div>

      <div className="max-h-[70vh] space-y-5 overflow-y-auto px-5 py-4 text-sm">
        {isLoading || !st ? <Spinner /> : <>
          <section>
            <div className="mb-1.5 flex items-center gap-2 font-medium">
              API Key
              {st.configured
                ? <Badge className="bg-emerald-50 text-emerald-700"><Check className="size-3" />已配置{st.origin === "env" && "（来自 .env）"}</Badge>
                : <Badge className="bg-amber-50 text-amber-700">未配置</Badge>}
            </div>
            <div className="flex gap-2">
              <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off"
                placeholder={st.configured ? "已保存，要换就粘贴新的" : "粘贴 sk- 开头的 Key"} />
              <Button disabled={!key.trim()} loading={save.isPending && save.variables?.api_key != null}
                onClick={() => save.mutate({ api_key: key.trim() }, { onSuccess: () => setKey("") })}>保存</Button>
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
              用的是 grsai 生图服务，两个模型共用一个 Key。
              <a href="https://grsai.ai/zh/dashboard/api-keys" target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center gap-0.5 text-indigo-600 hover:underline">去获取<ExternalLink className="size-3" /></a>
              {st.origin === "ui" && <button className="ml-3 cursor-pointer text-muted-foreground underline-offset-2 hover:underline" onClick={() => save.mutate({ api_key: "" })}>清除</button>}
            </p>
          </section>

          <section>
            <div className="mb-1.5 font-medium">模型</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {st.models.map((m) => (
                <button key={m.id} onClick={() => m.id !== st.model && save.mutate({ model: m.id })}
                  className={cn("cursor-pointer rounded-xl border p-3 text-left transition",
                    model === m.id ? "border-indigo-400 bg-indigo-50/60 ring-1 ring-indigo-300" : "hover:border-indigo-200")}>
                  <div className="flex items-center gap-1.5 font-medium">
                    {m.label}{model === m.id && <Check className="size-3.5 text-indigo-600" />}
                  </div>
                  <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{m.desc}</div>
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">选中的模型出图失败时，会自动换另一个再试一次。</p>
          </section>

          <section className="rounded-xl bg-slate-50 p-3">
            <div className="flex items-center gap-2">
              <div className="flex-1 text-xs text-muted-foreground">试出一张封面看看效果（会用掉一次生图额度）</div>
              <Button size="sm" variant="outline" disabled={!st.configured && !key.trim()} loading={test.isPending}
                onClick={() => test.mutate({ api_key: key.trim() || null, model: st.model })}><Sparkles />试出一张</Button>
            </div>
            {test.isPending && <p className="mt-2 text-xs text-muted-foreground">生成中，GPT Image 大约 1 分钟，Nano Banana 大约 20 秒…</p>}
            <ErrorText error={test.error} />
            {test.data && (test.data.ok
              ? <div className="mt-3 flex items-start gap-3">
                  <img src={test.data.url} alt="试生成" className="w-40 rounded-lg border" />
                  <div className="text-xs text-muted-foreground">{test.data.model} · 用时 {test.data.seconds} 秒<br />能出图，配置没问题。</div>
                </div>
              : <p className="mt-2 text-xs text-red-600">没出来：{test.data.error}</p>)}
          </section>
          <ErrorText error={save.error} />
        </>}
      </div>
    </Modal>
  );
}
