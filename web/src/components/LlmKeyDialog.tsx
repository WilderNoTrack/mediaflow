import { Check, ExternalLink, KeyRound, X } from "lucide-react";
import { useState } from "react";
import { useLlmSettings, useSaveLlmKey } from "../api/hooks";
import { Badge, Button, ErrorText, Input, Modal } from "./ui";

/** 填 DeepSeek Key：不用改文件、不用重启。保存前会实际试一句，填错当场提示。 */
export function LlmKeyDialog({ onClose }: { onClose: () => void }) {
  const { data: st } = useLlmSettings();
  const save = useSaveLlmKey();
  const [key, setKey] = useState("");
  const ok = save.isSuccess && st?.configured;
  return (
    <Modal className="max-w-lg" onClose={onClose}>
      <div className="flex items-start justify-between border-b px-5 py-4">
        <div>
          <div className="flex items-center gap-2 font-semibold"><KeyRound className="size-4 text-indigo-500" />填写 DeepSeek Key</div>
          <p className="mt-0.5 text-xs text-muted-foreground">写文案、和小媒聊天都靠它。Key 只存在这台电脑上。</p>
        </div>
        <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="关闭"><X className="size-4" /></button>
      </div>
      <div className="space-y-4 px-5 py-4 text-sm">
        <ol className="space-y-1.5 text-xs leading-relaxed text-slate-600">
          <li>1. 打开 <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline">DeepSeek 开放平台<ExternalLink className="size-3" /></a>，用手机号注册登录</li>
          <li>2. 左边「充值」先少充一点（按用量计费），再到「API keys」点「创建 API key」</li>
          <li>3. 复制 sk- 开头的那串，粘贴到下面</li>
        </ol>
        <div className="flex items-center gap-2">
          {st?.configured
            ? <Badge className="bg-emerald-50 text-emerald-700"><Check className="size-3" />已经填好{st.origin === "env" && "（来自 .env）"}</Badge>
            : <Badge className="bg-amber-50 text-amber-700">还没填</Badge>}
        </div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (key.trim()) save.mutate(key.trim(), { onSuccess: () => setKey("") }); }}>
          <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off"
            placeholder={st?.configured ? "已保存，要换就粘贴新的" : "粘贴 sk- 开头的 Key"} />
          <Button type="submit" variant="gradient" disabled={!key.trim()} loading={save.isPending}>{save.isPending ? "验证中" : "验证并保存"}</Button>
        </form>
        <ErrorText error={save.error} />
        {ok && <p className="flex items-center gap-1.5 text-xs text-emerald-700"><Check className="size-3.5" />能用了！现在可以去和小媒聊天、写稿了。</p>}
      </div>
      <div className="flex justify-end border-t px-5 py-3"><Button size="sm" variant={ok ? "gradient" : "outline"} onClick={onClose}>{ok ? "开始用" : "关闭"}</Button></div>
    </Modal>
  );
}
