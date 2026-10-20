import { Check, ExternalLink, ImageIcon, Sparkles, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useImageSettings, useSaveImageSettings, useTestImage } from "../api/hooks";
import { cn } from "../lib/utils";
import { Badge, Button, ErrorText, Input, Modal, Spinner } from "./ui";

const CH: Record<string, string> = { next: "openai-next", grsai: "grsai" };
const PAUSE_HOURS = 6;

function fmtTime(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** 一条生图通道的 Key：状态、粘贴保存、去获取、清除 */
function KeyRow({ name, tag, link, configured, origin, active, pending, onSave, note }: {
  name: string; tag: string; link: string; configured: boolean; origin: string; active: boolean; pending: boolean;
  onSave: (key: string, done: () => void) => void; note: ReactNode;
}) {
  const [key, setKey] = useState("");
  return (
    <div className={cn("rounded-xl border p-3", active && "border-indigo-300 bg-indigo-50/40")}>
      <div className="mb-1.5 flex flex-wrap items-center gap-2 font-medium">
        {name}<span className="text-xs font-normal text-muted-foreground">{tag}</span>
        {configured
          ? <Badge className="bg-emerald-50 text-emerald-700"><Check className="size-3" />已配置{origin === "env" && "（来自 .env）"}</Badge>
          : <Badge className="bg-slate-100 text-slate-600">未配置</Badge>}
        {active && <Badge className="bg-indigo-100 text-indigo-700">现在用这个</Badge>}
      </div>
      <div className="flex gap-2">
        <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off"
          placeholder={configured ? "已保存，要换就粘贴新的" : "粘贴 sk- 开头的 Key"} />
        <Button disabled={!key.trim()} loading={pending} onClick={() => onSave(key.trim(), () => setKey(""))}>保存</Button>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        {note}
        <a href={link} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center gap-0.5 text-indigo-600 hover:underline">去获取<ExternalLink className="size-3" /></a>
        {origin === "ui" && <button className="ml-3 cursor-pointer text-muted-foreground underline-offset-2 hover:underline" onClick={() => onSave("", () => {})}>清除</button>}
      </p>
    </div>
  );
}

/** AI 配图：填生图 Key（openai-next 优先、grsai 备用）、选模型，可以先试出一张看看效果。Key 只存在本机。 */
export function ImageSettingsDialog({ onClose }: { onClose: () => void }) {
  const { data: st, isLoading } = useImageSettings();
  const save = useSaveImageSettings();
  const test = useTestImage();
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
            <div className="font-medium">生图服务</div>
            <p className="mb-2 mt-0.5 text-xs text-muted-foreground">两个都填时先用 openai-next；它额度用完或出不了图，自动换 grsai 接着出，不用管。</p>
            <div className="space-y-2">
              <KeyRow name="openai-next" tag="优先用" link="https://credits.openai-next.com"
                configured={st.next_configured} origin={st.next_origin} active={st.channel === "next"}
                pending={save.isPending && save.variables?.next_api_key != null}
                onSave={(k, done) => save.mutate({ next_api_key: k }, { onSuccess: done })}
                note={st.next_exhausted_at
                  ? <span className="text-amber-700">{fmtTime(st.next_exhausted_at)} 额度用完了，{st.configured ? `接下来 ${PAUSE_HOURS} 小时先用 grsai，之后自动再试` : "填上 grsai 的 Key 就能接着出"}；充值后重新保存一下 Key 立刻恢复。</span>
                  : "支持 GPT Image 2.5、Gemini 3.1 Flash Image，一张大约 15–50 秒。"} />
              <KeyRow name="grsai" tag="备用" link="https://grsai.ai/zh/dashboard/api-keys"
                configured={st.configured} origin={st.origin} active={st.channel === "grsai"}
                pending={save.isPending && save.variables?.api_key != null}
                onSave={(k, done) => save.mutate({ api_key: k }, { onSuccess: done })}
                note={st.next_configured ? "openai-next 用完或出不了图时用它。" : "两个模型共用一个 Key。"} />
            </div>
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

          <section>
            <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 hover:border-indigo-200">
              <input type="checkbox" className="mt-0.5 size-4 accent-indigo-500" checked={st.use_refs}
                onChange={(e) => save.mutate({ use_refs: e.target.checked })} />
              <span>
                <span className="font-medium">照着样例图出图</span>
                <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                  账号有配图模板时，每张照模板里那种页的样例图排版；没有模板时，一张对一张照着这篇参考帖的原图做版式。内容和文字都换成本篇的（不照搬人物和文字）。
                  关掉就只按文字描述的风格出。不管开不开，一套图都用同一份视觉规范，保证统一。
                </span>
              </span>
            </label>
            <label className={cn("mt-2 flex items-start gap-2.5 rounded-xl border p-3", st.vision ? "cursor-pointer hover:border-indigo-200" : "opacity-60")}>
              <input type="checkbox" className="mt-0.5 size-4 accent-indigo-500" checked={st.check && st.vision} disabled={!st.vision}
                onChange={(e) => save.mutate({ check: e.target.checked })} />
              <span>
                <span className="font-medium">出完自己检查一遍</span>
                <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                  每张出完让 AI 看一眼：图上的字有没有错字乱码、画面和描述对不对得上、和同套的图是不是一个风格。有问题就带着修改意见自动重出一次（会多用一次生图额度），结果在草稿页每张图下面能看到。
                  {!st.vision && " 需要配好 DeepSeek Key 才能看图。"}
                </span>
              </span>
            </label>
          </section>

          <section className="rounded-xl bg-slate-50 p-3">
            <div className="flex items-center gap-2">
              <div className="flex-1 text-xs text-muted-foreground">试出一张封面看看效果（会用掉一次生图额度）</div>
              <Button size="sm" variant="outline" disabled={!st.channel} loading={test.isPending}
                onClick={() => test.mutate({ channel: st.channel, model: st.model })}><Sparkles />试出一张{st.channel && `（走 ${CH[st.channel]}）`}</Button>
            </div>
            {test.isPending && <p className="mt-2 text-xs text-muted-foreground">生成中，一般 15 秒到 1 分钟…</p>}
            <ErrorText error={test.error} />
            {test.data && (test.data.ok
              ? <div className="mt-3 flex items-start gap-3">
                  <img src={test.data.url} alt="试生成" className="w-40 rounded-lg border" />
                  <div className="text-xs text-muted-foreground">{CH[test.data.channel] ?? test.data.channel} · {test.data.model} · 用时 {test.data.seconds} 秒<br />能出图，配置没问题。</div>
                </div>
              : <p className="mt-2 text-xs text-red-600">没出来：{test.data.error}</p>)}
          </section>
          <ErrorText error={save.error} />
        </>}
      </div>
    </Modal>
  );
}
